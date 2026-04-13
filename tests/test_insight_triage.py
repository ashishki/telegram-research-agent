import sqlite3
import unittest

from output.insight_triage import (
    classify_insight,
    load_rejection_fingerprints,
    parse_insights_html,
    render_triaged_insights_html,
    store_triage_results,
    triage_insights,
    update_rejection_memory,
    _dedupe_triaged_insights,
    _select_reportable_insights,
    _normalize_fingerprint,
    TriagedInsight,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_HTML = (
    "<b>💡 Инсайты недели</b>\n\n"
    '<b>[Implement] MyProject — Add retry logic</b>\n'
    "Добавить повторные попытки для нестабильных API.\n"
    '<a href="https://t.me/chan/1">источник</a>\n\n'
    '<b>[Build] Lightweight cost tracker</b>\n'
    "Инструмент для отслеживания затрат на LLM-вызовы в реальном времени.\n"
    '<a href="https://t.me/chan/2">источник</a>'
)


def _make_triage_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE insight_triage_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_label TEXT NOT NULL,
            title TEXT NOT NULL,
            idea_type TEXT NOT NULL,
            timing TEXT NOT NULL,
            implementation_mode TEXT NOT NULL,
            confidence TEXT NOT NULL,
            evidence_strength TEXT NOT NULL,
            main_risk TEXT NOT NULL,
            recommendation TEXT NOT NULL,
            reason TEXT NOT NULL,
            source_url TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE insight_rejection_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title_fingerprint TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            reason TEXT NOT NULL,
            rejected_at TEXT NOT NULL,
            suppressed_until TEXT
        );
        """
    )
    return conn


# ---------------------------------------------------------------------------
# parse_insights_html
# ---------------------------------------------------------------------------

class TestParseInsightsHtml(unittest.TestCase):
    def test_extracts_implement_and_build(self):
        results = parse_insights_html(_SAMPLE_HTML)
        self.assertEqual(len(results), 2)

    def test_implement_header_detected(self):
        results = parse_insights_html(_SAMPLE_HTML)
        header, _, _, _ = results[0]
        self.assertIn("[Implement]", header)

    def test_build_header_detected(self):
        results = parse_insights_html(_SAMPLE_HTML)
        header, _, _, _ = results[1]
        self.assertIn("[Build]", header)

    def test_source_url_extracted(self):
        results = parse_insights_html(_SAMPLE_HTML)
        _, _, url, _ = results[0]
        self.assertEqual(url, "https://t.me/chan/1")

    def test_empty_html_returns_empty_list(self):
        self.assertEqual(parse_insights_html(""), [])

    def test_no_idea_headers_returns_empty_list(self):
        self.assertEqual(parse_insights_html("<b>💡 Инсайты недели</b>"), [])


# ---------------------------------------------------------------------------
# classify_insight
# ---------------------------------------------------------------------------

class TestClassifyInsight(unittest.TestCase):
    def test_implement_classified_do_now(self):
        insight = classify_insight(
            "[Implement] MyProject — Fix a bug",
            "Direct fix to existing module.",
            "https://t.me/chan/1",
        )
        self.assertEqual(insight.recommendation, "do_now")
        self.assertEqual(insight.idea_type, "implement")

    def test_build_classified_backlog(self):
        insight = classify_insight(
            "[Build] New CLI tool",
            "A useful new command-line tool.",
            "https://t.me/chan/2",
        )
        self.assertEqual(insight.recommendation, "backlog")
        self.assertEqual(insight.idea_type, "build")

    def test_rebuild_mode_classified_reject(self):
        insight = classify_insight(
            "[Implement] MyProject — Rebuild entire pipeline",
            "Rewrite the whole system from scratch.",
            "https://t.me/chan/3",
        )
        self.assertEqual(insight.recommendation, "reject_or_defer")
        self.assertEqual(insight.implementation_mode, "rebuild")

    def test_speculative_build_classified_reject(self):
        insight = classify_insight(
            "[Build] Generic portfolio showcase",
            "Universal framework for portfolio.",
            "https://t.me/chan/4",
        )
        self.assertEqual(insight.recommendation, "reject_or_defer")

    def test_rejection_memory_suppresses_idea(self):
        fingerprint = _normalize_fingerprint("[Implement] MyProject — Fix a bug")
        insight = classify_insight(
            "[Implement] MyProject — Fix a bug",
            "Direct fix.",
            "https://t.me/chan/1",
            rejection_fingerprints={fingerprint},
        )
        self.assertEqual(insight.recommendation, "reject_or_defer")
        self.assertTrue(insight.suppressed)

    def test_non_rejected_fingerprint_not_suppressed(self):
        insight = classify_insight(
            "[Implement] MyProject — Fix a bug",
            "Direct fix.",
            "https://t.me/chan/1",
            rejection_fingerprints={"unrelated fingerprint"},
        )
        self.assertEqual(insight.recommendation, "do_now")
        self.assertFalse(insight.suppressed)

    def test_unknown_type_falls_back_to_backlog(self):
        insight = classify_insight(
            "Some idea without type prefix",
            "Body text.",
            "",
        )
        self.assertEqual(insight.recommendation, "backlog")
        self.assertEqual(insight.idea_type, "unknown")


# ---------------------------------------------------------------------------
# rejection memory persistence
# ---------------------------------------------------------------------------

class TestRejectionMemory(unittest.TestCase):
    def setUp(self):
        self.conn = _make_triage_db()

    def tearDown(self):
        self.conn.close()

    def test_store_and_load_rejection_fingerprints(self):
        insights = [
            TriagedInsight(
                title="[Build] Generic portfolio showcase",
                summary="Portfolio framework.",
                source_url="",
                idea_type="build",
                timing="quarter",
                implementation_mode="new",
                confidence="medium",
                evidence_strength="moderate",
                main_risk="distraction",
                recommendation="reject_or_defer",
                reason="speculative",
            )
        ]
        update_rejection_memory(self.conn, insights)
        self.conn.commit()

        fingerprints = load_rejection_fingerprints(self.conn)
        self.assertGreater(len(fingerprints), 0)

    def test_do_now_not_stored_in_rejection_memory(self):
        insights = [
            TriagedInsight(
                title="[Implement] MyProject — Fix bug",
                summary="Fix.",
                source_url="",
                idea_type="implement",
                timing="now",
                implementation_mode="extend",
                confidence="high",
                evidence_strength="strong",
                main_risk="low",
                recommendation="do_now",
                reason="direct improvement",
            )
        ]
        update_rejection_memory(self.conn, insights)
        self.conn.commit()

        fingerprints = load_rejection_fingerprints(self.conn)
        self.assertEqual(len(fingerprints), 0)


# ---------------------------------------------------------------------------
# store_triage_results
# ---------------------------------------------------------------------------

class TestStoreTriage(unittest.TestCase):
    def setUp(self):
        self.conn = _make_triage_db()

    def tearDown(self):
        self.conn.close()

    def test_stores_records_for_week(self):
        results = parse_insights_html(_SAMPLE_HTML)
        insights = [
            classify_insight(h, b, u, raw_html=r)
            for h, b, u, r in results
        ]
        store_triage_results(self.conn, "2026-W14", insights)
        self.conn.commit()

        rows = self.conn.execute(
            "SELECT COUNT(*) FROM insight_triage_records WHERE week_label = '2026-W14'"
        ).fetchone()
        self.assertEqual(rows[0], 2)

    def test_idempotent_on_repeated_call(self):
        results = parse_insights_html(_SAMPLE_HTML)
        insights = [classify_insight(h, b, u, raw_html=r) for h, b, u, r in results]
        store_triage_results(self.conn, "2026-W14", insights)
        store_triage_results(self.conn, "2026-W14", insights)
        self.conn.commit()

        rows = self.conn.execute(
            "SELECT COUNT(*) FROM insight_triage_records WHERE week_label = '2026-W14'"
        ).fetchone()
        self.assertEqual(rows[0], 2)


class TestInsightDedupe(unittest.TestCase):
    def test_dedupe_keeps_first_item_per_source_url(self):
        insights = [
            TriagedInsight(
                title="[Implement] Project A — First idea",
                summary="Use this signal.",
                source_url="https://t.me/chan/1",
                idea_type="implement",
                timing="now",
                implementation_mode="extend",
                confidence="high",
                evidence_strength="strong",
                main_risk="low",
                recommendation="do_now",
                reason="direct improvement",
            ),
            TriagedInsight(
                title="[Implement] Project B — Second idea",
                summary="Same source reused.",
                source_url="https://t.me/chan/1",
                idea_type="implement",
                timing="now",
                implementation_mode="extend",
                confidence="high",
                evidence_strength="strong",
                main_risk="low",
                recommendation="do_now",
                reason="direct improvement",
            ),
        ]

        deduped = _dedupe_triaged_insights(insights)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0].title, "[Implement] Project A — First idea")

    def test_selection_prefers_two_distinct_implement_and_one_build(self):
        insights = [
            TriagedInsight(
                title="[Implement] Project A — First idea",
                summary="Use this signal.",
                source_url="https://t.me/chan/1",
                idea_type="implement",
                timing="now",
                implementation_mode="extend",
                confidence="high",
                evidence_strength="strong",
                main_risk="low",
                recommendation="do_now",
                reason="direct improvement",
            ),
            TriagedInsight(
                title="[Implement] Project A — Second idea",
                summary="Same project should be skipped.",
                source_url="https://t.me/chan/2",
                idea_type="implement",
                timing="now",
                implementation_mode="extend",
                confidence="high",
                evidence_strength="strong",
                main_risk="low",
                recommendation="do_now",
                reason="direct improvement",
            ),
            TriagedInsight(
                title="[Implement] Project B — Third idea",
                summary="Second distinct project.",
                source_url="https://t.me/chan/3",
                idea_type="implement",
                timing="now",
                implementation_mode="extend",
                confidence="high",
                evidence_strength="strong",
                main_risk="low",
                recommendation="do_now",
                reason="direct improvement",
            ),
            TriagedInsight(
                title="[Build] New Tool — Exploration",
                summary="Only one build should remain.",
                source_url="https://t.me/chan/4",
                idea_type="build",
                timing="quarter",
                implementation_mode="new",
                confidence="medium",
                evidence_strength="moderate",
                main_risk="distraction",
                recommendation="backlog",
                reason="new project concept",
            ),
        ]

        selected = _select_reportable_insights(insights)

        self.assertEqual(len(selected), 3)
        self.assertEqual([item.title for item in selected], [
            "[Implement] Project A — First idea",
            "[Implement] Project B — Third idea",
            "[Build] New Tool — Exploration",
        ])

    def test_triage_pipeline_stores_only_one_record_for_duplicate_source(self):
        conn = _make_triage_db()
        try:
            html = (
                "<b>💡 Инсайты недели</b>\n\n"
                '<b>[Implement] Project A — First idea</b>\n'
                "Body one.\n"
                '<a href="https://t.me/chan/1">источник</a>\n\n'
                '<b>[Implement] Project B — Second idea</b>\n'
                "Body two.\n"
                '<a href="https://t.me/chan/1">источник</a>\n\n'
                '<b>[Build] New Tool — Third idea</b>\n'
                "Body three.\n"
                '<a href="https://t.me/chan/2">источник</a>'
            )

            insights = triage_insights(html, conn, "2026-W16")
            conn.commit()

            rows = conn.execute(
                "SELECT title, source_url FROM insight_triage_records WHERE week_label = '2026-W16'"
            ).fetchall()

            self.assertEqual(len(insights), 2)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0][0], "[Implement] Project A — First idea")
        finally:
            conn.close()

# ---------------------------------------------------------------------------
# triage_insights (full pipeline)
# ---------------------------------------------------------------------------

class TestTriageInsightsPipeline(unittest.TestCase):
    def setUp(self):
        self.conn = _make_triage_db()

    def tearDown(self):
        self.conn.close()

    def test_returns_correct_count(self):
        insights = triage_insights(_SAMPLE_HTML, self.conn, "2026-W14")
        self.assertEqual(len(insights), 2)

    def test_implement_is_do_now(self):
        insights = triage_insights(_SAMPLE_HTML, self.conn, "2026-W14")
        implement = next(i for i in insights if i.idea_type == "implement")
        self.assertEqual(implement.recommendation, "do_now")

    def test_empty_html_returns_empty(self):
        insights = triage_insights("", self.conn, "2026-W14")
        self.assertEqual(insights, [])


# ---------------------------------------------------------------------------
# render_triaged_insights_html
# ---------------------------------------------------------------------------

class TestRenderTriagedInsights(unittest.TestCase):
    def test_do_now_section_present(self):
        results = parse_insights_html(_SAMPLE_HTML)
        insights = [classify_insight(h, b, u, raw_html=r) for h, b, u, r in results]
        rendered = render_triaged_insights_html(_SAMPLE_HTML, insights)
        self.assertIn("Сделать сейчас", rendered)

    def test_backlog_section_present(self):
        results = parse_insights_html(_SAMPLE_HTML)
        insights = [classify_insight(h, b, u, raw_html=r) for h, b, u, r in results]
        rendered = render_triaged_insights_html(_SAMPLE_HTML, insights)
        self.assertIn("Бэклог", rendered)

    def test_do_now_before_backlog(self):
        results = parse_insights_html(_SAMPLE_HTML)
        insights = [classify_insight(h, b, u, raw_html=r) for h, b, u, r in results]
        rendered = render_triaged_insights_html(_SAMPLE_HTML, insights)
        idx_do_now = rendered.index("Сделать сейчас")
        idx_backlog = rendered.index("Бэклог")
        self.assertLess(idx_do_now, idx_backlog)

    def test_fallback_to_raw_html_when_no_insights(self):
        raw = "<b>raw content</b>"
        rendered = render_triaged_insights_html(raw, [])
        self.assertEqual(rendered, raw)

    def test_reason_annotation_present(self):
        results = parse_insights_html(_SAMPLE_HTML)
        insights = [classify_insight(h, b, u, raw_html=r) for h, b, u, r in results]
        rendered = render_triaged_insights_html(_SAMPLE_HTML, insights)
        self.assertIn("<i>(", rendered)


if __name__ == "__main__":
    unittest.main()

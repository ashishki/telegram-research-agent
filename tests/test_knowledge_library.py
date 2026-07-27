from __future__ import annotations

import json
import subprocess
import sys
import unittest

from output.knowledge_library import (
    KNOWLEDGE_LIBRARY_TOPIC_SCHEMA_VERSION,
    REQUIRED_VIEWPORTS,
    TOPIC_SECTIONS,
    KnowledgeLibraryValidationError,
    build_knowledge_library_topic_page,
    render_knowledge_library_topic_page_html,
    validate_knowledge_library_topic_page,
    validate_knowledge_library_visual_contract,
)


def _topic_payload() -> dict[str, object]:
    return {
        "topic": {
            "topic_id": "agent-eval-gates",
            "title": "Agent Eval Gates",
            "query": "agent eval gates",
            "source": "query",
        },
        "as_of": "2026-07-27T12:00:00Z",
        "current_understanding": (
            "Agent eval gates are useful only when they keep source evidence, "
            "current gaps, and follow-up decisions visible together."
        ),
        "claims": [
            {
                "id": "claim-1",
                "title": "Eval gates need cited evidence",
                "body": "A gate is weaker when it records scores without source refs.",
                "observed_at": "2026-07-25T09:30:00Z",
                "source_refs": ["fixture://telegram/post/1001"],
                "tags": ["evaluation"],
            }
        ],
        "cases": [
            {
                "title": "Assistant release checklist",
                "body": "A release checklist caught missing no-answer coverage.",
                "observed_at": "2026-07-01T08:00:00Z",
                "source_refs": ["fixture://telegram/post/1002"],
            }
        ],
        "tools": [
            {
                "title": "FTS retrieval receipt",
                "body": "Local FTS receipts keep search evidence separate from synthesis.",
                "observed_at": "2026-05-20T08:00:00Z",
                "source_refs": ["fixture://telegram/post/1003"],
            }
        ],
        "practices": [
            {
                "title": "Batch deep review by milestone block",
                "body": "Deep review is batched unless a stop-ship boundary is touched.",
                "observed_at": "2026-07-26T18:00:00Z",
                "source_refs": ["fixture://policy/review"],
            }
        ],
        "contradictions": [
            {
                "title": "High pass count can hide stale fixtures",
                "body": "A broad gate may still contain known date-sensitive failures.",
                "observed_at": "2026-07-27T10:00:00Z",
                "source_refs": ["fixture://tests/product-ops"],
            }
        ],
        "project_links": [
            {
                "title": "Personal research memory",
                "body": "Topic pages should point back to project decisions.",
                "observed_at": "2026-07-24T10:00:00Z",
                "source_refs": ["fixture://project/prm"],
            }
        ],
        "saved_notes": [
            {
                "title": "Keep Atlas as audit surface",
                "body": "The reader product should be topic pages, not the old global dump.",
                "observed_at": "2026-07-23T10:00:00Z",
                "source_refs": ["fixture://docs/product-contract"],
            }
        ],
        "open_questions": [
            {
                "title": "Which topic should become the first real dogfood page?",
                "body": "Needs human selection before live operator evidence is claimed.",
                "observed_at": "2026-07-27T11:00:00Z",
                "source_refs": ["fixture://dogfood/not-started"],
            }
        ],
        "memory_events": [
            {
                "id": 1,
                "object_type": "knowledge_note",
                "event_type": "created",
                "memory_id": "note-1",
                "title": "Confirmed note from assistant answer",
                "body": "Only an exact confirmation token turns this into durable memory.",
                "created_at": "2026-07-27T09:00:00Z",
                "source_refs_json": json.dumps(["fixture://assistant/answer/1"]),
            },
            {
                "id": 2,
                "object_type": "decision",
                "event_type": "created",
                "memory_id": "decision-1",
                "title": "Use FTS before vector adoption",
                "rationale": "Vector work remains blocked until an accepted ADR exists.",
                "created_at": "2026-07-20T09:00:00Z",
                "source_refs_json": json.dumps(["fixture://adr/vector"]),
            },
            {
                "id": 3,
                "object_type": "experiment",
                "event_type": "edited",
                "memory_id": "experiment-1",
                "title": "Run fixture topic page review",
                "body": "Fixture-only review avoids raw Telegram text in committed tests.",
                "created_at": "2026-06-10T09:00:00Z",
                "source_refs_json": json.dumps(["fixture://experiment/topic-page"]),
            },
            {
                "id": 4,
                "object_type": "knowledge_note",
                "event_type": "deleted",
                "title": "Deleted note must not render",
                "created_at": "2026-07-27T09:00:00Z",
            },
        ],
        "original_sources": [
            {
                "ref": "fixture://telegram/post/1001",
                "label": "Synthetic Telegram post 1001",
                "kind": "telegram_archive",
                "observed_at": "2026-07-25T09:30:00Z",
            },
            {
                "ref": "fixture://docs/product-contract",
                "label": "Product contract excerpt",
                "kind": "doc",
                "observed_at": "2026-07-23T10:00:00Z",
            },
        ],
        "archive_hits": [
            {
                "archive_document_id": "archive-doc-1002",
                "source_url": "fixture://telegram/post/1002",
                "title": "Synthetic Telegram post 1002",
                "posted_at": "2026-07-01T08:00:00Z",
            }
        ],
    }


class KnowledgeLibraryTests(unittest.TestCase):
    def test_topic_page_contains_required_prm13_sections(self) -> None:
        page = build_knowledge_library_topic_page(_topic_payload())

        self.assertEqual(page["schema_version"], KNOWLEDGE_LIBRARY_TOPIC_SCHEMA_VERSION)
        self.assertEqual(page["surface"], "knowledge_library_topic_page")
        self.assertEqual(set(page["sections"]), set(TOPIC_SECTIONS))
        for section in TOPIC_SECTIONS:
            self.assertIsInstance(page["sections"][section], list)

        self.assertEqual(page["changes_30d"]["status"], "available")
        self.assertEqual(page["changes_90d"]["status"], "available")
        self.assertGreaterEqual(page["changes_30d"]["new_evidence_count"], 1)
        self.assertGreaterEqual(page["changes_90d"]["new_evidence_count"], 1)
        self.assertEqual(page["open_question_count"], 1)
        self.assertEqual(page["visual_contract"]["viewports"], list(REQUIRED_VIEWPORTS))
        self.assertIn("fixture://telegram/post/1001", page["source_refs"])
        self.assertEqual(
            {entry["title"] for entry in page["sections"]["decisions"]},
            {"Use FTS before vector adoption"},
        )
        self.assertEqual(
            {entry["title"] for entry in page["sections"]["experiments"]},
            {"Run fixture topic page review"},
        )
        self.assertNotIn(
            "Deleted note must not render",
            {entry["title"] for entry in page["sections"]["saved_notes"]},
        )

    def test_render_topic_page_html_has_sections_sources_and_static_visual_contract(self) -> None:
        page = build_knowledge_library_topic_page(_topic_payload())
        html = render_knowledge_library_topic_page_html(page)
        receipt = validate_knowledge_library_visual_contract(html)

        self.assertIn('<main class="kl-page" data-surface="knowledge_library_topic_page">', html)
        self.assertIn('<meta name="viewport" content="width=device-width, initial-scale=1">', html)
        self.assertIn("Content-Security-Policy", html)
        self.assertNotIn("<script", html.lower())
        self.assertNotIn("<link", html.lower())
        self.assertNotIn("@import", html.lower())
        for section in TOPIC_SECTIONS:
            self.assertIn(f'data-section="{section}"', html)
        self.assertIn("Original Sources", html)
        self.assertIn("Synthetic Telegram post 1001", html)
        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(receipt["browser_snapshot_status"], "not_run_playwright_unavailable")

    def test_weasyprint_layout_smoke_uses_static_html_without_network_assets(self) -> None:
        page = build_knowledge_library_topic_page(_topic_payload())
        html = render_knowledge_library_topic_page_html(page)
        script = """
import sys
from weasyprint import HTML
document = HTML(string=sys.stdin.read(), media_type="screen").render()
if len(document.pages) < 1:
    raise SystemExit("no rendered pages")
page = document.pages[0]
print(f"{page.width} {page.height}")
"""

        for viewport in REQUIRED_VIEWPORTS:
            viewport_html = html.replace(
                "<style>",
                f"<style>@page{{size:{viewport['width']}px {viewport['height']}px;margin:0}}",
                1,
            )
            result = subprocess.run(
                [sys.executable, "-c", script],
                input=viewport_html,
                text=True,
                capture_output=True,
                check=False,
            )
            if result.returncode != 0 and "No module named 'weasyprint'" in result.stderr:
                self.skipTest("WeasyPrint unavailable")
            self.assertEqual(result.returncode, 0, result.stderr)
            width, height = [float(value) for value in result.stdout.strip().split()]
            self.assertEqual(width, float(viewport["width"]))
            self.assertEqual(height, float(viewport["height"]))

    def test_visual_contract_rejects_active_content_or_missing_mobile_rules(self) -> None:
        with self.assertRaisesRegex(KnowledgeLibraryValidationError, "no_script"):
            validate_knowledge_library_visual_contract(
                '<html><head><meta name="viewport"></head><body>'
                '<main data-surface="knowledge_library_topic_page">'
                "<script>alert(1)</script></main></body></html>"
            )

        with self.assertRaisesRegex(KnowledgeLibraryValidationError, "mobile_breakpoint"):
            validate_knowledge_library_visual_contract(
                '<html><head><meta name="viewport"></head><body>'
                '<main data-surface="knowledge_library_topic_page">'
                "<style>.x{display:grid;grid-template-columns:repeat(auto-fit,1fr);"
                "overflow-wrap: anywhere}</style></main></body></html>"
            )

    def test_validation_rejects_missing_required_sections(self) -> None:
        page = build_knowledge_library_topic_page(_topic_payload())
        sections = dict(page["sections"])
        sections.pop("claims")
        invalid_page = dict(page)
        invalid_page["sections"] = sections

        with self.assertRaisesRegex(KnowledgeLibraryValidationError, "missing sections: claims"):
            validate_knowledge_library_topic_page(invalid_page)


if __name__ == "__main__":
    unittest.main()

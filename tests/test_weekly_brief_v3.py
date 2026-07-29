from __future__ import annotations

import json
import subprocess
import sys
import unittest

from output.weekly_brief_v3 import (
    GENERIC_FALLBACK_ACTION_PHRASES,
    WEEKLY_BRIEF_V3_REQUIRED_VIEWPORTS,
    WEEKLY_BRIEF_V3_SCHEMA_VERSION,
    WEEKLY_BRIEF_V3_SECTIONS,
    WeeklyBriefV3ValidationError,
    build_weekly_brief_v3,
    render_weekly_brief_v3_html,
    validate_weekly_brief_v3_text_has_no_generic_fallbacks,
    validate_weekly_brief_v3_visual_contract,
)


def _brief_payload() -> dict[str, object]:
    return {
        "week_id": "2026-W30",
        "as_of": "2026-07-29T10:00:00Z",
        "watch_topics": [
            {
                "title": "Grounded assistant release gates",
                "body": "The watch topic shifted from router coverage to answer evidence quality.",
                "stance": "watch",
                "source_refs": ["fixture://watch-topic/grounded-assistant"],
            }
        ],
        "reacted_posts": [
            {
                "title": "Operator marked citation receipts useful",
                "body": "Useful reactions clustered around direct source links and uncertainty language.",
                "reaction": "useful",
                "source_refs": ["fixture://reaction/post-2001"],
            },
            {
                "title": "Operator marked generic advice weak",
                "body": "Weak feedback appears when actions are not tied to a project decision.",
                "reaction": "weak",
                "source_refs": ["fixture://reaction/post-2002"],
            },
        ],
        "questions": [
            {
                "question": "Which answer failures need an explicit no-answer path?",
                "body": "Study unanswered and external-verification-required replies before changing routing.",
                "source_refs": ["fixture://assistant/question-1"],
            }
        ],
        "saved_notes": [
            {
                "title": "No mastery from passive exposure",
                "body": "Learning state progress requires explicit receipts, not source presence.",
                "source_refs": ["fixture://memory/note-learning-state"],
            }
        ],
        "active_projects": [
            {
                "project": "Assistant release gate",
                "title": "Assistant release gate",
                "body": "Use the brief to connect weekly evidence to the release checklist.",
                "next_action": "Add a release-gate check for unsupported answer fallbacks",
                "source_refs": ["fixture://project/assistant-release"],
            }
        ],
        "repeated_signals": [
            {
                "title": "Unsupported answer fallback risk increased",
                "body": "Repeated signals point to citation and no-answer behavior as the week's main change.",
                "delta": "3 related feedback events in 7 days",
                "source_refs": ["fixture://signal/repeated-fallback-risk"],
            }
        ],
        "experiments": [
            {
                "title": "Fixture no-answer regression",
                "body": "A small fixture can prove that weak retrieval stays a no-answer.",
                "next_action": "Run the no-answer fixture against the assistant contract",
                "source_refs": ["fixture://experiment/no-answer-regression"],
            }
        ],
        "feedback": [
            {
                "label": "decision-impacting",
                "feedback": "decision-impacting",
                "source_refs": ["fixture://feedback/artifact-1"],
            }
        ],
        "radar": {
            "status": "available",
            "title": "Radar candidate: eval harness",
            "body": "Candidate is present but secondary to the project-gated ACT item.",
            "decision": "investigate",
            "source_refs": ["fixture://radar/candidate-1"],
        },
    }


class WeeklyBriefV3Tests(unittest.TestCase):
    def test_brief_v3_contains_required_projection_sections_and_legacy_demotions(self) -> None:
        brief = build_weekly_brief_v3(_brief_payload())

        self.assertEqual(brief["schema_version"], WEEKLY_BRIEF_V3_SCHEMA_VERSION)
        self.assertEqual(brief["artifact_type"], "weekly_brief_v3")
        for section in WEEKLY_BRIEF_V3_SECTIONS:
            self.assertIn(section, brief)
            self.assertIsInstance(brief[section], dict)

        self.assertEqual(brief["main_change"]["status"], "available")
        self.assertEqual(brief["act_item"]["mode"], "ACT")
        self.assertEqual(brief["study_item"]["mode"], "STUDY")
        self.assertIn(brief["watch_ignore_item"]["mode"], {"WATCH", "IGNORE"})
        self.assertEqual(brief["reaction_summary"]["total"], 3)
        self.assertEqual(brief["project_connection"]["title"], "Project: Assistant release gate")
        self.assertEqual(brief["radar_card"]["state"], "available")
        self.assertEqual(brief["feedback_request"]["status"], "requested")
        self.assertEqual(brief["non_radar_status"], "available")
        self.assertEqual(
            {entry["surface"] for entry in brief["legacy_surface_demotions"]},
            {"weekly_brief_v1", "knowledge_atlas"},
        )
        self.assertIn("fixture://signal/repeated-fallback-risk", brief["source_refs"])
        self.assertFalse(brief["privacy_boundary"]["llm_generation"])

    def test_generated_brief_rejects_generic_fallback_action_phrasing(self) -> None:
        brief = build_weekly_brief_v3(_brief_payload())
        serialized = json.dumps(brief, sort_keys=True)
        for phrase in GENERIC_FALLBACK_ACTION_PHRASES:
            self.assertNotIn(phrase, serialized.lower())

        invalid_payload = _brief_payload()
        invalid_payload["active_projects"] = [
            {
                "project": "Assistant release gate",
                "next_action": "Do more research on assistant fallbacks",
                "source_refs": ["fixture://project/assistant-release"],
            }
        ]

        with self.assertRaisesRegex(WeeklyBriefV3ValidationError, "generic fallback action phrase"):
            build_weekly_brief_v3(invalid_payload)

        with self.assertRaisesRegex(WeeklyBriefV3ValidationError, "generic fallback action phrase"):
            validate_weekly_brief_v3_text_has_no_generic_fallbacks(
                {"action": "Review the sources before deciding"}
            )

    def test_radar_failure_is_localized_to_radar_card(self) -> None:
        payload = _brief_payload()
        payload["radar"] = {
            "status": "failed",
            "error": "fixture Radar timeout",
        }
        brief = build_weekly_brief_v3(payload)

        self.assertEqual(brief["radar_card"]["state"], "failed")
        self.assertEqual(brief["radar_card"]["status"], "failed")
        self.assertIn("Radar failed locally", brief["radar_card"]["body"])
        self.assertEqual(brief["dependency_status"]["radar"], "failed")
        self.assertEqual(brief["dependency_status"]["archive_search"], "available")
        self.assertEqual(brief["dependency_status"]["assistant_answers"], "available")
        self.assertEqual(brief["dependency_status"]["knowledge_library"], "available")
        self.assertEqual(brief["non_radar_status"], "available")
        for section in (
            "main_change",
            "act_item",
            "study_item",
            "watch_ignore_item",
            "reaction_summary",
            "project_connection",
        ):
            self.assertEqual(brief[section]["status"], "available")

        html = render_weekly_brief_v3_html(brief)
        self.assertIn("Radar unavailable", html)
        self.assertIn("Project: Assistant release gate", html)

    def test_rendered_html_has_static_visual_contract_and_sections(self) -> None:
        brief = build_weekly_brief_v3(_brief_payload())
        html = render_weekly_brief_v3_html(brief)
        receipt = validate_weekly_brief_v3_visual_contract(html)

        self.assertIn('<main class="wb3-page" data-surface="weekly_brief_v3">', html)
        self.assertIn('<meta name="viewport" content="width=device-width, initial-scale=1">', html)
        self.assertIn("Content-Security-Policy", html)
        self.assertNotIn("<script", html.lower())
        self.assertNotIn("<link", html.lower())
        self.assertNotIn("@import", html.lower())
        for section in WEEKLY_BRIEF_V3_SECTIONS:
            if section == "radar_card":
                self.assertIn('data-section="radar_card"', html)
            else:
                self.assertIn(f'data-section="{section}"', html)
        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(receipt["browser_snapshot_status"], "not_run_playwright_unavailable")

    def test_weasyprint_layout_smoke_uses_static_html_without_network_assets(self) -> None:
        html = render_weekly_brief_v3_html(build_weekly_brief_v3(_brief_payload()))
        script = """
import sys
from weasyprint import HTML
document = HTML(string=sys.stdin.read(), media_type="screen").render()
if len(document.pages) < 1:
    raise SystemExit("no rendered pages")
page = document.pages[0]
print(f"{page.width} {page.height}")
"""

        for viewport in WEEKLY_BRIEF_V3_REQUIRED_VIEWPORTS:
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
        with self.assertRaisesRegex(WeeklyBriefV3ValidationError, "no_script"):
            validate_weekly_brief_v3_visual_contract(
                '<html><head><meta name="viewport"></head><body>'
                '<main data-surface="weekly_brief_v3">'
                "<script>alert(1)</script></main></body></html>"
            )

        with self.assertRaisesRegex(WeeklyBriefV3ValidationError, "mobile_breakpoint"):
            validate_weekly_brief_v3_visual_contract(
                '<html><head><meta name="viewport"></head><body>'
                '<main data-surface="weekly_brief_v3">'
                "<style>.x{display:grid;grid-template-columns:repeat(auto-fit,1fr);"
                "overflow-wrap: anywhere}</style></main></body></html>"
            )


if __name__ == "__main__":
    unittest.main()

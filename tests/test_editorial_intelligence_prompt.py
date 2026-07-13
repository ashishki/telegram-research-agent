import copy
import json
import unittest

from output.editorial_intelligence_prompt import (
    EDITORIAL_MAX_PROJECT_ACTIONS,
    EDITORIAL_MAX_SIGNALS,
    EDITORIAL_MAX_TOKENS,
    EDITORIAL_PROMPT_VERSION,
    EDITORIAL_SCHEMA_VERSION,
    build_editorial_prompt,
)


class EditorialIntelligencePromptTests(unittest.TestCase):
    def _package(self) -> dict[str, object]:
        return {
            "run_id": "tra-weekly-2026-W28-test",
            "reporting_period": {
                "reporting_week": "2026-W28",
                "analysis_period_start": "2026-07-06T00:00:00Z",
                "analysis_period_end": "2026-07-13T00:00:00Z",
            },
            "eligible_evidence": [
                {
                    "evidence_ref": "evidence:agent-evaluation",
                    "maturity": "single_source",
                    "summary_ru": "Проверка пока опирается на один источник.",
                }
            ],
            "selected_signals": [
                {
                    "signal_id": "signal:agent-evaluation",
                    "evidence_refs": ["evidence:agent-evaluation"],
                    "title_ru": "Проверяемость агентных систем",
                }
            ],
            "reaction_effect": {"effect": "linked_only"},
            "project_permissions": [],
            "radar": {
                "radar_ref": "radar:w28",
                "reader_decision": "investigate",
                "context_only": True,
            },
        }

    def test_public_contract_constants_are_frozen(self) -> None:
        self.assertEqual(EDITORIAL_SCHEMA_VERSION, "editorial_intelligence.v1")
        self.assertEqual(EDITORIAL_PROMPT_VERSION, "editorial-intelligence-v1")
        self.assertEqual(EDITORIAL_MAX_SIGNALS, 3)
        self.assertEqual(EDITORIAL_MAX_PROJECT_ACTIONS, 2)
        self.assertEqual(EDITORIAL_MAX_TOKENS, 6000)

    def test_prompt_is_deterministic_for_equivalent_mapping_order(self) -> None:
        package = self._package()
        reordered = dict(reversed(list(package.items())))

        first = build_editorial_prompt(package)
        second = build_editorial_prompt(reordered)

        self.assertEqual(first, second)
        system, prompt = first
        self.assertIn("Проверяемость агентных систем", prompt)
        self.assertNotIn("\\u041f", prompt)
        payload_text = prompt.split("INPUT_PACKAGE_JSON:\n", 1)[1]
        self.assertEqual(json.loads(payload_text), package)
        self.assertTrue(system.strip())

    def test_prompt_builder_does_not_mutate_nested_input(self) -> None:
        package = self._package()
        before = copy.deepcopy(package)

        build_editorial_prompt(package)

        self.assertEqual(package, before)

    def test_system_prompt_enforces_editorial_boundaries(self) -> None:
        system, prompt = build_editorial_prompt(self._package())

        for expected in (
            "at most 3 signals",
            "at most\n  2 project_actions",
            "concise Russian plain language",
            "Never invent or repair a missing reference",
            "context_only",
            "Never promote",
            "Do not\n  place one signal in more than one matrix category",
            "loaded or considered feedback is not an applied effect",
            "Weak or low-maturity evidence requires explicit cautious wording",
            "copy\n  zero_change_thesis from the input exactly",
            "Do not repeat generic action prose",
            "no Markdown fence, commentary, HTML, SVG, or extra text",
            "The host, not the model, attaches generation_receipt",
        ):
            self.assertIn(expected, system)
        self.assertIn("Return JSON only", prompt)

    def test_output_skeleton_has_exact_model_authored_top_level_fields(self) -> None:
        system, _ = build_editorial_prompt(self._package())
        skeleton_text = system.split(
            "Exact model-output skeleton (placeholder values describe what to copy or author):\n",
            1,
        )[1]
        skeleton = json.loads(skeleton_text)

        self.assertEqual(
            list(skeleton),
            [
                "schema_version",
                "run_id",
                "reporting_period",
                "weekly_thesis",
                "decision_matrix",
                "signals",
                "project_actions",
                "feedback_effect",
                "mvp_summary",
                "visual_specs",
                "feedback_targets",
            ],
        )
        self.assertNotIn("generation_receipt", skeleton)
        self.assertEqual(skeleton["schema_version"], EDITORIAL_SCHEMA_VERSION)
        self.assertEqual(
            set(skeleton["decision_matrix"]), {"act", "study", "watch", "ignore"}
        )

    def test_non_mapping_and_non_json_numbers_fail_closed(self) -> None:
        with self.assertRaises(TypeError):
            build_editorial_prompt([])  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            build_editorial_prompt({"score": float("nan")})


if __name__ == "__main__":
    unittest.main()

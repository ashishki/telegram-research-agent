import unittest

from assistant.project_context import (
    build_project_context_decision_support,
    render_project_context_answer,
)


EVAL_PROJECT = {
    "name": "Eval-Ground-Truth-Lab",
    "repo": "ashishki/Eval-Ground-Truth-Lab",
    "description": "Evaluation lab for coding-agent ground truth, judge calibration, and evidence-backed acceptance.",
    "focus": "gold labels, holdout sets, evaluator rubrics, citation correctness, replayable fixtures",
    "keywords": [
        "ground truth",
        "gold labels",
        "holdout sets",
        "evaluator rubrics",
        "citation correctness",
        "replayable fixtures",
        "eval",
    ],
    "learning_keywords": ["judge calibration"],
    "exclude_keywords": ["production mvp"],
}


def _archive(snippet: str, *, source_url: str = "https://t.me/eval_lab/1001") -> dict:
    return {
        "status": "ok",
        "items": [
            {
                "archive_document_id": "tg:-1001:1001",
                "posted_at": "2026-07-20T10:00:00Z",
                "source_url": source_url,
                "snippet": snippet,
            }
        ],
    }


def _curated(summary: str) -> dict:
    return {
        "status": "ok",
        "items": [
            {
                "id": "claim-1",
                "item_type": "claim_card",
                "title": "Grounded eval infrastructure",
                "summary": summary,
                "source_refs": ["https://t.me/eval_lab/1002"],
                "atom_ids": [501],
            }
        ],
    }


class TestProjectContext(unittest.TestCase):
    def test_direct_project_context_cites_archive_and_names_descriptor_fields(self):
        result = build_project_context_decision_support(
            query="What applies to Eval-Ground-Truth-Lab?",
            project_descriptor=EVAL_PROJECT,
            archive_result=_archive(
                "Coding-agent evals need ground truth labels, citation correctness checks, and holdout sets."
            ),
            curated_result=_curated("Judge calibration needs evidence-backed acceptance fixtures."),
        )

        self.assertEqual(result["schema_version"], "project_context_decision_support.v1")
        self.assertEqual(result["relevance_label"], "direct_implication")
        self.assertIn("https://t.me/eval_lab/1001", result["archive_evidence"]["source_refs"])
        self.assertIn("https://t.me/eval_lab/1001", result["source_refs"])
        self.assertIn("keywords", result["descriptor_fields_used"])
        self.assertIn("focus", result["descriptor_fields_used"])
        self.assertTrue(result["project_suggestions"])
        self.assertFalse(result["decision_support"]["automatic_mvp_build_approval"])
        self.assertFalse(result["decision_support"]["code_mutation_exposed"])
        self.assertFalse(result["decision_support"]["project_mutation_exposed"])

        answer = render_project_context_answer(result)
        self.assertIn("Eval-Ground-Truth-Lab -> direct_implication", answer)
        self.assertIn("Descriptor fields used:", answer)
        self.assertIn("https://t.me/eval_lab/1001", answer)
        self.assertIn("no MVP build approval", answer)

    def test_weak_keyword_only_match_does_not_create_project_suggestion(self):
        result = build_project_context_decision_support(
            query="Should this eval mention become a project action?",
            project_descriptor=EVAL_PROJECT,
            archive_result=_archive("A general eval benchmark was mentioned without ground truth or label details."),
            curated_result={"status": "empty", "items": []},
        )

        self.assertEqual(result["relevance_label"], "weak_watch")
        self.assertEqual(result["project_suggestions"], [])
        self.assertEqual(result["watch_or_learning"]["kind"], "weak_watch")
        self.assertIn("do not turn it into an action", result["watch_or_learning"]["reader_guidance"])

    def test_learning_relevance_is_separate_from_direct_implication(self):
        result = build_project_context_decision_support(
            query="What should I study for Eval-Ground-Truth-Lab?",
            project_descriptor=EVAL_PROJECT,
            archive_result=_archive("A reference pattern for judge calibration can help evaluation design."),
            curated_result={"status": "empty", "items": []},
        )

        self.assertEqual(result["relevance_label"], "learning_relevance")
        self.assertEqual(result["project_suggestions"], [])
        self.assertEqual(result["watch_or_learning"]["kind"], "learning_relevance")
        self.assertIn("direct project implication", result["unknowns"])

    def test_no_match_stays_no_match_even_with_source_evidence(self):
        result = build_project_context_decision_support(
            query="Does this apply to Eval-Ground-Truth-Lab?",
            project_descriptor=EVAL_PROJECT,
            archive_result=_archive("Film school lesson planning and classroom exercises."),
            curated_result={"status": "empty", "items": []},
        )

        self.assertEqual(result["relevance_label"], "no_match")
        self.assertEqual(result["project_suggestions"], [])
        self.assertEqual(result["watch_or_learning"]["kind"], "no_match")


if __name__ == "__main__":
    unittest.main()

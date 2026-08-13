import unittest

from assistant.professional_personalization import (
    LENS_IDS,
    PROFESSIONAL_PERSONALIZATION_SCHEMA_VERSION,
    professional_lens_schema,
    propose_lens_preference_change,
    rerank_for_professional_lens,
)


class TestProfessionalPersonalization(unittest.TestCase):
    def test_lens_schema_contract(self):
        schema = professional_lens_schema()

        self.assertEqual(schema["schema_version"], PROFESSIONAL_PERSONALIZATION_SCHEMA_VERSION)
        self.assertTrue(schema["lens_policy"]["recall_never_reduced_by_lens"])
        self.assertTrue(schema["lens_policy"]["durable_changes_require_confirmation"])
        self.assertEqual(set(schema["professional_lenses"]), set(LENS_IDS))
        for definition in schema["professional_lenses"].values():
            self.assertTrue(definition["goals"])
            self.assertTrue(definition["evidence_preferences"])
            self.assertTrue(definition["output_preferences"])

    def test_lens_does_not_reduce_recall_candidates(self):
        candidates = [
            {"source_url": "https://t.me/example/1", "snippet": "RAG evaluation postmortem"},
            {"source_url": "https://t.me/example/2", "snippet": "editorial angle for Russian post"},
            {"source_url": "https://t.me/example/3", "snippet": "unrelated retained context"},
        ]

        ranked = rerank_for_professional_lens(candidates, lens_id="ai_systems_engineer")

        self.assertEqual({item["source_url"] for item in ranked}, {item["source_url"] for item in candidates})
        self.assertEqual(len(ranked), len(candidates))
        self.assertEqual(ranked[0]["source_url"], "https://t.me/example/1")

    def test_lens_preference_change_requires_confirmation(self):
        proposal = propose_lens_preference_change(
            requested_lens="writer_editor",
            current_default_lens="ai_systems_engineer",
        )

        self.assertEqual(proposal["status"], "proposed")
        self.assertTrue(proposal["requires_human_confirmation"])
        self.assertFalse(proposal["write_performed"])
        self.assertFalse(proposal["profile_mutation_exposed"])


if __name__ == "__main__":
    unittest.main()

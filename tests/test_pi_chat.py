import unittest

from assistant.pi_chat import answer_pi_chat


class _FakeFacade:
    def get_workbook_summary(self, week_label=None):
        return {
            "status": "ok",
            "week_label": week_label or "2026-W28",
            "decision_brief": [{"title": "Eval gates", "summary": "Eval gates matter."}],
            "artifact_paths": {"html": "/tmp/workbook.html"},
            "message": "Workbook summary loaded.",
        }

    def get_artifact_status(self, week_label=None):
        return {
            "status": "partial",
            "week_label": week_label or "2026-W28",
            "weekly_brief": {"display_name": "Weekly Brief", "status": "current"},
            "knowledge_atlas": {"display_name": "Knowledge Atlas", "status": "current"},
            "mvp_radar": {"display_name": "MVP Radar", "status": "missing"},
            "mvp_radar_gate": {
                "decision": "do_not_build",
                "matched_gate_evidence_count": 0,
                "market_context_status": "context_only",
            },
            "artifact_paths": {
                "weekly_intelligence_brief_json": "/tmp/2026-W28.weekly-brief.json",
                "knowledge_atlas_json": "/tmp/2026-W28.knowledge-atlas.json",
            },
            "message": "Weekly Brief: current; Knowledge Atlas: current; MVP Radar: missing",
        }

    def search_intelligence_items(self, query, filters=None, limit=10):
        return {
            "status": "ok",
            "query": query,
            "filters": filters or {},
            "items": [
                {
                    "id": "claim-1",
                    "item_type": "claim_card",
                    "title": "Eval gates",
                    "summary": "Eval gates are now release infrastructure.",
                    "source_refs": ["https://t.me/source/1"],
                    "atom_ids": [101],
                }
            ],
            "message": "Curated intelligence items matched deterministic search.",
        }

    def get_action_statuses(self, week_label=None):
        return {
            "status": "ok",
            "week_label": week_label,
            "items": [{"title": "Try eval gate", "status": "unknown"}],
            "message": "Action statuses loaded.",
        }

    def get_project_actions(self, week_label=None):
        return {
            "status": "ok",
            "week_label": week_label,
            "items": [{"project": "telegram-research-agent", "action": "Test Hermes chat"}],
            "message": "Project actions loaded.",
        }


class _FakeLLM:
    @staticmethod
    def complete_json(prompt, system="", category="unknown", model=None):
        return {
            "tool_calls": [
                {"name": "get_weekly_summary", "arguments": {"week_label": "2026-W28"}},
                {"name": "search_intelligence_items", "arguments": {"query": "eval gates", "limit": 3}},
            ],
            "reason": "Need weekly context and specific curated evidence.",
        }

    @staticmethod
    def complete(prompt, system="", max_tokens=2048, category="unknown", model=None):
        assert "Eval gates are now release infrastructure" in prompt
        assert "https://t.me/source/1" in prompt
        return "Eval gates matter this week. Source: https://t.me/source/1; atom:101."


class _BrokenPlannerLLM(_FakeLLM):
    @staticmethod
    def complete_json(prompt, system="", category="unknown", model=None):
        raise RuntimeError("planner unavailable")

    @staticmethod
    def complete(prompt, system="", max_tokens=2048, category="unknown", model=None):
        return "Hermes found curated actions and evidence. Source: https://t.me/source/1."


class _NoAnswerLLM(_BrokenPlannerLLM):
    @staticmethod
    def complete(prompt, system="", max_tokens=2048, category="unknown", model=None):
        raise RuntimeError("answer unavailable")


class TestPIChat(unittest.TestCase):
    def test_answer_pi_chat_runs_llm_planned_read_only_tools(self):
        result = answer_pi_chat("Что с eval gates?", facade=_FakeFacade(), llm_client=_FakeLLM)

        self.assertEqual(result["status"], "ok")
        self.assertIn("Eval gates matter", result["answer"])
        self.assertEqual([call["name"] for call in result["tool_calls"]], ["get_weekly_summary", "search_intelligence_items"])
        self.assertIn("https://t.me/source/1", result["evidence"]["source_refs"])
        self.assertIn(101, result["evidence"]["atom_ids"])
        self.assertTrue(all(call["name"] != "run_codex" for call in result["tool_calls"]))

    def test_answer_pi_chat_rejects_non_catalog_tool(self):
        class BadToolLLM(_FakeLLM):
            @staticmethod
            def complete_json(prompt, system="", category="unknown", model=None):
                return {"tool_calls": [{"name": "run_codex", "arguments": {"prompt": "do it"}}]}

        result = answer_pi_chat("Запусти Codex", facade=_FakeFacade(), llm_client=BadToolLLM)

        self.assertEqual(result["tool_results"][0]["status"], "rejected")
        self.assertIn("not in read-only PI catalog", result["tool_results"][0]["result"]["message"])

    def test_answer_pi_chat_falls_back_when_planning_fails(self):
        result = answer_pi_chat("Что делать по проектам?", facade=_FakeFacade(), llm_client=_BrokenPlannerLLM)

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["tool_calls"])
        self.assertIn("Source:", result["answer"])

    def test_answer_pi_chat_falls_back_to_artifact_status_for_brief_atlas_radar(self):
        result = answer_pi_chat("Какие артефакты Brief Atlas Radar актуальны?", facade=_FakeFacade(), llm_client=_NoAnswerLLM)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["tool_calls"][0]["name"], "get_artifact_status")
        self.assertIn("get_artifact_status", result["answer"])
        self.assertIn("MVP Radar", result["tool_results"][0]["result"]["message"])
        self.assertIn("/tmp/2026-W28.weekly-brief.json", result["answer"])

    def test_answer_pi_chat_handles_empty_question(self):
        result = answer_pi_chat("", facade=_FakeFacade(), llm_client=_FakeLLM)

        self.assertEqual(result["status"], "invalid")
        self.assertIn("Напиши вопрос", result["answer"])


if __name__ == "__main__":
    unittest.main()

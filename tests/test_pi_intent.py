import unittest
import sys
import types


def _install_stub(module_name: str, **attributes: object) -> None:
    if module_name in sys.modules:
        return
    module = types.ModuleType(module_name)
    for name, value in attributes.items():
        setattr(module, name, value)
    sys.modules[module_name] = module


_install_stub(
    "anthropic",
    APIConnectionError=Exception,
    APIStatusError=Exception,
    APITimeoutError=Exception,
    Anthropic=object,
    RateLimitError=Exception,
)

from assistant.pi_intent import classify_operator_message


class _BrokenLLM:
    @staticmethod
    def complete_json(prompt, system="", category="unknown", model=None):
        raise RuntimeError("offline")


class _FeedbackLLM:
    @staticmethod
    def complete_json(prompt, system="", category="unknown", model=None):
        return {"intent": "feedback", "confidence": 0.91, "reason": "operator reports quality"}


class _LowConfidenceLLM:
    @staticmethod
    def complete_json(prompt, system="", category="unknown", model=None):
        return {"intent": "feedback", "confidence": 0.2, "reason": "uncertain"}


class TestPIIntent(unittest.TestCase):
    def test_llm_classification_is_used_when_confident(self):
        result = classify_operator_message(
            "это было полезно, но shallow",
            input_kind="voice_transcript",
            llm_client=_FeedbackLLM,
        )

        self.assertEqual(result["intent"], "feedback")
        self.assertGreater(result["confidence"], 0.9)

    def test_heuristic_routes_reminders_when_llm_unavailable(self):
        result = classify_operator_message(
            "напомни завтра дать feedback по workbook",
            llm_client=_BrokenLLM,
        )

        self.assertEqual(result["intent"], "reminder")

    def test_low_confidence_falls_back_to_chat_for_questions_about_feedback(self):
        result = classify_operator_message(
            "как теперь работает feedback?",
            llm_client=_LowConfidenceLLM,
        )

        self.assertEqual(result["intent"], "chat")

    def test_empty_message_defaults_to_chat(self):
        result = classify_operator_message("", llm_client=_BrokenLLM)

        self.assertEqual(result["intent"], "chat")
        self.assertEqual(result["confidence"], 0.0)


if __name__ == "__main__":
    unittest.main()

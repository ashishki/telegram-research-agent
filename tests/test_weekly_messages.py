import unittest

from output.weekly_messages import build_brief_message, build_implementation_message, build_mvp_message


class TestWeeklyMessages(unittest.TestCase):
    def test_build_brief_message_is_compact_and_reader_facing(self):
        message = build_brief_message(
            week_label="2026-W25",
            posts=[
                {
                    "id": 1,
                    "bucket": "watch",
                    "signal_score": 0.8,
                    "view_count": 100,
                    "topic_label": "agent self-improvement",
                    "channel_username": "@Redmadnews",
                    "message_url": "https://t.me/Redmadnews/5304",
                    "content": (
                        "Рекурсивное улучшение: ИИ начинает работать над собой. "
                        "Anthropic описывает, как модели помогают улучшать своих преемников."
                    ),
                }
            ],
            bucket_counts={"strong": 0, "watch": 1, "noise": 3},
            top_topics=[{"label": "agent self-improvement", "post_count": 1}],
        )

        self.assertIn("Бриф недели 2026-W25", message)
        self.assertIn("Источник: @Redmadnews", message)
        self.assertNotIn("bucket", message)
        self.assertNotIn("Matches:", message)
        self.assertLess(len(message), 3200)

    def test_build_implementation_message_filters_to_existing_project_work(self):
        html = """
        <b>[Implement] gdev-agent — Добавить eval для guardrail</b>
        Нужно добавить один тестовый набор и прогонять его в CI.
        <a href="https://t.me/example/1">источник</a>
        <i>(✅ Сделать сейчас)</i>
        <b>[Build] New Product — Новый продукт</b>
        Не должен попасть в implementation.
        <a href="https://t.me/example/2">источник</a>
        """

        message = build_implementation_message(week_label="2026-W25", insights_html=html)

        self.assertIn("Что улучшить в проектах — 2026-W25", message)
        self.assertIn("gdev-agent — Добавить eval для guardrail", message)
        self.assertIn("это не новые продукты", message)
        self.assertNotIn("New Product", message)

    def test_build_mvp_message_states_evidence_gap(self):
        message = build_mvp_message(
            week_label="2026-W25",
            title="LLM Guardrail Watchdog",
            status="investigate",
            recommendation="revisit_with_evidence_gap",
            score=64,
            source_mix={
                "selected_telegram_seed_evidence_count": 1,
                "selected_external_evidence_count": 0,
            },
            live_intelligence={"repeated_claim_count": 0},
        )

        self.assertIn("MVP-кандидат 2026-W25: LLM Guardrail Watchdog", message)
        self.assertIn("Решение: пока не строим.", message)
        self.assertIn("Два независимых внешних источника", message)


if __name__ == "__main__":
    unittest.main()

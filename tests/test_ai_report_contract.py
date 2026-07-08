import json
import unittest
from pathlib import Path

from output.ai_report_contract import (
    REPORT_CONTRACT_VERSION,
    build_weekly_ai_report_contract,
    validate_weekly_ai_report_contract,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
W28_FIXTURE_ROOT = PROJECT_ROOT / "docs" / "artifacts" / "ai-decision-intelligence-2026-W28"


def _valid_html() -> str:
    return """
<!doctype html>
<html lang="ru">
<body>
<section id="operator-verdict"><h2>Операторский вердикт</h2><p>Русский текст отчета для оператора.</p></section>
<section id="claim-evidence"><h2>Доказательства по ключевым утверждениям</h2><p>Карточки утверждений с источниками.</p></section>
<section id="what-changed"><h2>Что изменилось</h2><p>Было, новое свидетельство, обновленная интерпретация.</p></section>
<section id="actions"><h2>Операционные действия</h2><p>Действия с критерием успеха и остановки.</p></section>
<section id="project-diagnostic"><h2>Диагностика проектного соответствия</h2><p>Проекты проверены, широкие совпадения отклонены.</p></section>
<section id="feedback"><h2>Какой фидбек оставить</h2><p>Минимальный фидбек недели: прочитано, попробовано, пропущено, доверие исправлено.</p></section>
</body>
</html>
"""


def _complete_contract_metadata() -> dict:
    return {
        "report_contract": {
            "version": REPORT_CONTRACT_VERSION,
            "html_language": "ru",
        },
        "decision_cards": [
            {
                "id": "decision-1",
                "verdict": "apply",
                "title": "Проверить eval-гейт",
                "why_for_operator": "Это снижает риск agent-written изменений.",
                "evidence_atom_ids": [1],
                "confidence": "medium",
                "next_action": "Запустить маленькую проверку.",
                "success_criterion": "Плохое изменение заблокировано.",
                "feedback_target_id": "action-1-feedback",
            },
            {
                "id": "decision-2",
                "verdict": "study",
                "title": "Изучить J-space",
                "why_for_operator": "Это влияет на safety tooling.",
                "evidence_atom_ids": [2],
                "confidence": "low",
                "next_action": "Прочитать источник.",
                "success_criterion": "Есть краткая заметка.",
                "feedback_target_id": "read-1-feedback",
            },
            {
                "id": "decision-3",
                "verdict": "verify_first",
                "title": "Проверить benchmark",
                "why_for_operator": "Утверждение одноисточниковое.",
                "evidence_atom_ids": [3],
                "confidence": "low",
                "next_action": "Найти независимое подтверждение.",
                "success_criterion": "Подтверждение найдено или claim понижен.",
                "feedback_target_id": "trust-feedback",
            },
        ],
        "claim_cards": [
            {
                "id": f"claim-{index}",
                "claim": f"Утверждение {index}",
                "evidence_atom_ids": [index],
                "source_post_ids": [index],
                "source_count": 1,
                "source_urls": [f"https://t.me/source/{index}"],
                "source_independence_key": "telegram:source",
                "evidence_tier": "verified_single_source",
                "evidence_role": "practice_report",
                "verification_status": "verified",
                "quote_verified": True,
                "claim_scope": "practice",
                "time_horizon": "medium_to_long",
                "confidence": "medium",
                "caveat": "Цитата проверена, но источник один.",
                "expiry_hint": "Проверить заново через месяц.",
                "staleness_status": "active",
                "wording_policy": "source_bounded",
                "next_verification_step": "Сверить источник и найти подтверждение.",
                "decision_eligible": True,
            }
            for index in range(1, 4)
        ],
        "deep_explanation_cards": [
            {
                "id": f"deep-explain-{index}",
                "claim_card_id": f"claim-{index}",
                "title": f"Утверждение {index}",
                "what_is_this": f"Plain-language explanation {index}",
                "why_now": "Сигнал попал в сильные карточки недели.",
                "how_it_works": "Проверить источник и связать claim с действием.",
                "where_is_hype": "Хайп там, где нет независимого источника.",
                "what_to_do": "Проверить цитату и сделать маленький тест.",
                "what_not_to_do": "Не считать build-ready без новой проверки.",
                "caveat": "Цитата проверена, но источник один.",
                "source_urls": [f"https://t.me/source/{index}"],
                "evidence_tier": "verified_single_source",
                "quote_verification_status": "verified",
                "what_would_change_my_mind": "Независимый источник опровергнет claim или тест провалится.",
                "explanatory_only": True,
            }
            for index in range(1, 4)
        ],
        "thread_deltas": [
            {
                "thread_slug": "eval-gates",
                "previous_state": "Раньше это было практикой отдельных задач.",
                "previous_week_state": "Раньше это было практикой отдельных задач.",
                "new_evidence": "Новый атом связывает eval с релизом.",
                "this_week_evidence": [
                    {
                        "atom_id": 1,
                        "claim": "Новый атом связывает eval с релизом.",
                        "source_urls": ["https://t.me/source/1"],
                        "last_seen_at": "2026-07-06T08:00:00Z",
                        "confidence": "medium",
                    }
                ],
                "updated_interpretation": "Теперь это релизная дисциплина.",
                "confidence_movement": "up",
                "confidence_change": "up",
                "delta_reason": "Появилось новое свидетельство.",
                "new_evidence_atom_ids": [1],
                "state": "updated",
                "why_this_is_one_thread": "Связано общими сущностями/практиками: eval gates.",
                "merge_split_audit_status": "ok",
            }
        ],
        "action_cards": [
            {
                "id": "action-1",
                "target_ref": "action-1",
                "action_kind": "try",
                "title": "Проверить eval-гейт",
                "effort": "30 мин",
                "scope": "experiment",
                "next_step": "Собрать одну проверку.",
                "success_criterion": "Плохое изменение заблокировано.",
                "kill_condition": "Остановить, если нет измеримого результата.",
                "follow_up_hint": "Отметить tried/useful.",
                "feedback_event_options": ["tried", "useful"],
                "outcome_policy": "Не считать useful без фидбека.",
                "feedback_target_id": "action-1-feedback",
            },
            {
                "id": "action-2",
                "target_ref": "action-2",
                "action_kind": "try",
                "title": "Прочитать источник",
                "effort": "30 мин",
                "scope": "skill",
                "next_step": "Выписать применимый прием.",
                "success_criterion": "Есть один прием.",
                "kill_condition": "Остановить, если источник слишком мелкий.",
                "follow_up_hint": "Отметить too_shallow/wrong_priority при необходимости.",
                "feedback_event_options": ["tried", "useful", "too_shallow"],
                "outcome_policy": "Не засчитывать без read/tried feedback.",
                "feedback_target_id": "action-2-feedback",
            },
            {
                "id": "action-3",
                "target_ref": "action-3",
                "action_kind": "experiment",
                "title": "Запустить мини-эксперимент",
                "effort": "60 мин",
                "scope": "experiment",
                "next_step": "Проверить claim на мини-задаче.",
                "success_criterion": "Есть измеримый результат.",
                "kill_condition": "Остановить, если claim не подтверждается.",
                "follow_up_hint": "Отметить applied_to_project или wrong_priority.",
                "feedback_event_options": ["tried", "useful", "applied_to_project"],
                "outcome_policy": "Эксперимент засчитывается только после outcome feedback.",
                "feedback_target_id": "action-3-feedback",
            }
        ],
        "project_diagnostic": {
            "checked_projects": ["telegram-research-agent"],
            "checked_project_count": 1,
            "confirmed_leads": [],
            "project_watch": [],
            "learning_only_implications": [{"topic": "eval", "reason": "полезно для навыка"}],
            "close_but_not_enough_signals": [
                {
                    "project": "telegram-research-agent",
                    "thread_slug": "eval-gates",
                    "thread_title": "eval-gates",
                    "rejected_terms": ["workflow"],
                    "reason": "Совпадение только по широким словам.",
                    "needed_evidence": "Нужна специфичная сущность.",
                }
            ],
            "rejected_broad_overlaps": [
                {
                    "project": "telegram-research-agent",
                    "term": "workflow",
                    "reason": "broad_overlap_suppressed",
                }
            ],
            "no_confirmed_leads_reason": "Нет специфичной связи с проектом.",
            "missing_config_suggestions": ["Добавить специфичные project keywords."],
        },
        "feedback_targets": [
            {
                "id": "action-1-feedback",
                "target_type": "action",
                "prompt": "Отметьте результат действия.",
                "event_options": ["tried", "useful"],
            },
            {
                "id": "action-2-feedback",
                "target_type": "action",
                "prompt": "Отметьте результат второго действия.",
                "event_options": ["tried", "useful", "too_shallow"],
            },
            {
                "id": "action-3-feedback",
                "target_type": "action",
                "prompt": "Отметьте результат эксперимента.",
                "event_options": ["tried", "useful", "applied_to_project"],
            },
            {
                "id": "read-1-feedback",
                "target_type": "read_queue",
                "prompt": "Отметьте первый прочитанный источник.",
                "event_options": ["read", "useful"],
            },
            {
                "id": "read-2-feedback",
                "target_type": "read_queue",
                "prompt": "Отметьте второй прочитанный источник.",
                "event_options": ["read", "useful", "wrong_priority"],
            },
            {
                "id": "missed-feedback",
                "target_type": "missed_post",
                "prompt": "Укажите пропущенный пост или отметьте, что пропусков не было.",
                "event_options": ["missed_important_post", "no_missed_posts"],
            },
            {
                "id": "trust-feedback",
                "target_type": "trust_correction",
                "prompt": "Исправьте доверие к утверждению.",
                "event_options": ["trust_too_high", "verify_first"],
            },
        ],
    }


class TestAiReportContract(unittest.TestCase):
    def test_structured_but_low_value_report_fails_contract(self):
        metadata = {
            "report_contract": {
                "version": REPORT_CONTRACT_VERSION,
                "html_language": "ru",
            },
            "decision_cards": [],
            "claim_cards": [],
            "thread_deltas": [],
            "action_cards": [],
            "project_diagnostic": {},
            "feedback_targets": [],
        }

        findings = validate_weekly_ai_report_contract(metadata, html_text=_valid_html())
        messages = "\n".join(finding.message for finding in findings)

        self.assertIn("operator decision cards", messages)
        self.assertIn("claim evidence cards", messages)
        self.assertIn("temporal thread deltas", messages)
        self.assertIn("operational action cards", messages)
        self.assertIn("project fit diagnostic", messages)
        self.assertIn("feedback targets", messages)

    def test_w28_versioned_artifact_is_offline_fixture_and_fails_new_contract(self):
        metadata = json.loads((W28_FIXTURE_ROOT / "2026-W28.visual.json").read_text(encoding="utf-8"))
        html_text = (W28_FIXTURE_ROOT / "2026-W28.visual.html").read_text(encoding="utf-8")

        findings = validate_weekly_ai_report_contract(metadata, html_text=html_text)
        messages = "\n".join(finding.message for finding in findings)

        self.assertIn("Report contract version is missing", messages)
        self.assertIn("Final HTML language contract must be Russian", messages)
        self.assertIn("Russian user-value section is missing", messages)
        self.assertIn("claim evidence cards", messages)

    def test_complete_contract_passes_without_live_database(self):
        metadata = _complete_contract_metadata()

        findings = validate_weekly_ai_report_contract(metadata, html_text=_valid_html())

        self.assertEqual(findings, [])

    def test_unverified_claim_without_weak_label_fails(self):
        metadata = _complete_contract_metadata()
        metadata["claim_cards"][0]["quote_verified"] = False
        metadata["claim_cards"][0]["verification_status"] = "quote_not_found"
        metadata["claim_cards"][0]["evidence_tier"] = "verified_single_source"
        metadata["claim_cards"][0]["decision_eligible"] = True

        findings = validate_weekly_ai_report_contract(metadata, html_text=_valid_html())
        messages = "\n".join(finding.message for finding in findings)

        self.assertIn("Unverifiable top claim must be explicitly labeled weak", messages)

    def test_apply_decision_cannot_use_unverified_weak_claim(self):
        metadata = _complete_contract_metadata()
        metadata["claim_cards"][0]["quote_verified"] = False
        metadata["claim_cards"][0]["verification_status"] = "quote_not_found"
        metadata["claim_cards"][0]["evidence_tier"] = "weak_single_source"
        metadata["claim_cards"][0]["decision_eligible"] = False
        metadata["claim_cards"][0]["caveat"] = "Слабая карточка: цитата не найдена."

        findings = validate_weekly_ai_report_contract(metadata, html_text=_valid_html())
        messages = "\n".join(finding.message for finding in findings)

        self.assertIn("Apply/study decision cards cannot rely on unverifiable claim evidence", messages)

    def test_weak_claim_requires_cautious_wording_policy(self):
        metadata = _complete_contract_metadata()
        metadata["claim_cards"][0]["quote_verified"] = False
        metadata["claim_cards"][0]["verification_status"] = "quote_not_found"
        metadata["claim_cards"][0]["evidence_tier"] = "weak_single_source"
        metadata["claim_cards"][0]["decision_eligible"] = False
        metadata["claim_cards"][0]["caveat"] = "Слабая карточка: цитата не найдена."
        metadata["claim_cards"][0]["wording_policy"] = "source_bounded"

        findings = validate_weekly_ai_report_contract(metadata, html_text=_valid_html())
        messages = "\n".join(finding.message for finding in findings)

        self.assertIn("Weak claim must use cautious wording policy", messages)

    def test_claim_cards_require_atom_ids_and_source_urls(self):
        metadata = _complete_contract_metadata()
        metadata["claim_cards"][0]["evidence_atom_ids"] = []
        metadata["claim_cards"][1]["source_urls"] = []
        metadata["claim_cards"][1]["source_count"] = 0

        findings = validate_weekly_ai_report_contract(metadata, html_text=_valid_html())
        messages = "\n".join(finding.message for finding in findings)

        self.assertIn("Claim card must cite atom IDs", messages)
        self.assertIn("Claim card must include source URLs", messages)

    def test_action_cards_require_try_experiment_and_feedback_policy(self):
        metadata = _complete_contract_metadata()
        metadata["action_cards"] = [
            {
                "id": "action-1",
                "target_ref": "action-1",
                "action_kind": "try",
                "title": "Only one action",
                "effort": "30 мин",
                "scope": "skill",
                "next_step": "Try it.",
                "success_criterion": "Done.",
                "kill_condition": "Stop.",
                "feedback_target_id": "action-1-feedback",
            }
        ]

        findings = validate_weekly_ai_report_contract(metadata, html_text=_valid_html())
        messages = "\n".join(finding.message for finding in findings)

        self.assertIn("at least three operational action cards", messages)

    def test_thread_delta_builder_explains_five_temporal_changes(self):
        threads = []
        for index in range(1, 6):
            atoms = []
            if index < 5:
                atoms.append(
                    {
                        "id": index * 10,
                        "claim": f"Предыдущее состояние темы {index}",
                        "confidence": 0.55,
                        "last_seen_at": "2026-06-30T08:00:00Z",
                        "source_urls": [f"https://t.me/source/{index * 10}"],
                        "entities": [f"Entity {index}"],
                    }
                )
            atoms.append(
                {
                    "id": index * 10 + 1,
                    "claim": f"Новое свидетельство недели {index}",
                    "confidence": 0.74,
                    "last_seen_at": "2026-07-06T08:00:00Z",
                    "source_urls": [f"https://t.me/source/{index * 10 + 1}"],
                    "entities": [f"Entity {index}"],
                }
            )
            threads.append(
                {
                    "id": index,
                    "slug": f"thread-{index}",
                    "title": f"Тема {index}",
                    "summary": f"Сводка темы {index}",
                    "status": "active",
                    "first_seen_at": "2026-06-30T08:00:00Z" if index < 5 else "2026-07-06T08:00:00Z",
                    "last_seen_at": "2026-07-06T08:00:00Z",
                    "momentum_7d": 0.4,
                    "momentum_30d": 0.3,
                    "atom_count": len(atoms),
                    "source_channel_count": 1,
                    "key_entities": [f"Entity {index}"],
                    "current_claims": [f"Обновленная интерпретация темы {index}"],
                    "changed_this_week": True,
                    "atoms": atoms,
                }
            )
        contract = build_weekly_ai_report_contract(
            {
                "week_label": "2026-W28",
                "week_start": "2026-07-06T00:00:00Z",
                "week_end": "2026-07-13T00:00:00Z",
                "threads": threads,
                "frontier_analysis": {
                    "actions": [{"title": "Проверить дельту", "next_step": "Сравнить атомы."}],
                    "study_now": [{"topic": "Temporal deltas", "reason": "Нужны для интерпретации."}],
                },
                "feedback_context": {"event_count": 0},
            },
            project_links=[],
            projects=[{"name": "telegram-research-agent"}],
        )

        deltas = contract["thread_deltas"]

        self.assertEqual(len(deltas), 5)
        self.assertTrue(all(delta["this_week_evidence"] for delta in deltas))
        self.assertTrue(all(delta["why_this_is_one_thread"] for delta in deltas))
        self.assertTrue(all(delta["merge_split_audit_status"] for delta in deltas))
        self.assertIn("insufficient_history", {delta["state"] for delta in deltas})

    def test_project_diagnostic_explains_zero_leads_without_broad_match_noise(self):
        contract = build_weekly_ai_report_contract(
            {
                "week_label": "2026-W28",
                "week_start": "2026-07-06T00:00:00Z",
                "week_end": "2026-07-13T00:00:00Z",
                "threads": [
                    {
                        "id": 1,
                        "slug": "generic-workflow",
                        "title": "AI workflow evidence",
                        "summary": "Generic AI workflow evidence without a project-specific entity.",
                        "status": "active",
                        "first_seen_at": "2026-07-06T08:00:00Z",
                        "last_seen_at": "2026-07-06T08:00:00Z",
                        "momentum_7d": 0.2,
                        "momentum_30d": 0.2,
                        "atom_count": 1,
                        "source_channel_count": 1,
                        "key_entities": ["AI"],
                        "current_claims": ["Teams discuss workflow evidence."],
                        "changed_this_week": True,
                        "atoms": [
                            {
                                "id": 1,
                                "claim": "Generic workflow evidence matters.",
                                "confidence": 0.7,
                                "last_seen_at": "2026-07-06T08:00:00Z",
                                "source_urls": ["https://t.me/source/1"],
                                "entities": ["AI"],
                                "practices": ["workflow", "evidence"],
                            }
                        ],
                    }
                ],
                "frontier_analysis": {
                    "actions": [{"title": "Проверить", "next_step": "Проверить."}],
                    "study_now": [{"topic": "workflow", "reason": "Учебно полезно."}],
                },
                "feedback_context": {"event_count": 0},
            },
            project_links=[],
            projects=[{"name": "workflow-to-agent-studio", "keywords": ["AI", "workflow", "evidence", "tool"]}],
        )

        diagnostic = contract["project_diagnostic"]

        self.assertEqual(diagnostic["confirmed_leads"], [])
        self.assertEqual(diagnostic["project_watch"], [])
        self.assertEqual(diagnostic["implementation_suggestions"], [])
        self.assertTrue(diagnostic["close_but_not_enough_signals"])
        self.assertTrue(diagnostic["rejected_broad_overlaps"])
        self.assertTrue(diagnostic["missing_config_suggestions"])
        self.assertIn("Нет подтвержденных проектных лидов", diagnostic["no_confirmed_leads_reason"])

    def test_feedback_changes_are_exposed_in_report_contract(self):
        contract = build_weekly_ai_report_contract(
            {
                "week_label": "2026-W28",
                "week_start": "2026-07-06T00:00:00Z",
                "week_end": "2026-07-13T00:00:00Z",
                "threads": [],
                "frontier_analysis": {},
                "feedback_context": {
                    "event_count": 2,
                    "counts_by_feedback": {"useful": 1, "wrong_priority": 1},
                    "downranked_target_refs": ["action:agent-frameworks"],
                    "promoted_target_refs": ["knowledge_atom:2"],
                    "feedback_eval_examples": [{"example_type": "priority_calibration"}],
                    "feedback_changes": {
                        "status": "feedback_used",
                        "summary": "Changed by confirmed feedback.",
                        "items": ["Downranked noisy action.", "Promoted useful atom."],
                    },
                },
            },
            project_links=[],
            projects=[],
        )

        used = contract["report_contract"]["feedback_used_summary"]

        self.assertEqual(used["summary"], "Changed by confirmed feedback.")
        self.assertIn("action:agent-frameworks", used["downranked"])
        self.assertIn("knowledge_atom:2", used["promoted"])


if __name__ == "__main__":
    unittest.main()

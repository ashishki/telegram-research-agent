import json
import unittest
from pathlib import Path

from output.ai_report_contract import (
    INTELLIGENCE_CONTRACT_VERSION,
    RADAR_INTELLIGENCE_CONTRACT_VERSION,
    REPORT_CONTRACT_VERSION,
    build_canonical_intelligence_contract,
    build_weekly_ai_report_contract,
    validate_canonical_intelligence_contract,
    validate_weekly_ai_report_contract,
)
from output.learning_layer import LEARNING_STAGES, PROJECT_LEARNING_PROJECTION_VERSION


PROJECT_ROOT = Path(__file__).resolve().parents[1]
W28_FIXTURE_ROOT = PROJECT_ROOT / "docs" / "artifacts" / "ai-decision-intelligence-2026-W28"
CONTRACT_FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "intelligence_contract"


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
        "project_learning_projection": _complete_project_learning_projection(),
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
        "intelligence_contract": _complete_intelligence_contract(),
    }


def _complete_project_learning_projection() -> dict:
    return {
        "schema_version": PROJECT_LEARNING_PROJECTION_VERSION,
        "week_label": "2026-W28",
        "source_policy": {
            "confirmed_project_implication": "requires project-specific evidence and source refs",
            "broad_overlap": "rejected_not_confirmed",
            "market_business_context": "context_only",
            "no_feedback_semantics": "unknown",
            "passive_reading": "not_mastery",
        },
        "project_intelligence": {
            "external_signals": [
                {
                    "id": "external-signal:1",
                    "title": "Eval gates are becoming release infrastructure.",
                    "thread_slug": "eval-gates",
                    "atom_type": "engineering_practice",
                    "context_policy": "source_backed",
                    "source_atom_ids": [1],
                    "source_refs": ["https://t.me/source/1"],
                    "evidence_state": "source_ref_available",
                }
            ],
            "confirmed_implications": [],
            "weak_watches": [],
            "rejected_overlaps": [
                {
                    "project": "telegram-research-agent",
                    "term": "workflow",
                    "reason": "broad_overlap_suppressed",
                    "confirmation_state": "rejected",
                }
            ],
            "tiny_pr_ideas": [],
            "stale_decisions": [],
            "research_debt": [{"debt_type": "project_config_gap", "description": "Добавить специфичные project keywords."}],
            "repeated_themes_without_action": [],
            "no_confirmed_leads_reason": "Нет специфичной связи с проектом.",
        },
        "learning_intelligence": {
            "allowed_stages": list(LEARNING_STAGES),
            "stage_definitions": {stage: f"{stage} definition" for stage in LEARNING_STAGES},
            "stage_counts": {stage: (1 if stage == "read" else 0) for stage in LEARNING_STAGES},
            "objectives": [
                {
                    "id": "learning-objective:atom:1",
                    "topic": "Eval gates are becoming release infrastructure.",
                    "stage": "read",
                    "target_stage": "implemented",
                    "stage_evidence": "source atom with source refs",
                    "source_atom_ids": [1],
                    "source_refs": ["https://t.me/source/1"],
                    "feedback_state": "unknown",
                    "mastery_claim": "not_claimed",
                }
            ],
            "experiments": [],
            "outcomes": [],
            "feedback_state": "unknown",
            "mastery_policy": "read is source exposure, not mastery",
        },
    }


def _complete_intelligence_contract() -> dict:
    source_observations = [
        {
            "id": f"source_observation:url:source-{index}",
            "source_type": "telegram_link",
            "url": f"https://t.me/source/{index}",
            "observed_at": "2026-07-06T08:00:00Z",
            "raw_excerpt": f"Утверждение {index}",
            "metadata": {"atom_ids": [index]},
            "collection_method": "sidecar_projection",
            "ingestion_provenance": {"derived_from": "fixture"},
        }
        for index in range(1, 4)
    ]
    evidence_items = [
        {
            "id": f"evidence_item:claim-{index}:1",
            "claim_id": f"claim-{index}",
            "source_observation_id": f"source_observation:url:source-{index}",
            "source_observation_ref": f"source_observation:url:source-{index}",
            "atom_ids": [index],
            "quote": f"Утверждение {index}",
            "verified_excerpt": f"Утверждение {index}",
            "evidence_role": "practice_report",
            "evidence_tier": "verified_single_source",
            "independence_key": "telegram:source",
            "independence_keys": ["telegram:source"],
            "verification_status": "verified",
            "quote_verified": True,
            "date_relevance": "active",
            "scope": "practice",
            "expiry_hint": "Проверить заново через месяц.",
            "polarity": "supporting",
            "context_only": False,
            "decision_grade": True,
            "radar_gate_eligible": False,
        }
        for index in range(1, 4)
    ]
    claims = [
        {
            "id": f"claim-{index}",
            "statement": f"Утверждение {index}",
            "scope": "practice",
            "time_horizon": "medium_to_long",
            "supporting_evidence_item_ids": [f"evidence_item:claim-{index}:1"],
            "contradicting_evidence_item_ids": [],
            "source_observation_ids": [f"source_observation:url:source-{index}"],
            "source_independence": {"count": 1, "keys": ["telegram:source"]},
            "confidence_band": "medium",
            "uncertainty_reasons": ["Цитата проверена, но источник один."],
            "verification_state": "verified",
            "decision_grade": True,
            "insufficient_evidence": False,
            "wording_policy": "source_bounded",
            "next_verification_step": "Сверить источник и найти подтверждение.",
            "atom_ids": [index],
        }
        for index in range(1, 4)
    ]
    return {
        "contract_version": INTELLIGENCE_CONTRACT_VERSION,
        "schema_version": INTELLIGENCE_CONTRACT_VERSION,
        "week_label": "2026-W28",
        "projection_boundaries": {
            "canonical_state": "SQLite rows and versioned JSON sidecars",
            "rendered_surfaces": ["html"],
            "llm_prose": "derived_interpretation_not_source_of_truth",
            "market_business_context": "context_only",
            "no_feedback_semantics": "unknown",
        },
        "source_observations": source_observations,
        "evidence_items": evidence_items,
        "claims": claims,
        "knowledge_atoms": [
            {
                "id": f"knowledge_atom:{index}",
                "atom_id": index,
                "claim": f"Утверждение {index}",
                "summary": f"Утверждение {index}",
                "atom_type": "engineering_practice",
                "relation": "supports",
                "why_it_matters": "Нужно для проверки контракта.",
                "first_seen_at": "2026-07-06T08:00:00Z",
                "last_seen_at": "2026-07-06T08:00:00Z",
                "staleness_status": "active",
                "claim_ids": [f"claim-{index}"],
                "evidence_item_ids": [f"evidence_item:claim-{index}:1"],
                "source_urls": [f"https://t.me/source/{index}"],
            }
            for index in range(1, 4)
        ],
        "idea_threads": [
            {
                "id": "idea_thread:eval-gates",
                "thread_slug": "eval-gates",
                "title": "eval-gates",
                "status": "active",
                "atom_ids": [1],
                "claim_ids": ["claim-1"],
                "evidence_item_ids": ["evidence_item:claim-1:1"],
                "previous_state": "Раньше это было практикой отдельных задач.",
                "current_state": "Теперь это релизная дисциплина.",
                "delta_basis": "new_evidence",
                "new_evidence_atom_ids": [1],
                "momentum_vs_evidence": {
                    "momentum_7d": 0.4,
                    "momentum_30d": 0.3,
                    "evidence_growth": True,
                    "momentum_is_not_evidence": True,
                },
                "contradictions": [],
                "merge_split_audit_status": "ok",
            }
        ],
        "decisions": [
            {
                "id": "decision-1",
                "verdict": "apply",
                "title": "Проверить eval-гейт",
                "claim_ids": ["claim-1"],
                "evidence_atom_ids": [1],
                "source_policy": "decision_grade_claims_required_for_apply_or_study",
                "evidence_state": "decision_grade",
                "next_action": "Запустить маленькую проверку.",
                "success_criterion": "Плохое изменение заблокировано.",
            }
        ],
        "experiments": [],
        "outcomes": [],
        "radar_exchange": {
            "contract_version": RADAR_INTELLIGENCE_CONTRACT_VERSION,
            "status": "unbound_legacy",
            "reader_state": "unbound_legacy",
            "reader_decision": "unavailable",
            "selected_candidate": "",
            "recommendation": "unavailable",
            "diagnostic_legacy_recommendation": "investigate",
            "matched_external_evidence_count": 0,
            "context_only_evidence_count": 1,
            "context_only_can_satisfy_gate": False,
            "missing_evidence": ["Need matched external evidence."],
        },
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

    def test_valid_canonical_contract_fixture_passes(self):
        payload = json.loads((CONTRACT_FIXTURE_ROOT / "valid_canonical_sidecar.json").read_text(encoding="utf-8"))

        findings = validate_canonical_intelligence_contract(payload["intelligence_contract"])

        self.assertEqual(findings, [])

    def test_unsupported_decision_grade_fixture_fails(self):
        payload = json.loads((CONTRACT_FIXTURE_ROOT / "unsupported_decision_grade_claim.json").read_text(encoding="utf-8"))

        findings = validate_canonical_intelligence_contract(payload["intelligence_contract"])
        messages = "\n".join(finding.message for finding in findings)

        self.assertIn("Decision-grade claim must cite supporting evidence", messages)
        self.assertIn("Decision-grade claim must cite source observations", messages)

    def test_context_only_evidence_cannot_satisfy_radar_gate(self):
        payload = json.loads((CONTRACT_FIXTURE_ROOT / "context_only_radar_gate.json").read_text(encoding="utf-8"))

        findings = validate_canonical_intelligence_contract(payload["intelligence_contract"])
        messages = "\n".join(finding.message for finding in findings)

        self.assertIn("Context-only evidence cannot be decision-grade", messages)
        self.assertIn("Radar context-only records must not satisfy demand evidence gates", messages)

    def test_non_available_canonical_radar_exchange_cannot_claim_permission(self):
        contract = _complete_intelligence_contract()
        contract["radar_exchange"].update(
            {
                "reader_state": "unbound_legacy",
                "reader_decision": "build_allowed",
                "selected_candidate": "Forged candidate",
                "recommendation": "build",
                "matched_external_evidence_count": 2,
            }
        )

        findings = validate_canonical_intelligence_contract(contract)

        self.assertTrue(
            any(
                finding.message
                == "Non-available Radar exchange cannot expose permission authority"
                for finding in findings
            )
        )

    def test_canonical_radar_permission_requires_matching_proof_count(self):
        contract = _complete_intelligence_contract()
        contract["radar_exchange"].update(
            {
                "status": "selected",
                "reader_state": "available",
                "reader_decision": "build_allowed",
                "selected_candidate": "Candidate",
                "recommendation": "build",
                "matched_external_evidence_count": 0,
            }
        )

        findings = validate_canonical_intelligence_contract(contract)

        self.assertTrue(
            any(
                "two matched proof sources" in finding.message
                for finding in findings
            )
        )

    def test_canonical_radar_exchange_ignores_forged_or_incomplete_gate_claims(self):
        strict_reader = {
            "schema_version": "mvp_radar_reader.v1",
            "reader_state": "available",
            "status": "selected",
            "selected_candidate": "Bound candidate",
            "recommendation": "focused_experiment",
            "matched_external_evidence": [],
            "matched_external_proof": [
                {
                    "evidence_ref": "context-forgery",
                    "source_type": "market_context",
                    "supports_gate": True,
                    "decision_grade": True,
                    "context_only": True,
                    "build_ready_evidence": True,
                    "gate_eligible": True,
                },
                {
                    "evidence_ref": "missing-grade-forgery",
                    "source_type": "external_research",
                    "supports_gate": True,
                    "context_only": False,
                    "build_ready_evidence": True,
                    "gate_eligible": True,
                },
                {
                    "evidence_ref": "verified-proof",
                    "evidence_kind": "search_demand",
                    "source_type": "serp",
                    "supports_gate": True,
                    "decision_grade": True,
                    "context_only": False,
                    "build_ready_evidence": True,
                    "negative_signal": False,
                    "gate_eligible": True,
                },
            ],
            "unmatched_context": [
                {
                    "context_ref": "market-context",
                    "context_only": True,
                    "supports_gate": False,
                    "decision_grade": False,
                    "gate_eligible": False,
                }
            ],
            "missing_evidence": ["Need one more independent source."],
        }
        legacy_forgery = {
            "status": "selected",
            "selected_candidate": "Unbound candidate",
            "recommendation": "focused_experiment",
            "matched_external_evidence": [
                {
                    "supports_gate": True,
                    "decision_grade": True,
                    "context_only": False,
                    "gate_eligible": True,
                }
            ],
        }

        strict_contract = build_canonical_intelligence_contract(
            {"week_label": "2026-W28"},
            mvp_radar=strict_reader,
            mvp_radar_authoritative=True,
        )
        unbound_strict_contract = build_canonical_intelligence_contract(
            {"week_label": "2026-W28"},
            mvp_radar=strict_reader,
        )
        legacy_contract = build_canonical_intelligence_contract(
            {"week_label": "2026-W28"},
            mvp_radar=legacy_forgery,
        )

        strict_exchange = strict_contract["radar_exchange"]
        unbound_strict_exchange = unbound_strict_contract["radar_exchange"]
        legacy_exchange = legacy_contract["radar_exchange"]
        self.assertEqual(strict_exchange["matched_external_evidence_count"], 1)
        self.assertGreaterEqual(strict_exchange["context_only_evidence_count"], 1)
        self.assertFalse(strict_exchange["context_only_can_satisfy_gate"])
        self.assertEqual(unbound_strict_exchange["reader_state"], "unbound_legacy")
        self.assertEqual(
            unbound_strict_exchange["diagnostic_reader_state"], "available"
        )
        self.assertEqual(
            unbound_strict_exchange["matched_external_evidence_count"], 0
        )
        self.assertEqual(unbound_strict_exchange["selected_candidate"], "")
        self.assertEqual(unbound_strict_exchange["recommendation"], "unavailable")
        self.assertEqual(legacy_exchange["matched_external_evidence_count"], 0)
        self.assertFalse(legacy_exchange["context_only_can_satisfy_gate"])
        self.assertEqual(legacy_exchange["reader_state"], "unbound_legacy")
        self.assertEqual(legacy_exchange["reader_decision"], "unavailable")
        self.assertEqual(legacy_exchange["selected_candidate"], "")
        self.assertEqual(legacy_exchange["recommendation"], "unavailable")
        self.assertEqual(
            legacy_exchange["diagnostic_legacy_recommendation"],
            "focused_experiment",
        )

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
        intelligence_contract = contract["intelligence_contract"]

        self.assertEqual(len(deltas), 5)
        self.assertTrue(all(delta["this_week_evidence"] for delta in deltas))
        self.assertTrue(all(delta["why_this_is_one_thread"] for delta in deltas))
        self.assertTrue(all(delta["merge_split_audit_status"] for delta in deltas))
        self.assertIn("insufficient_history", {delta["state"] for delta in deltas})
        self.assertEqual(intelligence_contract["contract_version"], INTELLIGENCE_CONTRACT_VERSION)
        self.assertTrue(intelligence_contract["source_observations"])
        self.assertTrue(intelligence_contract["evidence_items"])
        self.assertTrue(intelligence_contract["claims"])
        self.assertIn(
            "new_evidence",
            {thread["delta_basis"] for thread in intelligence_contract["idea_threads"]},
        )

    def test_project_learning_projection_distinguishes_stages_without_reading_mastery(self):
        contract = build_weekly_ai_report_contract(
            {
                "week_label": "2026-W28",
                "week_start": "2026-07-06T00:00:00Z",
                "week_end": "2026-07-13T00:00:00Z",
                "threads": [
                    {
                        "id": 1,
                        "slug": "eval-gates",
                        "title": "Eval Gates",
                        "summary": "Eval gates before agent-written releases.",
                        "status": "active",
                        "first_seen_at": "2026-07-06T08:00:00Z",
                        "last_seen_at": "2026-07-06T08:00:00Z",
                        "momentum_7d": 0.4,
                        "momentum_30d": 0.4,
                        "atom_count": 1,
                        "source_channel_count": 1,
                        "key_entities": ["eval gates"],
                        "current_claims": ["Eval gates reduce release risk."],
                        "changed_this_week": True,
                        "atoms": [
                            {
                                "id": 1,
                                "claim": "Eval gates reduce release risk for coding agents.",
                                "summary": "A source describes eval gates before release.",
                                "confidence": 0.84,
                                "last_seen_at": "2026-07-06T08:00:00Z",
                                "source_urls": ["https://t.me/ai_lab/101"],
                                "atom_type": "engineering_practice",
                                "practices": ["eval-gated release"],
                            }
                        ],
                    }
                ],
                "frontier_analysis": {
                    "actions": [{"title": "Implement eval guard", "next_step": "Add one guard.", "success_criterion": "Guard is tested."}],
                    "study_now": [{"topic": "eval gates", "reason": "Useful skill."}],
                },
                "feedback_context": {"event_count": 0},
            },
            project_links=[],
            projects=[],
        )

        learning = contract["project_learning_projection"]["learning_intelligence"]

        self.assertEqual(set(learning["allowed_stages"]), set(LEARNING_STAGES))
        self.assertEqual(set(learning["stage_counts"]), set(LEARNING_STAGES))
        self.assertIn("read", {item["stage"] for item in learning["objectives"]})
        self.assertIn("prerequisite_gap", {item["stage"] for item in learning["objectives"]})
        self.assertTrue(
            all(item["mastery_claim"] != "claimed_from_reading_only" for item in learning["objectives"])
        )
        self.assertEqual(learning["feedback_state"], "unknown")

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

    def test_broad_only_higher_project_link_is_rejected_not_confirmed(self):
        context = {
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
                    "momentum_7d": 0.4,
                    "momentum_30d": 0.4,
                    "atom_count": 1,
                    "source_channel_count": 2,
                    "key_entities": ["AI"],
                    "current_claims": ["Teams discuss workflow evidence."],
                    "changed_this_week": True,
                    "atoms": [
                        {
                            "id": 1,
                            "claim": "Generic workflow evidence matters.",
                            "summary": "Generic source-backed workflow evidence.",
                            "confidence": 0.7,
                            "last_seen_at": "2026-07-06T08:00:00Z",
                            "source_urls": ["https://t.me/source/1", "https://t.me/source/2"],
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
        }

        contract = build_weekly_ai_report_contract(
            context,
            project_links=[
                {
                    "project": "workflow-to-agent-studio",
                    "repo": "workflow-to-agent-studio",
                    "thread_slug": "generic-workflow",
                    "thread_title": "AI workflow evidence",
                    "confidence": "higher",
                    "why": "Matches generic AI workflow evidence.",
                    "next_step": "Open a PR.",
                    "evidence_urls": ["https://t.me/source/1", "https://t.me/source/2"],
                    "source_atom_ids": [1],
                    "shared_terms": ["ai", "workflow", "evidence", "tool"],
                }
            ],
            projects=[{"name": "workflow-to-agent-studio", "keywords": ["AI", "workflow", "evidence", "tool"]}],
        )

        diagnostic = contract["project_diagnostic"]
        projection = contract["project_learning_projection"]["project_intelligence"]

        self.assertEqual(diagnostic["confirmed_leads"], [])
        self.assertEqual(diagnostic["project_watch"], [])
        self.assertEqual(diagnostic["implementation_suggestions"], [])
        self.assertEqual(projection["confirmed_implications"], [])
        self.assertTrue(projection["rejected_overlaps"])
        self.assertEqual(
            contract["intelligence_contract"]["project_implications"],
            [],
        )

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

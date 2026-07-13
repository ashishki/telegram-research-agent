from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from llm.client import LLMCompletionReceipt
from llm.router import route
from output.editorial_intelligence import (
    EDITORIAL_ARTIFACT_FILENAME,
    EditorialInputError,
    EditorialValidationError,
    _load_persisted_run_inputs,
    build_editorial_input_package,
    editorial_input_hash,
    generate_editorial_intelligence_artifact,
    synthesize_editorial_intelligence,
    validate_editorial_artifact,
    validate_editorial_model_output,
)
from output.editorial_intelligence_prompt import EDITORIAL_SCHEMA_VERSION


RUN_ID = "tra-weekly-2026-W28-editorial-test"
MODEL = route("synthesis")
PERIOD = {
    "reporting_week": "2026-W28",
    "analysis_period_start": "2026-07-06T00:00:00Z",
    "analysis_period_end": "2026-07-13T00:00:00Z",
}
RAW_ARCHIVE_SECRET = "RAW ARCHIVE SECRET MUST NOT LEAK INTO THE EDITORIAL PACKAGE"


def _atom(index: int) -> dict[str, object]:
    quote = f"Проверяемая цитата для сигнала {index}"
    return {
        "id": index,
        "atom_type": "engineering_practice",
        "relation": "supports",
        "claim": f"Проверяемый инженерный сигнал {index}",
        "summary": f"Краткое проверяемое описание сигнала {index}",
        "why_it_matters": f"Сигнал {index} помогает проверить рабочий процесс.",
        "evidence_quote": quote,
        "confidence": 0.82,
        "novelty_score": 0.71,
        "practical_utility_score": 0.91,
        "first_seen_at": "2026-07-07T08:00:00Z",
        "last_seen_at": "2026-07-10T08:00:00Z",
        "staleness_status": "active",
        "entities": [f"Signal-{index}"],
        "practices": [f"verification-{index}"],
        "source_urls": [
            f"https://t.me/source{index}a/101",
            f"https://t.me/source{index}b/202",
        ],
        "source_post_ids": [index * 10 + 1, index * 10 + 2],
        "source_posts": [
            {
                "post_id": index * 10 + 1,
                "channel_username": f"source{index}a",
                "message_url": f"https://t.me/source{index}a/101",
                "posted_at": "2026-07-09T08:00:00Z",
                "content": f"{quote}. {RAW_ARCHIVE_SECRET}",
            },
            {
                "post_id": index * 10 + 2,
                "channel_username": f"source{index}b",
                "message_url": f"https://t.me/source{index}b/202",
                "posted_at": "2026-07-10T08:00:00Z",
                "content": f"Независимое подтверждение: {quote}.",
            },
        ],
    }


def _thread(index: int) -> dict[str, object]:
    slug = f"signal-{index:02d}"
    atom = _atom(index)
    return {
        "id": index,
        "slug": slug,
        "title": f"Проверяемая тема {index}",
        "summary": f"Сводка темы {index} без доступа к сырому архиву.",
        "status": "active",
        "changed_this_week": True,
        "current_claims": [atom["claim"]],
        "superseded_claims": [],
        "contradictions": [],
        "atoms": [atom],
        "atom_count": 1,
        "source_channel_count": 2,
        "source_channels": [f"source{index}a", f"source{index}b"],
        "canonical_thread_refs": [f"canonical_thread:{slug}"],
        "momentum_7d": 0.4,
        "momentum_30d": 0.3,
        "momentum_90d": 0.2,
    }


def _context(*, thread_count: int = 4) -> dict[str, object]:
    threads = [_thread(index) for index in range(1, thread_count + 1)]
    return {
        "run_id": RUN_ID,
        "run_date": "2026-07-13",
        "generated_at": "2026-07-13T07:00:00Z",
        "week_label": PERIOD["reporting_week"],
        **PERIOD,
        "period_mode": "completed_iso_week",
        "feedback_snapshot_at": PERIOD["analysis_period_end"],
        "feedback_snapshot_usable": True,
        "threads": threads,
        "canonical_threads": [
            {
                "canonical_thread_id": f"canonical-{index:02d}",
                "canonical_thread_ref": f"canonical_thread:signal-{index:02d}",
                "stable_slug": f"signal-{index:02d}",
                "title": f"Каноническая тема {index}",
                "summary": f"Канонический тезис темы {index}.",
                "status": "active",
                "changed_this_week": True,
                "current_claims": [f"Канонический проверяемый тезис {index}"],
            }
            for index in range(1, thread_count + 1)
        ],
        "canonical_thread_snapshot": {
            "schema_version": "canonical_idea_threads.snapshot.v1",
            "as_of": PERIOD["analysis_period_end"],
            "fingerprint": "sha256:" + "a" * 64,
        },
        "reaction_effect": {
            "schema_version": "reaction_personalization.v1",
            "run_id": RUN_ID,
            "surface": "weekly_brief",
            **PERIOD,
            "snapshot_ref": f"reaction-snapshot:{RUN_ID}",
            "snapshot_status": "complete",
            "status": "no_eligible_reactions",
            "counts": {
                "personal_reaction_events_detected": 0,
                "unique_reacted_posts": 0,
                "posts_resolved": 0,
                "eligible_period_posts": 0,
                "unique_atoms_linked": 0,
                "unique_canonical_threads_linked": 0,
                "canonical_threads_boosted": 0,
                "unique_compatibility_threads_linked": 0,
                "compatibility_threads_boosted": 0,
                "selected_items_linked": 0,
                "selected_signals_influenced": 0,
                "unconsumed_reaction_events": 0,
            },
            "influenced_items": [],
            "linked_only_items": [],
            "eligible_thread_audit": [],
            "unconsumed_by_reason": {},
            "unconsumed": [],
            "ranking_policy": {
                "policy_version": "reaction-ranking.v1",
                "strength": "weak",
                "below_confirmed_feedback": True,
                "can_change_evidence_gate": False,
            },
            "reader_summary_ru": (
                "Для источников этого периода личные реакции не найдены. Это не "
                "снижало оценки тем и не трактовалось как отсутствие интереса."
            ),
        },
        "feedback_context": {
            "event_count": 3,
            "confirmed_event_count": 3,
            "confirmation_state": "confirmed_only",
            "promoted_target_refs": ["idea_thread:signal-01"],
            "downranked_target_refs": [],
            "downranked_thread_slugs": [],
            "downranked_atom_refs": [],
            "feedback_effect_traces": [
                {
                    "event_id": 101,
                    "feedback_type": "useful",
                    "target_type": "idea_thread",
                    "target_ref": "signal-01",
                    "effect": "selection_changed",
                    "provenance": {"event_id": 101},
                },
                {
                    "event_id": 102,
                    "feedback_type": "useful",
                    "target_type": "idea_thread",
                    "target_ref": "signal-02",
                    "provenance": {"event_id": 102},
                },
                {
                    "event_id": 103,
                    "feedback_type": "too_shallow",
                    "target_type": "weekly_report",
                    "target_ref": "2026-W27",
                    "provenance": {"event_id": 103},
                },
            ],
            "recent_events": [
                {"id": 101, "notes": RAW_ARCHIVE_SECRET},
            ],
        },
        "frontier_analysis": {
            "executive_brief": "Пока это только производный редакционный контекст.",
            "what_changed": [
                {
                    "title": "Изменился способ проверки",
                    "summary": "Нужна отдельная проверка первичных доказательств.",
                    "why_it_matters": "Это снижает риск неподтвержденного вывода.",
                }
            ],
            "caveats": ["Производный текст не является первичным доказательством."],
        },
        "marked_posts": [{"content": RAW_ARCHIVE_SECRET}],
        "raw_archive": [{"content": RAW_ARCHIVE_SECRET}],
    }


def _run_identity() -> dict[str, object]:
    return {
        "run_id": RUN_ID,
        "run_date": "2026-07-13",
        "generated_at": "2026-07-13T07:00:00Z",
        **PERIOD,
        "period_mode": "completed_iso_week",
        "pipeline_profile": "irx2_orchestration.v1",
        "manifest_path": f"/tmp/{RUN_ID}/manifest.json",
    }


def _radar_binding(*, run_id: str = RUN_ID) -> dict[str, object]:
    return {
        "schema_version": "radar_run_binding.v1",
        "manifest_schema_version": "weekly_run_manifest.v1",
        "manifest_run_id": run_id,
        "radar_run_id": f"{run_id}-radar",
        "run_date": "2026-07-13",
        "generated_at": "2026-07-13T07:00:00Z",
        **PERIOD,
        "week_label": PERIOD["reporting_week"],
        "period_mode": "completed_iso_week",
        "radar_contract_version": "tra-radar-intelligence-contract.v1",
        "radar_schema_version": "mvp_of_week.v1",
        "seed_export_ref": {
            "path": "radar/seeds.json",
            "sha256": "a" * 64,
        },
        "selected_candidate": {
            "candidate_id": "candidate-1",
            "title": "Проверяемый кандидат",
            "dossier_status": "investigate",
            "recommendation": "investigate",
            "missing_evidence": ["Нужно независимое подтверждение спроса."],
        },
        "status_projection": {"status": "selected"},
        "radar_json_ref": {
            "path": "radar/raw.json",
            "sha256": "b" * 64,
        },
        "created_at": "2026-07-13T07:03:00Z",
    }


def _feedback_effect(package: dict[str, object]) -> dict[str, object]:
    permissions = package["feedback_permissions"]
    assert isinstance(permissions, dict)
    result: dict[str, object] = {
        "confirmed_events_considered": permissions["confirmed_events_considered"],
        "applied_changes": [],
        "unchanged": [],
        "requires_code_or_config": [],
    }
    events = permissions["events"]
    assert isinstance(events, list)
    for event in events:
        assert isinstance(event, dict)
        classification = str(event["classification"])
        bucket = result[classification]
        assert isinstance(bucket, list)
        bucket.append(
            {
                "feedback_ref": event["feedback_ref"],
                "reader_summary_ru": event["reader_summary_ru"],
            }
        )
    return result


def _valid_model_output(
    package: dict[str, object],
    *,
    signal_count: int = 3,
) -> dict[str, object]:
    candidates = package["signal_candidates"]
    assert isinstance(candidates, list)
    selected = candidates[:signal_count]
    signals: list[dict[str, object]] = []
    matrix: dict[str, list[str]] = {"act": [], "study": [], "watch": [], "ignore": []}
    decisions = ("verify_first", "watch", "ignore", "study")
    for index, candidate in enumerate(selected, start=1):
        assert isinstance(candidate, dict)
        decision = decisions[(index - 1) % len(decisions)]
        allowed = candidate["allowed_decisions"]
        assert isinstance(allowed, list)
        if decision not in allowed:
            decision = "watch"
        matrix_bucket = "study" if decision == "verify_first" else decision
        matrix[matrix_bucket].append(str(candidate["signal_id"]))
        ceiling = str(candidate["confidence_ceiling"])
        cautious = " Пока вывод требует проверки." if ceiling == "low" else ""
        reaction = candidate["reaction_effect"]
        assert isinstance(reaction, dict)
        signals.append(
            {
                "signal_id": candidate["signal_id"],
                "decision": decision,
                "title": f"Проверяемый сигнал {index}",
                "what_happened": f"Появилось проверяемое свидетельство {index}.{cautious}",
                "plain_explanation": f"Простое объяснение сигнала {index}.{cautious}",
                "what_changed": f"Изменилась наблюдаемая часть процесса {index}.{cautious}",
                "why_for_operator": f"Это помогает принять ограниченное решение {index}.{cautious}",
                "confidence": ceiling,
                "evidence_refs": list(candidate["evidence_refs"]),
                "reaction_effect": {
                    "effect": reaction["effect"],
                    "reader_reason_ru": reaction["reader_reason_ru"],
                },
                "project_implications": [],
                "next_action": {
                    "title": f"Сверить доказательство сигнала {index} с двумя источниками",
                    "acceptance_criteria": [
                        f"Для сигнала {index} записан наблюдаемый результат проверки."
                    ],
                },
                "do_not_do": f"Не расширять вывод сигнала {index} за границы его источников.",
            }
        )
    selection_policy = package["selection_policy"]
    assert isinstance(selection_policy, dict)
    thesis_ceiling = str(selection_policy["thesis_confidence_ceiling"])
    thesis_caution = (
        " Пока общий вывод требует проверки." if thesis_ceiling == "low" else ""
    )
    evidence_refs = list(selected[0]["evidence_refs"]) if selected else []
    radar = package["radar_permission"]
    assert isinstance(radar, dict)
    allowed_radar = radar["allowed_reader_decisions"]
    assert isinstance(allowed_radar, list)
    reader_decision = (
        "unavailable" if "unavailable" in allowed_radar else str(allowed_radar[0])
    )
    return {
        "schema_version": EDITORIAL_SCHEMA_VERSION,
        "run_id": package["run_id"],
        "reporting_period": copy.deepcopy(package["reporting_period"]),
        "weekly_thesis": {
            "title": "Проверяемость ограничивает безопасное применение сигналов",
            "plain_language_summary": (
                "Неделя показывает, что выводы нужно связывать с проверяемыми источниками."
                + thesis_caution
            ),
            "why_for_operator": (
                "Это не позволяет принять сильное решение по одному красивому объяснению."
                + thesis_caution
            ),
            "confidence": thesis_ceiling,
            "evidence_refs": evidence_refs,
        },
        "decision_matrix": matrix,
        "signals": signals,
        "project_actions": [],
        "feedback_effect": _feedback_effect(package),
        "mvp_summary": {
            "radar_ref": radar["radar_ref"],
            "reader_decision": reader_decision,
            "why": radar["why"],
            "what_would_change_it": radar["what_would_change_it"],
        },
        "visual_specs": [],
        "feedback_targets": [],
    }


def _receipt(text: str, *, model: str = MODEL) -> LLMCompletionReceipt:
    return LLMCompletionReceipt(
        text=text,
        model=model,
        input_tokens=321,
        output_tokens=123,
        estimated_cost_usd=0.01234567,
        duration_ms=87,
        attempts=1,
        usage_recorded=True,
    )


def _package_from_prompt(prompt: str) -> dict[str, object]:
    return json.loads(prompt.split("INPUT_PACKAGE_JSON:\n", 1)[1])


class EditorialIntelligenceTests(unittest.TestCase):
    def _package(
        self,
        *,
        context: dict[str, object] | None = None,
        radar_binding: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return build_editorial_input_package(
            context or _context(),
            run_identity=_run_identity(),
            radar_binding=(
                radar_binding if radar_binding is not None else _radar_binding()
            ),
            feedback_snapshot_count=3,
        )

    def assert_validation_error(
        self,
        payload: dict[str, object],
        package: dict[str, object],
        message: str,
    ) -> None:
        with self.assertRaises(EditorialValidationError) as caught:
            validate_editorial_model_output(payload, input_package=package)
        self.assertIn(message, "\n".join(caught.exception.errors))

    def test_input_is_bounded_omits_raw_content_and_preserves_eligible_order(
        self,
    ) -> None:
        context = _context(thread_count=10)
        before = copy.deepcopy(context)

        package = self._package(context=context)

        candidates = package["signal_candidates"]
        evidence = package["evidence_catalog"]
        self.assertIsInstance(candidates, list)
        self.assertIsInstance(evidence, list)
        self.assertLessEqual(len(candidates), 8)
        self.assertLessEqual(len(evidence), 24)
        self.assertEqual(
            [candidate["signal_id"] for candidate in candidates],
            [f"signal:signal-{index:02d}" for index in range(1, 6)],
        )
        serialized = json.dumps(package, ensure_ascii=False, sort_keys=True)
        self.assertNotIn(RAW_ARCHIVE_SECRET, serialized)
        self.assertNotIn("source_posts", serialized)
        self.assertNotIn("raw_archive", serialized)
        self.assertEqual(context, before)

    def test_input_builder_does_not_mutate_context_identity_radar_or_permissions(
        self,
    ) -> None:
        context = _context()
        identity = _run_identity()
        radar = _radar_binding()
        preliminary = build_editorial_input_package(
            context,
            run_identity=identity,
            radar_binding=radar,
            feedback_snapshot_count=3,
        )
        candidate = preliminary["signal_candidates"][0]
        permissions = [
            {
                "project_action_ref": "project-action:telegram-research-agent:verify-signal",
                "signal_id": candidate["signal_id"],
                "project": "telegram-research-agent",
                "permission": "allowed",
                "evidence_refs": list(candidate["evidence_refs"]),
            }
        ]
        originals = tuple(
            copy.deepcopy(value) for value in (context, identity, radar, permissions)
        )

        package = build_editorial_input_package(
            context,
            run_identity=identity,
            radar_binding=radar,
            project_permissions=permissions,
            feedback_snapshot_count=3,
        )

        self.assertEqual((context, identity, radar, permissions), originals)
        self.assertEqual(
            package["project_permissions"][0]["project_action_ref"],
            permissions[0]["project_action_ref"],
        )

    def test_run_identity_and_model_run_mismatches_fail_closed(self) -> None:
        identity = _run_identity()
        identity["analysis_period_end"] = "2026-07-14T00:00:00Z"
        with self.assertRaisesRegex(
            EditorialInputError, "analysis_period_end mismatch"
        ):
            build_editorial_input_package(
                _context(),
                run_identity=identity,
                feedback_snapshot_count=3,
            )

        context = _context()
        context["run_id"] = "foreign-run"
        with self.assertRaisesRegex(EditorialInputError, "context.run_id mismatch"):
            build_editorial_input_package(
                context,
                run_identity=_run_identity(),
                feedback_snapshot_count=3,
            )

        package = self._package()
        payload = _valid_model_output(package)
        payload["run_id"] = "foreign-run"
        self.assert_validation_error(payload, package, "run_id mismatch")

    def test_cross_signal_evidence_is_rejected(self) -> None:
        package = self._package()
        payload = _valid_model_output(package, signal_count=2)
        signals = payload["signals"]
        assert isinstance(signals, list)
        first, second = signals
        assert isinstance(first, dict) and isinstance(second, dict)
        first["evidence_refs"] = list(second["evidence_refs"])

        self.assert_validation_error(
            payload,
            package,
            "contains cross-signal or unknown evidence_refs",
        )

    def test_limits_enums_russian_markup_and_low_evidence_permissions_are_strict(
        self,
    ) -> None:
        package = self._package(context=_context(thread_count=5))

        too_many = _valid_model_output(package, signal_count=4)
        self.assert_validation_error(too_many, package, "signals exceeds limit 3")

        invalid_enum = _valid_model_output(package)
        invalid_signals = invalid_enum["signals"]
        assert isinstance(invalid_signals, list) and isinstance(
            invalid_signals[0], dict
        )
        invalid_signals[0]["decision"] = "ship_everything"
        self.assert_validation_error(invalid_enum, package, "decision is invalid")

        english = _valid_model_output(package)
        english_signals = english["signals"]
        assert isinstance(english_signals, list) and isinstance(
            english_signals[0], dict
        )
        english_signals[0]["title"] = "English reader narrative"
        self.assert_validation_error(
            english, package, "must contain Russian reader copy"
        )

        disguised_english = _valid_model_output(package)
        disguised_signals = disguised_english["signals"]
        assert isinstance(disguised_signals, list) and isinstance(
            disguised_signals[0], dict
        )
        disguised_signals[0]["title"] = "English narrative with а token"
        self.assert_validation_error(
            disguised_english, package, "must contain Russian reader copy"
        )

        markup = _valid_model_output(package)
        markup_signals = markup["signals"]
        assert isinstance(markup_signals, list) and isinstance(markup_signals[0], dict)
        markup_signals[0]["plain_explanation"] = "<div>Русское объяснение</div>"
        self.assert_validation_error(markup, package, "must not contain HTML")

        image_markup = _valid_model_output(package)
        image_signals = image_markup["signals"]
        assert isinstance(image_signals, list) and isinstance(image_signals[0], dict)
        image_signals[0]["plain_explanation"] = (
            'Русское объяснение <img src="x" alt="схема">'
        )
        self.assert_validation_error(image_markup, package, "must not contain HTML")

        low_package = copy.deepcopy(package)
        low_candidates = low_package["signal_candidates"]
        low_policy = low_package["selection_policy"]
        assert isinstance(low_candidates, list) and isinstance(low_candidates[0], dict)
        assert isinstance(low_policy, dict)
        low_candidates[0]["confidence_ceiling"] = "low"
        low_candidates[0]["allowed_decisions"] = [
            "study",
            "watch",
            "ignore",
            "verify_first",
        ]
        low_policy["thesis_confidence_ceiling"] = "low"
        escalation = _valid_model_output(low_package, signal_count=1)
        escalation_signals = escalation["signals"]
        assert isinstance(escalation_signals, list) and isinstance(
            escalation_signals[0], dict
        )
        escalation_signals[0]["decision"] = "act"
        escalation_signals[0]["confidence"] = "high"
        escalation["decision_matrix"] = {
            "act": [escalation_signals[0]["signal_id"]],
            "study": [],
            "watch": [],
            "ignore": [],
        }
        with self.assertRaises(EditorialValidationError) as caught:
            validate_editorial_model_output(escalation, input_package=low_package)
        errors = "\n".join(caught.exception.errors)
        self.assertIn("decision exceeds deterministic permission", errors)
        self.assertIn("confidence exceeds deterministic evidence ceiling", errors)

    def test_verify_first_belongs_to_study_matrix_bucket(self) -> None:
        package = self._package()
        valid = _valid_model_output(package, signal_count=1)
        validated = validate_editorial_model_output(valid, input_package=package)
        self.assertEqual(validated["signals"][0]["decision"], "verify_first")
        self.assertEqual(
            validated["decision_matrix"],
            {
                "act": [],
                "study": [validated["signals"][0]["signal_id"]],
                "watch": [],
                "ignore": [],
            },
        )

        wrong_bucket = copy.deepcopy(valid)
        signal_id = wrong_bucket["signals"][0]["signal_id"]
        wrong_bucket["decision_matrix"] = {
            "act": [],
            "study": [],
            "watch": [signal_id],
            "ignore": [],
        }
        self.assert_validation_error(
            wrong_bucket,
            package,
            "decision_matrix bucket mismatch",
        )

    def test_reaction_effect_must_match_exact_deterministic_projection(self) -> None:
        package = self._package()
        candidates = package["signal_candidates"]
        assert isinstance(candidates, list) and isinstance(candidates[0], dict)
        self.assertEqual(candidates[0]["reaction_effect"]["effect"], "none")

        payload = _valid_model_output(package, signal_count=1)
        signal = payload["signals"][0]
        assert isinstance(signal, dict) and isinstance(signal["reaction_effect"], dict)
        signal["reaction_effect"]["reader_reason_ru"] = (
            "Модель попыталась иначе объяснить отсутствие реакции."
        )
        self.assert_validation_error(
            payload,
            package,
            "reader_reason_ru must match the validated receipt",
        )

    def test_radar_wrong_run_and_build_escalation_are_rejected(self) -> None:
        wrong_run = self._package(
            radar_binding=_radar_binding(run_id="foreign-run")
        )
        self.assertTrue(wrong_run["release_policy"]["requires_partial"])
        self.assertEqual(
            wrong_run["radar_permission"]["allowed_reader_decisions"],
            ["unavailable"],
        )

        package = self._package(radar_binding=_radar_binding())
        radar = package["radar_permission"]
        assert isinstance(radar, dict)
        self.assertFalse(radar["build_allowed"])
        self.assertNotIn("build_allowed", radar["allowed_reader_decisions"])
        payload = _valid_model_output(package, signal_count=1)
        mvp = payload["mvp_summary"]
        assert isinstance(mvp, dict)
        mvp["reader_decision"] = "build_allowed"
        self.assert_validation_error(
            payload,
            package,
            "reader_decision exceeds deterministic Radar permission",
        )

    def test_feedback_loading_is_not_effect_and_classification_is_host_owned(
        self,
    ) -> None:
        package = self._package()
        permissions = package["feedback_permissions"]
        assert isinstance(permissions, dict)
        classifications = {
            event["feedback_ref"]: event["classification"]
            for event in permissions["events"]
        }
        self.assertEqual(classifications["feedback:101"], "applied_changes")
        self.assertEqual(classifications["feedback:102"], "unchanged")
        self.assertEqual(classifications["feedback:103"], "requires_code_or_config")
        self.assertTrue(permissions["loaded_is_not_applied"])

        payload = _valid_model_output(package, signal_count=1)
        effect = payload["feedback_effect"]
        assert isinstance(effect, dict)
        unchanged = effect["unchanged"]
        applied = effect["applied_changes"]
        assert isinstance(unchanged, list) and isinstance(applied, list)
        loaded_only = unchanged.pop()
        applied.append(loaded_only)
        self.assert_validation_error(
            payload,
            package,
            "is not allowed in this classification",
        )

    def test_preflight_dependencies_fail_closed_without_calling_model(self) -> None:
        context = _context()
        failed_radar = _radar_binding()
        failed_radar["status_projection"] = {"status": "failed"}
        partial_reaction = copy.deepcopy(context)
        partial_reaction["reaction_effect"]["snapshot_status"] = "partial"
        partial_reaction["reaction_effect"]["status"] = "partial"
        partial_reaction["reaction_effect"]["reader_summary_ru"] = (
            "Синхронизация реакций не завершена. Персонализация по реакциям "
            "для этого запуска не применялась."
        )
        missing_manifest = _run_identity()
        missing_manifest["manifest_path"] = ""
        missing_canonical = copy.deepcopy(context)
        missing_canonical["canonical_thread_snapshot"] = {}

        packages = (
            build_editorial_input_package(
                context,
                run_identity=_run_identity(),
                radar_binding=None,
                feedback_snapshot_count=3,
            ),
            build_editorial_input_package(
                context,
                run_identity=_run_identity(),
                radar_binding=failed_radar,
                feedback_snapshot_count=3,
            ),
            build_editorial_input_package(
                partial_reaction,
                run_identity=_run_identity(),
                radar_binding=_radar_binding(),
                feedback_snapshot_count=3,
            ),
            build_editorial_input_package(
                context,
                run_identity=missing_manifest,
                radar_binding=_radar_binding(),
                feedback_snapshot_count=3,
            ),
            build_editorial_input_package(
                missing_canonical,
                run_identity=_run_identity(),
                radar_binding=_radar_binding(),
                feedback_snapshot_count=3,
            ),
        )

        for package in packages:
            with self.subTest(
                reasons=package["release_policy"]["partial_reasons"]
            ):
                calls = 0

                def must_not_run(**_kwargs: object) -> LLMCompletionReceipt:
                    nonlocal calls
                    calls += 1
                    raise AssertionError("model must not run for partial input")

                artifact = synthesize_editorial_intelligence(
                    package,
                    model=MODEL,
                    completion=must_not_run,
                    generated_at="2026-07-13T07:05:00Z",
                )
                self.assertEqual(calls, 0)
                self.assertTrue(artifact["partial"])
                self.assertEqual(
                    artifact["fallback_reason"], "deterministic_input_partial"
                )
                self.assertTrue(
                    artifact["generation_receipt"]["validation_errors"]
                )

    def test_valid_no_candidate_radar_is_authoritative_not_failed(self) -> None:
        binding = _radar_binding()
        binding["selected_candidate"] = None
        binding["status_projection"] = {"status": "no_candidate"}

        package = self._package(radar_binding=binding)

        self.assertFalse(package["release_policy"]["requires_partial"])
        self.assertEqual(
            package["radar_permission"]["allowed_reader_decisions"],
            ["unavailable"],
        )
        self.assertTrue(package["radar_permission"]["radar_ref"])

    def test_unresolved_source_evidence_never_becomes_a_signal(self) -> None:
        context = _context(thread_count=1)
        atom = context["threads"][0]["atoms"][0]
        atom["source_urls"] = []
        atom["source_post_ids"] = []
        atom["source_posts"] = []

        package = self._package(context=context)

        self.assertEqual(package["evidence_catalog"], [])
        self.assertEqual(package["signal_candidates"], [])

    def test_zero_change_is_valid_but_changed_candidate_requires_signal(self) -> None:
        context = _context(thread_count=2)
        for thread in context["threads"]:
            thread["changed_this_week"] = False
        for thread in context["canonical_threads"]:
            thread["changed_this_week"] = False
        package = self._package(context=context)
        zero_change = _valid_model_output(package, signal_count=0)
        zero_change["weekly_thesis"] = copy.deepcopy(
            package["zero_change_thesis"]
        )

        validated = validate_editorial_model_output(
            zero_change,
            input_package=package,
        )
        self.assertEqual(validated["signals"], [])

        changed_package = self._package(context=_context(thread_count=1))
        changed_empty = _valid_model_output(changed_package, signal_count=0)
        changed_thesis = changed_empty["weekly_thesis"]
        changed_thesis["confidence"] = "low"
        changed_thesis["evidence_refs"] = []
        changed_thesis["plain_language_summary"] += " Пока вывод требует проверки."
        changed_thesis["why_for_operator"] += " Пока вывод требует проверки."
        self.assert_validation_error(
            changed_empty,
            changed_package,
            "changed eligible candidates require at least one signal",
        )

    def test_canonical_collapse_happens_before_cap_and_owns_semantics(self) -> None:
        context = _context(thread_count=3)
        for thread in context["threads"][:2]:
            thread["canonical_thread_refs"] = ["canonical_thread:signal-01"]

        with patch(
            "output.editorial_intelligence.MAX_SIGNAL_CANDIDATES",
            2,
        ):
            package = self._package(context=context)
        candidates = package["signal_candidates"]

        self.assertEqual(
            [candidate["signal_id"] for candidate in candidates],
            ["signal:signal-01", "signal:signal-03"],
        )
        self.assertEqual(candidates[0]["title"], "Каноническая тема 1")
        self.assertEqual(len(candidates[0]["source_thread_refs"]), 2)

    def test_confidence_requires_grade_and_independence_on_same_claim(self) -> None:
        context = _context(thread_count=2)
        first_atom = context["threads"][0]["atoms"][0]
        first_atom["source_urls"] = [first_atom["source_urls"][0]]
        first_atom["source_post_ids"] = [first_atom["source_post_ids"][0]]
        first_atom["source_posts"] = [first_atom["source_posts"][0]]
        second_atom = context["threads"][1]["atoms"][0]
        second_atom["evidence_quote"] = ""
        context["threads"][1]["canonical_thread_refs"] = [
            "canonical_thread:signal-01"
        ]

        package = self._package(context=context)

        self.assertEqual(len(package["signal_candidates"]), 1)
        self.assertEqual(
            package["signal_candidates"][0]["confidence_ceiling"],
            "low",
        )

    def test_feedback_corrections_cancel_applied_inference(self) -> None:
        context = _context()
        context["feedback_context"]["feedback_corrections"] = [
            {
                "event_id": 104,
                "feedback_type": "retraction",
                "corrects_feedback_id": 101,
                "rewrites_prior_event": False,
            }
        ]

        package = self._package(context=context)
        classifications = {
            event["feedback_ref"]: event["classification"]
            for event in package["feedback_permissions"]["events"]
        }

        self.assertEqual(classifications["feedback:101"], "unchanged")
        self.assertEqual(classifications["feedback:102"], "unchanged")

    def test_generic_duplicate_actions_and_unreturned_project_actions_fail(self) -> None:
        package = self._package()
        generic = _valid_model_output(package, signal_count=1)
        generic["signals"][0]["next_action"]["title"] = "Проверить это"
        self.assert_validation_error(generic, package, "is a generic action")

        duplicate = _valid_model_output(package, signal_count=1)
        criterion = duplicate["signals"][0]["next_action"][
            "acceptance_criteria"
        ][0]
        duplicate["signals"][0]["do_not_do"] = criterion
        self.assert_validation_error(duplicate, package, "duplicates")

        preliminary = self._package()
        second = preliminary["signal_candidates"][1]
        permission = {
            "project_action_ref": "project-action:test:second-signal",
            "signal_id": second["signal_id"],
            "project": "telegram-research-agent",
            "permission": "allowed",
            "evidence_refs": list(second["evidence_refs"]),
        }
        project_package = build_editorial_input_package(
            _context(),
            run_identity=_run_identity(),
            radar_binding=_radar_binding(),
            project_permissions=[permission],
            feedback_snapshot_count=3,
        )
        project_output = _valid_model_output(project_package, signal_count=1)
        project_output["project_actions"] = [permission["project_action_ref"]]
        self.assert_validation_error(
            project_output,
            project_package,
            "project_actions exceeds deterministic permission",
        )

    def test_valid_model_result_gets_host_receipt_cost_and_exactly_one_call(
        self,
    ) -> None:
        package = self._package(radar_binding=_radar_binding())
        model_payload = _valid_model_output(package)
        calls: list[dict[str, object]] = []

        def complete(**kwargs: object) -> LLMCompletionReceipt:
            calls.append(dict(kwargs))
            return _receipt(json.dumps(model_payload, ensure_ascii=False))

        before = copy.deepcopy(package)
        artifact = synthesize_editorial_intelligence(
            package,
            model=MODEL,
            completion=complete,
            generated_at="2026-07-13T07:05:00Z",
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["model"], MODEL)
        self.assertEqual(calls[0]["category"], "editorial_intelligence")
        self.assertEqual(artifact["generation_status"], "complete")
        self.assertFalse(artifact["partial"])
        self.assertNotIn("generation_receipt", model_payload)
        receipt = artifact["generation_receipt"]
        self.assertEqual(receipt["model"], MODEL)
        self.assertEqual(receipt["input_tokens"], 321)
        self.assertEqual(receipt["output_tokens"], 123)
        self.assertEqual(receipt["estimated_cost_usd"], 0.01234567)
        self.assertEqual(receipt["duration_ms"], 87)
        self.assertEqual(receipt["completion_mode"], "model")
        self.assertEqual(
            receipt["input_hash"],
            editorial_input_hash(package, model=MODEL),
        )
        validate_editorial_artifact(
            artifact,
            input_package=package,
            expected_model=MODEL,
            expected_input_hash=receipt["input_hash"],
        )
        self.assertEqual(package, before)

    def test_invalid_json_and_schema_create_explicit_partial_fallbacks(self) -> None:
        package = self._package()
        for text, expected_reason in (
            ("not-json", "invalid_json"),
            (json.dumps({"schema_version": "wrong"}), "validation_failed"),
            (
                '{"schema_version":"editorial_intelligence.v1",'
                '"schema_version":"editorial_intelligence.v1"}',
                "validation_failed",
            ),
        ):
            with self.subTest(reason=expected_reason):
                calls = 0

                def complete(**_kwargs: object) -> LLMCompletionReceipt:
                    nonlocal calls
                    calls += 1
                    return _receipt(text)

                artifact = synthesize_editorial_intelligence(
                    package,
                    model=MODEL,
                    completion=complete,
                    generated_at="2026-07-13T07:05:00Z",
                )
                self.assertEqual(calls, 1)
                self.assertEqual(artifact["generation_status"], "partial")
                self.assertTrue(artifact["partial"])
                self.assertEqual(artifact["fallback_reason"], expected_reason)
                self.assertEqual(artifact["signals"], [])
                self.assertEqual(
                    artifact["decision_matrix"],
                    {"act": [], "study": [], "watch": [], "ignore": []},
                )
                self.assertEqual(
                    artifact["generation_receipt"]["completion_mode"],
                    "deterministic_fallback",
                )
                validate_editorial_artifact(artifact, input_package=package)

    def test_wrong_completion_model_is_partial_and_audit_visible(self) -> None:
        package = self._package()
        payload = _valid_model_output(package)

        artifact = synthesize_editorial_intelligence(
            package,
            model=MODEL,
            completion=lambda **_kwargs: _receipt(
                json.dumps(payload, ensure_ascii=False),
                model="unexpected-provider-model",
            ),
            generated_at="2026-07-13T07:05:00Z",
        )

        self.assertTrue(artifact["partial"])
        self.assertEqual(artifact["fallback_reason"], "validation_failed")
        receipt = artifact["generation_receipt"]
        self.assertEqual(receipt["requested_model"], MODEL)
        self.assertEqual(receipt["model"], "unexpected-provider-model")
        self.assertIn(
            "completion receipt model does not match requested model",
            receipt["validation_errors"],
        )

    def test_partial_artifact_must_equal_host_projection_exactly(self) -> None:
        package = self._package()
        artifact = synthesize_editorial_intelligence(
            package,
            model=MODEL,
            completion=lambda **_kwargs: _receipt("invalid-json"),
            generated_at="2026-07-13T07:05:00Z",
        )
        malformed = copy.deepcopy(artifact)
        malformed["feedback_effect"]["unchanged"] = []

        with self.assertRaises(EditorialValidationError) as caught:
            validate_editorial_artifact(
                malformed,
                input_package=package,
                expected_model=MODEL,
                expected_input_hash=editorial_input_hash(package, model=MODEL),
            )
        self.assertIn(
            "partial fallback must exactly match deterministic projection",
            caught.exception.errors,
        )

    @patch("output.editorial_intelligence._load_persisted_run_inputs")
    def test_cache_reuses_only_complete_exact_hash_and_never_reuses_partial(
        self,
        load_persisted_inputs: object,
    ) -> None:
        load_persisted_inputs.side_effect = (  # type: ignore[attr-defined]
            lambda _identity, *, supplied_radar_binding, context: (
                supplied_radar_binding,
                3,
                [],
            )
        )
        context = _context()
        identity = _run_identity()
        calls = 0

        def complete_from_prompt(**kwargs: object) -> LLMCompletionReceipt:
            nonlocal calls
            calls += 1
            package = _package_from_prompt(str(kwargs["prompt"]))
            return _receipt(
                json.dumps(_valid_model_output(package), ensure_ascii=False)
            )

        with tempfile.TemporaryDirectory() as tmp:
            first = generate_editorial_intelligence_artifact(
                context,
                run_identity=identity,
                output_root=tmp,
                radar_binding=_radar_binding(),
                feedback_snapshot_count=3,
                model=MODEL,
                completion=complete_from_prompt,
                generated_at="2026-07-13T07:05:00Z",
            )
            second = generate_editorial_intelligence_artifact(
                context,
                run_identity=identity,
                output_root=tmp,
                radar_binding=_radar_binding(),
                feedback_snapshot_count=3,
                model=MODEL,
                completion=complete_from_prompt,
            )
            self.assertFalse(first.skipped_existing)
            self.assertTrue(second.skipped_existing)
            self.assertEqual(calls, 1)

            changed = copy.deepcopy(context)
            changed["canonical_thread_snapshot"]["fingerprint"] = "sha256:" + "c" * 64
            with self.assertRaisesRegex(EditorialInputError, "immutable"):
                generate_editorial_intelligence_artifact(
                    changed,
                    run_identity=identity,
                    output_root=tmp,
                    radar_binding=_radar_binding(),
                    feedback_snapshot_count=3,
                    model=MODEL,
                    completion=complete_from_prompt,
                )
            self.assertEqual(calls, 1)

        partial_calls = 0

        def partial_then_valid(**kwargs: object) -> LLMCompletionReceipt:
            nonlocal partial_calls
            partial_calls += 1
            if partial_calls == 1:
                return _receipt("invalid-json")
            package = _package_from_prompt(str(kwargs["prompt"]))
            return _receipt(
                json.dumps(_valid_model_output(package), ensure_ascii=False)
            )

        with tempfile.TemporaryDirectory() as tmp:
            partial = generate_editorial_intelligence_artifact(
                context,
                run_identity=identity,
                output_root=tmp,
                radar_binding=_radar_binding(),
                feedback_snapshot_count=3,
                model=MODEL,
                completion=partial_then_valid,
            )
            self.assertTrue(partial.partial)
            with self.assertRaisesRegex(EditorialInputError, "immutable"):
                generate_editorial_intelligence_artifact(
                    context,
                    run_identity=identity,
                    output_root=tmp,
                    radar_binding=_radar_binding(),
                    feedback_snapshot_count=3,
                    model=MODEL,
                    completion=partial_then_valid,
                )
            self.assertEqual(partial_calls, 1)

    @patch("output.editorial_intelligence._load_persisted_run_inputs")
    def test_persistence_is_exclusive_atomic_and_preserves_existing_run(
        self,
        load_persisted_inputs: object,
    ) -> None:
        load_persisted_inputs.side_effect = (  # type: ignore[attr-defined]
            lambda _identity, *, supplied_radar_binding, context: (
                supplied_radar_binding,
                3,
                [],
            )
        )
        context = _context()
        identity = _run_identity()
        calls = 0

        def complete_from_prompt(**kwargs: object) -> LLMCompletionReceipt:
            nonlocal calls
            calls += 1
            package = _package_from_prompt(str(kwargs["prompt"]))
            return _receipt(
                json.dumps(_valid_model_output(package), ensure_ascii=False)
            )

        with tempfile.TemporaryDirectory() as tmp:
            summary = generate_editorial_intelligence_artifact(
                context,
                run_identity=identity,
                output_root=tmp,
                radar_binding=_radar_binding(),
                feedback_snapshot_count=3,
                model=MODEL,
                completion=complete_from_prompt,
                generated_at="2026-07-13T07:05:00Z",
            )
            expected = Path(tmp) / RUN_ID / "editorial" / EDITORIAL_ARTIFACT_FILENAME
            self.assertEqual(Path(summary.path), expected)
            self.assertTrue(expected.is_file())
            persisted = json.loads(expected.read_text(encoding="utf-8"))
            package = self._package(context=context, radar_binding=_radar_binding())
            validate_editorial_artifact(
                persisted,
                input_package=package,
                expected_model=MODEL,
                expected_input_hash=editorial_input_hash(package, model=MODEL),
            )
            before = expected.read_bytes()

            new_run_id = f"{RUN_ID}-new"
            new_context = copy.deepcopy(context)
            new_context["run_id"] = new_run_id
            new_context["reaction_effect"]["run_id"] = new_run_id
            new_context["reaction_effect"]["snapshot_ref"] = (
                f"reaction-snapshot:{new_run_id}"
            )
            new_identity = {**identity, "run_id": new_run_id}
            new_radar = _radar_binding(run_id=new_run_id)
            new_path = (
                Path(tmp)
                / new_run_id
                / "editorial"
                / EDITORIAL_ARTIFACT_FILENAME
            )

            with patch(
                "output.editorial_intelligence.os.link",
                side_effect=OSError("exclusive create failed"),
            ):
                with self.assertRaisesRegex(OSError, "exclusive create failed"):
                    generate_editorial_intelligence_artifact(
                        new_context,
                        run_identity=new_identity,
                        output_root=tmp,
                        radar_binding=new_radar,
                        feedback_snapshot_count=3,
                        model=MODEL,
                        completion=complete_from_prompt,
                    )
            self.assertEqual(expected.read_bytes(), before)
            self.assertFalse(new_path.exists())
            self.assertFalse(
                any(
                    path.name.startswith(f".{EDITORIAL_ARTIFACT_FILENAME}.")
                    for directory in (expected.parent, new_path.parent)
                    if directory.exists()
                    for path in directory.iterdir()
                )
            )
            self.assertEqual(calls, 2)

    def test_arbitrary_radar_contract_schema_and_status_force_partial(self) -> None:
        cases = (
            ("contract", "radar_contract_version", "arbitrary-contract.v999"),
            ("schema", "radar_schema_version", "arbitrary-schema.v999"),
            ("status", "status_projection", {"status": "production_ready"}),
        )

        for label, field, value in cases:
            with self.subTest(label=label):
                binding = _radar_binding()
                binding[field] = value

                package = self._package(radar_binding=binding)
                policy = package["release_policy"]
                radar = package["radar_permission"]
                assert isinstance(policy, dict) and isinstance(radar, dict)

                self.assertTrue(policy["requires_partial"])
                self.assertFalse(policy["model_call_allowed"])
                self.assertTrue(
                    any(
                        str(reason).startswith("radar_")
                        for reason in policy["partial_reasons"]
                    )
                )
                self.assertEqual(radar["allowed_reader_decisions"], ["unavailable"])
                self.assertFalse(radar["build_allowed"])

    def test_production_radar_candidate_without_id_gets_stable_host_id(self) -> None:
        binding = _radar_binding()
        candidate = binding["selected_candidate"]
        assert isinstance(candidate, dict)
        candidate.pop("candidate_id")
        candidate["dossier_status"] = "focused_experiment"
        candidate["recommendation"] = "existing_project_context"

        first = self._package(radar_binding=copy.deepcopy(binding))
        second = self._package(radar_binding=copy.deepcopy(binding))
        first_radar = first["radar_permission"]
        second_radar = second["radar_permission"]
        assert isinstance(first_radar, dict) and isinstance(second_radar, dict)
        first_candidate = first_radar["selected_candidate"]
        second_candidate = second_radar["selected_candidate"]
        assert isinstance(first_candidate, dict) and isinstance(second_candidate, dict)

        self.assertFalse(first["release_policy"]["requires_partial"])
        self.assertTrue(str(first_candidate["candidate_id"]).startswith("candidate:"))
        self.assertGreater(len(str(first_candidate["candidate_id"])), len("candidate:"))
        self.assertEqual(
            first_candidate["candidate_id"],
            second_candidate["candidate_id"],
        )

    def test_padded_signal_evidence_and_matrix_refs_are_rejected(self) -> None:
        package = self._package()
        base = _valid_model_output(package, signal_count=1)
        signal = base["signals"][0]
        assert isinstance(signal, dict)
        signal_id = str(signal["signal_id"])
        evidence_ref = str(signal["evidence_refs"][0])
        matrix = base["decision_matrix"]
        assert isinstance(matrix, dict)
        populated_bucket = next(
            bucket for bucket, refs in matrix.items() if isinstance(refs, list) and refs
        )

        padded_signal = copy.deepcopy(base)
        padded_signal["signals"][0]["signal_id"] = f" {signal_id}"
        self.assert_validation_error(
            padded_signal,
            package,
            "signal_id must be an exact non-empty string",
        )

        padded_evidence = copy.deepcopy(base)
        padded_evidence["signals"][0]["evidence_refs"][0] = f"{evidence_ref} "
        self.assert_validation_error(
            padded_evidence,
            package,
            "evidence_refs[0] must not contain surrounding whitespace",
        )

        padded_matrix = copy.deepcopy(base)
        padded_matrix["decision_matrix"][populated_bucket][0] = f" {signal_id}"
        self.assert_validation_error(
            padded_matrix,
            package,
            f"decision_matrix.{populated_bucket}[0] must not contain surrounding whitespace",
        )

    def test_zero_change_requires_exact_host_thesis_projection(self) -> None:
        context = _context(thread_count=1)
        context["threads"][0]["changed_this_week"] = False
        context["canonical_threads"][0]["changed_this_week"] = False
        package = self._package(context=context)
        fabricated = _valid_model_output(package, signal_count=0)
        fabricated["weekly_thesis"] = {
            "title": "За неделю появился сильный вывод",
            "plain_language_summary": (
                "Пока модель считает, что найдено важное изменение без сигнала."
            ),
            "why_for_operator": (
                "Пока оператору предлагается принять решение без допустимого сигнала."
            ),
            "confidence": "low",
            "evidence_refs": [],
        }

        self.assert_validation_error(
            fabricated,
            package,
            "zero-change thesis must match deterministic host projection",
        )

        exact = _valid_model_output(package, signal_count=0)
        exact["weekly_thesis"] = copy.deepcopy(package["zero_change_thesis"])
        validated = validate_editorial_model_output(exact, input_package=package)
        self.assertEqual(validated["weekly_thesis"], package["zero_change_thesis"])

    def test_reader_narrative_fields_reject_non_strings(self) -> None:
        package = self._package()
        cases = (
            ("weekly_thesis.title", ("weekly_thesis", "title"), 42),
            ("signals[0].what_happened", ("signals", 0, "what_happened"), ["текст"]),
        )

        for label, path, value in cases:
            with self.subTest(field=label):
                payload = _valid_model_output(package, signal_count=1)
                if path[0] == "weekly_thesis":
                    payload["weekly_thesis"][path[1]] = value
                else:
                    payload["signals"][path[1]][path[2]] = value
                self.assert_validation_error(
                    payload,
                    package,
                    f"{label} must be a string",
                )

    def test_feedback_counts_reject_string_and_float_coercion(self) -> None:
        for invalid in ("3", 3.0):
            with self.subTest(layer="context", value=invalid):
                context = _context()
                context["feedback_context"]["confirmed_event_count"] = invalid
                with self.assertRaisesRegex(
                    EditorialInputError,
                    "feedback confirmed_event_count must be an integer",
                ):
                    build_editorial_input_package(
                        context,
                        run_identity=_run_identity(),
                        radar_binding=_radar_binding(),
                        feedback_snapshot_count=3,
                    )

            with self.subTest(layer="snapshot", value=invalid):
                with self.assertRaisesRegex(
                    EditorialInputError,
                    "feedback snapshot count must be an integer",
                ):
                    build_editorial_input_package(
                        _context(),
                        run_identity=_run_identity(),
                        radar_binding=_radar_binding(),
                        feedback_snapshot_count=invalid,
                    )

            with self.subTest(layer="model", value=invalid):
                package = self._package()
                payload = _valid_model_output(package, signal_count=1)
                payload["feedback_effect"]["confirmed_events_considered"] = invalid
                self.assert_validation_error(
                    payload,
                    package,
                    "feedback_effect.confirmed_events_considered must be an integer",
                )

    def test_explicit_weak_model_is_rejected_before_completion(self) -> None:
        package = self._package()
        weak_model = (
            "claude-haiku-4-5" if MODEL != "claude-haiku-4-5" else "claude-sonnet-4-6"
        )
        calls = 0

        def must_not_run(**_kwargs: object) -> LLMCompletionReceipt:
            nonlocal calls
            calls += 1
            raise AssertionError("weak-model request must fail before completion")

        with self.assertRaisesRegex(
            EditorialInputError,
            "must match the strong synthesis route",
        ):
            synthesize_editorial_intelligence(
                package,
                model=weak_model,
                completion=must_not_run,
            )
        self.assertEqual(calls, 0)

    def test_narrative_permission_bypasses_fail_but_host_negation_is_valid(self) -> None:
        package = self._package()

        mutation = _valid_model_output(package, signal_count=1)
        mutation["signals"][0]["what_happened"] = (
            "В production сразу выкатить новую версию проекта"
        )
        self.assert_validation_error(
            mutation,
            package,
            "invents an unpermitted persistent mutation",
        )

        readiness = _valid_model_output(package, signal_count=1)
        readiness["signals"][0]["what_changed"] = (
            "Кандидат полностью готов к выпуску MVP"
        )
        self.assert_validation_error(
            readiness,
            package,
            "invents Radar/MVP readiness",
        )

        action_bypass = _valid_model_output(package, signal_count=1)
        action_bypass["signals"][0]["next_action"] = {
            "title": "Проверить сигнал, затем открыть PR с новой реализацией",
            "acceptance_criteria": ["PR открыт и готов к merge."],
        }
        self.assert_validation_error(
            action_bypass,
            package,
            "references project/code/deployment without deterministic project permission",
        )

        for claim in (
            "Radar дал зелёный свет кандидату для реализации.",
            "MVP пора отправлять пользователям без дополнительной проверки.",
        ):
            with self.subTest(readiness_claim=claim):
                readiness_bypass = _valid_model_output(package, signal_count=1)
                readiness_bypass["signals"][0]["plain_explanation"] = claim
                self.assert_validation_error(
                    readiness_bypass,
                    package,
                    "invents Radar/MVP readiness",
                )

        zero_context = _context(thread_count=1)
        zero_context["threads"][0]["changed_this_week"] = False
        zero_context["canonical_threads"][0]["changed_this_week"] = False
        zero_package = self._package(context=zero_context)
        zero_output = _valid_model_output(zero_package, signal_count=0)
        zero_output["weekly_thesis"] = copy.deepcopy(zero_package["zero_change_thesis"])
        self.assertIn(
            "Не начинайте сборку или изменение проекта",
            zero_output["weekly_thesis"]["why_for_operator"],
        )
        validate_editorial_model_output(zero_output, input_package=zero_package)

    def test_low_evidence_requires_cautious_wording_in_every_reader_field(self) -> None:
        context = _context(thread_count=1)
        atom = context["threads"][0]["atoms"][0]
        atom["source_urls"] = atom["source_urls"][:1]
        atom["source_post_ids"] = atom["source_post_ids"][:1]
        atom["source_posts"] = atom["source_posts"][:1]
        package = self._package(context=context)
        candidate = package["signal_candidates"][0]
        assert isinstance(candidate, dict)
        self.assertEqual(candidate["confidence_ceiling"], "low")
        base = _valid_model_output(package, signal_count=1)

        signal_replacements = {
            "what_happened": "Получено свидетельство о поведении рабочего процесса.",
            "plain_explanation": "Описание связывает наблюдение с рабочим процессом.",
            "what_changed": "Наблюдаемая часть процесса изменилась за неделю.",
            "why_for_operator": "Это влияет на решение оператора по данной теме.",
        }
        for field, replacement in signal_replacements.items():
            with self.subTest(scope="signal", field=field):
                payload = copy.deepcopy(base)
                payload["signals"][0][field] = replacement
                self.assert_validation_error(
                    payload,
                    package,
                    f"signals[0].{field} low evidence requires explicit cautious wording",
                )

        thesis_replacements = {
            "plain_language_summary": (
                "Неделя связывает выводы с проверяемыми источниками."
            ),
            "why_for_operator": (
                "Связь помогает выбрать направление дальнейшей работы."
            ),
        }
        for field, replacement in thesis_replacements.items():
            with self.subTest(scope="thesis", field=field):
                payload = copy.deepcopy(base)
                payload["weekly_thesis"][field] = replacement
                self.assert_validation_error(
                    payload,
                    package,
                    f"weekly_thesis.{field} low evidence requires explicit cautious wording",
                )

    def test_canonical_critical_and_ambiguous_refs_fail_closed(self) -> None:
        with patch(
            "output.editorial_intelligence.validate_canonical_intelligence_contract",
            return_value=[SimpleNamespace(severity="critical")],
        ):
            critical = self._package(context=_context(thread_count=1))
        self.assertTrue(critical["release_policy"]["requires_partial"])
        self.assertIn(
            "canonical_intelligence_contract_invalid",
            critical["release_policy"]["partial_reasons"],
        )

        ambiguous_refs = (
            [],
            ["canonical_thread:signal-01", "canonical_thread:signal-02"],
        )
        for refs in ambiguous_refs:
            with self.subTest(canonical_refs=refs):
                context = _context(thread_count=1)
                context["threads"][0]["canonical_thread_refs"] = refs
                package = self._package(context=context)

                self.assertEqual(package["signal_candidates"], [])
                self.assertTrue(package["release_policy"]["requires_partial"])
                self.assertIn(
                    "canonical_resolution_incomplete",
                    package["release_policy"]["partial_reasons"],
                )

    def test_truncated_feedback_requires_exact_bounded_trace_count(self) -> None:
        context = _context()
        feedback = context["feedback_context"]
        assert isinstance(feedback, dict)
        feedback["confirmed_event_count"] = 21
        feedback["event_count"] = 21
        feedback["feedback_effect_traces"] = []
        package = build_editorial_input_package(
            context,
            run_identity=_run_identity(),
            radar_binding=_radar_binding(),
            feedback_snapshot_count=21,
        )
        self.assertIn(
            "feedback_trace_count_mismatch",
            package["release_policy"]["partial_reasons"],
        )

        calls = 0

        def must_not_run(**_kwargs: object) -> LLMCompletionReceipt:
            nonlocal calls
            calls += 1
            raise AssertionError("incomplete feedback trace must bypass the model")

        artifact = synthesize_editorial_intelligence(
            package,
            model=MODEL,
            completion=must_not_run,
        )
        self.assertEqual(calls, 0)
        self.assertTrue(artifact["partial"])

    def test_persisted_legacy_reaction_binding_allows_only_neutral_receipt(
        self,
    ) -> None:
        identity = _run_identity()
        manifest = {
            field: identity[field]
            for field in (
                "run_id",
                "run_date",
                "generated_at",
                "reporting_week",
                "analysis_period_start",
                "analysis_period_end",
                "period_mode",
                "pipeline_profile",
            )
        }
        manifest["stages"] = {
            "reaction_sync": {
                "status": "succeeded",
                "snapshot_ref": f"reaction-snapshot:{RUN_ID}",
                "record_counts": {"personal_reaction_events_detected": 0},
            },
            "feedback_snapshot": {
                "status": "succeeded",
                "cutoff": PERIOD["analysis_period_end"],
                "confirmed_event_count": 3,
            },
            "radar": {"status": "failed"},
        }

        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "manifest.json"
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False),
                encoding="utf-8",
            )
            bound_identity = {**identity, "manifest_path": str(manifest_path)}
            with (
                patch(
                    "output.editorial_intelligence.load_manifest",
                    return_value=manifest,
                ),
                patch(
                    "output.editorial_intelligence.load_bound_reaction_snapshot",
                    return_value=None,
                ),
            ):
                _radar, _count, neutral_reasons = _load_persisted_run_inputs(
                    bound_identity,
                    supplied_radar_binding=None,
                    context=_context(),
                )
                forged_context = _context()
                forged_context["reaction_effect"]["status"] = "effects_applied"
                forged_context["reaction_effect"]["influenced_items"] = [
                    {"effect": "selection_changed"}
                ]
                _radar, _count, forged_reasons = _load_persisted_run_inputs(
                    bound_identity,
                    supplied_radar_binding=None,
                    context=forged_context,
                )

        self.assertNotIn("reaction_receipt_integrity_invalid", neutral_reasons)
        self.assertIn("reaction_receipt_integrity_invalid", forged_reasons)

    def test_generator_persisted_input_failure_is_partial_without_model_call(self) -> None:
        calls = 0

        def must_not_run(**_kwargs: object) -> LLMCompletionReceipt:
            nonlocal calls
            calls += 1
            raise AssertionError("persisted-input failure must bypass the model")

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "output.editorial_intelligence._load_persisted_run_inputs",
                return_value=(None, None, ["persisted_input_verification_failed"]),
            ):
                summary = generate_editorial_intelligence_artifact(
                    _context(),
                    run_identity=_run_identity(),
                    output_root=tmp,
                    radar_binding=_radar_binding(),
                    feedback_snapshot_count=3,
                    model=MODEL,
                    completion=must_not_run,
                    generated_at="2026-07-13T07:05:00Z",
                )
            artifact = json.loads(Path(summary.path).read_text(encoding="utf-8"))

        self.assertEqual(calls, 0)
        self.assertTrue(summary.partial)
        self.assertTrue(artifact["partial"])
        self.assertEqual(artifact["fallback_reason"], "deterministic_input_partial")
        self.assertIn(
            "persisted_input_verification_failed",
            artifact["generation_receipt"]["validation_errors"],
        )

    def test_supplied_feedback_count_mismatch_with_manifest_is_partial(self) -> None:
        calls = 0

        def must_not_run(**_kwargs: object) -> LLMCompletionReceipt:
            nonlocal calls
            calls += 1
            raise AssertionError("feedback-count mismatch must bypass the model")

        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "output.editorial_intelligence._load_persisted_run_inputs",
                return_value=(_radar_binding(), 3, []),
            ):
                summary = generate_editorial_intelligence_artifact(
                    _context(),
                    run_identity=_run_identity(),
                    output_root=tmp,
                    radar_binding=_radar_binding(),
                    feedback_snapshot_count=2,
                    model=MODEL,
                    completion=must_not_run,
                    generated_at="2026-07-13T07:05:00Z",
                )
            artifact = json.loads(Path(summary.path).read_text(encoding="utf-8"))

        self.assertEqual(calls, 0)
        self.assertTrue(summary.partial)
        self.assertIn(
            "supplied_feedback_snapshot_count_mismatch",
            artifact["generation_receipt"]["validation_errors"],
        )


if __name__ == "__main__":
    unittest.main()

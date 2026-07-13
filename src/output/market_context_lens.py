from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from config.settings import PROJECT_ROOT, STRONG_MODEL, Settings
from llm.client import LLMClient, LLMError, LLMSchemaError
from output.ai_report_contract import INTELLIGENCE_CONTRACT_VERSION, RADAR_INTELLIGENCE_CONTRACT_VERSION
from output.market_pain_intelligence import (
    build_market_pain_pack,
    market_pack_context_seed,
    summarize_market_pain_pack,
)
from output.reporting_period import ReportingPeriod


OUTPUT_DIR = PROJECT_ROOT / "data" / "output" / "market_context_lens"
DEFAULT_BASELINE_DAYS = 84
DEFAULT_DELTA_DAYS = 7
DEFAULT_CONTEXT_LIMIT = 120
BASELINE_MAX_TOKENS = 8192
DELTA_MAX_TOKENS = 6144
BASELINE_SCHEMA_VERSION = "market_context_lens.baseline.v1"
DELTA_SCHEMA_VERSION = "market_context_lens.weekly_delta.v1"
CURRENT_SCHEMA_VERSION = "market_context_lens.current.v1"


class MarketLensLlmClient(Protocol):
    @staticmethod
    def complete_json(
        prompt: str,
        system: str = "",
        category: str = "unknown",
        model: str | None = None,
        max_tokens: int = 2048,
    ) -> dict[str, Any] | list[Any]:
        ...


@dataclass(frozen=True)
class MarketContextLensResult:
    week_label: str
    baseline_path: str
    delta_path: str
    current_path: str
    baseline_pack_path: str
    weekly_pack_path: str
    baseline_created: bool
    baseline_lens: dict[str, Any]
    weekly_delta: dict[str, Any]
    current_context: dict[str, Any]
    baseline_pack: dict[str, Any]
    weekly_pack: dict[str, Any]


def build_market_context_lens(
    settings: Settings,
    *,
    reporting_period: ReportingPeriod | None = None,
    now: datetime | None = None,
    baseline_days: int = DEFAULT_BASELINE_DAYS,
    delta_days: int = DEFAULT_DELTA_DAYS,
    output_root: Path | str | None = None,
    force_baseline: bool = False,
    llm_client: MarketLensLlmClient = LLMClient,
    model: str | None = None,
    use_llm: bool | None = None,
) -> MarketContextLensResult:
    current = (
        reporting_period.generated_at
        if reporting_period is not None
        else (now or datetime.now(timezone.utc))
    )
    current = _as_utc(current)
    analysis_period_end = (
        reporting_period.analysis_period_end
        if reporting_period is not None
        else current
    )
    week_label = (
        reporting_period.reporting_week
        if reporting_period is not None
        else _week_label(current)
    )
    root = Path(output_root) if output_root is not None else OUTPUT_DIR
    baseline_path = root / "baseline.json"
    delta_path = root / "weekly" / f"{week_label}.json"
    current_path = root / "current.json"
    baseline_pack_path = root / "source_packs" / f"{week_label}.baseline-{max(1, baseline_days)}d.json"
    weekly_pack_path = root / "source_packs" / f"{week_label}.weekly-{max(1, delta_days)}d.json"

    baseline_cutoff = _cutoff(analysis_period_end, baseline_days)
    weekly_cutoff = (
        _iso(reporting_period.analysis_period_start)
        if reporting_period is not None
        else _cutoff(current, delta_days)
    )
    period_end_iso = _iso(analysis_period_end)
    with sqlite3.connect(settings.db_path) as connection:
        connection.row_factory = sqlite3.Row
        baseline_pack = build_market_pain_pack(
            connection,
            cutoff=baseline_cutoff,
            analysis_period_end=period_end_iso,
            reporting_period=reporting_period,
            limit=DEFAULT_CONTEXT_LIMIT,
        )
        weekly_pack = build_market_pain_pack(
            connection,
            cutoff=weekly_cutoff,
            analysis_period_end=period_end_iso,
            reporting_period=reporting_period,
            limit=DEFAULT_CONTEXT_LIMIT,
        )

    _write_json(baseline_pack_path, baseline_pack)
    _write_json(weekly_pack_path, weekly_pack)

    cached_baseline = _read_json_object(baseline_path) if baseline_path.exists() else None
    baseline_created = (
        force_baseline
        or cached_baseline is None
        or not _baseline_cache_is_compatible(
            cached_baseline,
            reporting_period=reporting_period,
            source_window_start=baseline_cutoff,
            source_window_end=period_end_iso,
        )
    )
    if baseline_created:
        baseline_lens = _synthesize_baseline_lens(
            pack=baseline_pack,
            now=current,
            baseline_days=max(1, baseline_days),
            llm_client=llm_client,
            model=model,
            use_llm=use_llm,
        )
        baseline_lens = _with_source_window(
            baseline_lens,
            source_window_start=baseline_cutoff,
            source_window_end=period_end_iso,
            reporting_period=reporting_period,
        )
        _write_json(baseline_path, baseline_lens)
    else:
        assert cached_baseline is not None
        baseline_lens = cached_baseline

    weekly_delta = _synthesize_weekly_delta(
        baseline=baseline_lens,
        pack=weekly_pack,
        now=current,
        delta_days=max(1, delta_days),
        week_label=week_label,
        llm_client=llm_client,
        model=model,
        use_llm=use_llm,
    )
    weekly_delta = _with_source_window(
        weekly_delta,
        source_window_start=weekly_cutoff,
        source_window_end=period_end_iso,
        reporting_period=reporting_period,
    )
    _write_json(delta_path, weekly_delta)

    current_context = _build_current_context(
        baseline=baseline_lens,
        weekly_delta=weekly_delta,
        now=current,
        week_label=week_label,
        baseline_path=baseline_path,
        delta_path=delta_path,
        current_path=current_path,
        baseline_pack_path=baseline_pack_path,
        weekly_pack_path=weekly_pack_path,
    )
    current_context = _with_source_window(
        current_context,
        source_window_start=weekly_cutoff,
        source_window_end=period_end_iso,
        reporting_period=reporting_period,
    )
    _write_json(current_path, current_context)

    return MarketContextLensResult(
        week_label=week_label,
        baseline_path=str(baseline_path),
        delta_path=str(delta_path),
        current_path=str(current_path),
        baseline_pack_path=str(baseline_pack_path),
        weekly_pack_path=str(weekly_pack_path),
        baseline_created=baseline_created,
        baseline_lens=baseline_lens,
        weekly_delta=weekly_delta,
        current_context=current_context,
        baseline_pack=baseline_pack,
        weekly_pack=weekly_pack,
    )


def market_context_lens_seed(current_context: dict[str, Any]) -> dict[str, object] | None:
    if not current_context or current_context.get("status") != "available":
        return None
    text = str(current_context.get("context_text") or "").strip()
    if not text:
        return None
    source_urls = [
        str(url)
        for url in current_context.get("source_urls", [])
        if isinstance(url, str) and url.strip()
    ]
    return {
        "upstream_id": f"market-context-lens:{current_context.get('week_label') or 'current'}",
        "contract_version": RADAR_INTELLIGENCE_CONTRACT_VERSION,
        "intelligence_contract_version": INTELLIGENCE_CONTRACT_VERSION,
        "captured_at": str(current_context.get("generated_at") or ""),
        "title": "Context Only: Market Lens Baseline + Weekly Delta",
        "text": text,
        "snippet": _truncate(text, 260),
        "source_url": source_urls[0] if source_urls else "",
        "source_urls": source_urls,
        "channel_username": ",".join(current_context.get("channels_requested") or []),
        "post_id": "",
        "bucket": "market_context",
        "signal_score": None,
        "user_adjusted_score": None,
        "manual_tags": [],
        "project_names": [],
        "demand_surfaces": [],
        "evidence_strength": "context_only_market_analyst_pack",
        "pain_statement": "Persistent business-market lens only; use to critique candidate plausibility.",
        "target_user": "Market-aware operators validating narrow MVP bets",
        "verification_needed": [
            "do not select this context row as an MVP candidate",
            "external demand validation for any derived candidate",
            "willingness-to-pay evidence outside Telegram",
            "non-Telegram source corroboration",
        ],
        "anti_complexity_note": (
            "Context only. Use the baseline and weekly delta to rank, demote, and "
            "shape validation, not as build-ready proof."
        ),
        "private": False,
        "source_kind": "market_analyst_context",
        "radar_role": "context_only",
        "context_only": True,
        "build_ready_evidence": False,
        "market_context_lens_kind": "current",
        "market_context_baseline_path": str(current_context.get("baseline_path") or ""),
        "market_context_delta_path": str(current_context.get("weekly_delta_path") or ""),
        "market_context_current_path": str(current_context.get("current_path") or ""),
    }


def summarize_market_context_lens(current_context: dict[str, Any] | None) -> str:
    if not current_context:
        return "Market lens: not built."
    status = current_context.get("status") or "unknown"
    baseline = current_context.get("baseline") if isinstance(current_context.get("baseline"), dict) else {}
    weekly_delta = (
        current_context.get("weekly_delta")
        if isinstance(current_context.get("weekly_delta"), dict)
        else {}
    )
    if status != "available":
        return "Market lens: empty; no baseline or weekly market context available."
    return (
        "Market lens: "
        f"baseline={baseline.get('synthesis_mode') or 'unknown'} "
        f"rules={len(baseline.get('decision_rules') or [])}, "
        f"weekly_delta={weekly_delta.get('synthesis_mode') or 'unknown'} "
        f"adjustments={len(weekly_delta.get('radar_adjustments') or [])}; "
        "context only, Radar gates still apply"
    )


def _synthesize_baseline_lens(
    *,
    pack: dict[str, Any],
    now: datetime,
    baseline_days: int,
    llm_client: MarketLensLlmClient,
    model: str | None,
    use_llm: bool | None,
) -> dict[str, Any]:
    context_seed = market_pack_context_seed(pack)
    if context_seed is None:
        return _empty_baseline_lens(now=now, baseline_days=baseline_days, pack=pack)
    selected_model = _market_lens_model(model)
    if _should_use_llm(use_llm):
        try:
            payload = llm_client.complete_json(
                prompt=_baseline_prompt(pack=pack, context_text=str(context_seed["text"])),
                system=_market_lens_system(),
                category="market_lens",
                model=selected_model,
                max_tokens=BASELINE_MAX_TOKENS,
            )
            return _normalize_baseline_payload(
                payload,
                now=now,
                baseline_days=baseline_days,
                pack=pack,
                model=selected_model,
                synthesis_mode="llm",
                model_error=None,
            )
        except (LLMError, LLMSchemaError, TypeError, ValueError) as exc:
            return _fallback_baseline_lens(
                now=now,
                baseline_days=baseline_days,
                pack=pack,
                model=selected_model,
                model_error=exc.__class__.__name__,
            )
    return _fallback_baseline_lens(
        now=now,
        baseline_days=baseline_days,
        pack=pack,
        model=selected_model,
        model_error=None,
    )


def _synthesize_weekly_delta(
    *,
    baseline: dict[str, Any],
    pack: dict[str, Any],
    now: datetime,
    delta_days: int,
    week_label: str,
    llm_client: MarketLensLlmClient,
    model: str | None,
    use_llm: bool | None,
) -> dict[str, Any]:
    context_seed = market_pack_context_seed(pack)
    if context_seed is None:
        return _empty_weekly_delta(
            now=now,
            delta_days=delta_days,
            week_label=week_label,
            pack=pack,
        )
    selected_model = _market_lens_model(model)
    if _should_use_llm(use_llm):
        try:
            payload = llm_client.complete_json(
                prompt=_delta_prompt(
                    baseline=baseline,
                    pack=pack,
                    context_text=str(context_seed["text"]),
                ),
                system=_market_lens_system(),
                category="market_lens",
                model=selected_model,
                max_tokens=DELTA_MAX_TOKENS,
            )
            return _normalize_delta_payload(
                payload,
                now=now,
                delta_days=delta_days,
                week_label=week_label,
                pack=pack,
                model=selected_model,
                synthesis_mode="llm",
                model_error=None,
            )
        except (LLMError, LLMSchemaError, TypeError, ValueError) as exc:
            return _fallback_weekly_delta(
                now=now,
                delta_days=delta_days,
                week_label=week_label,
                pack=pack,
                model=selected_model,
                model_error=exc.__class__.__name__,
            )
    return _fallback_weekly_delta(
        now=now,
        delta_days=delta_days,
        week_label=week_label,
        pack=pack,
        model=selected_model,
        model_error=None,
    )


def _normalize_baseline_payload(
    payload: dict[str, Any] | list[Any],
    *,
    now: datetime,
    baseline_days: int,
    pack: dict[str, Any],
    model: str,
    synthesis_mode: str,
    model_error: str | None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TypeError("market lens baseline payload must be an object")
    return _baseline_lens(
        now=now,
        baseline_days=baseline_days,
        pack=pack,
        model=model,
        synthesis_mode=synthesis_mode,
        model_error=model_error,
        executive_lens=_text(payload.get("executive_lens"))
        or _text(payload.get("summary"))
        or _fallback_executive_lens(pack),
        decision_rules=_string_items(payload.get("decision_rules"), limit=10),
        rank_up_signals=_string_items(payload.get("rank_up_signals"), limit=8),
        rank_down_signals=_string_items(payload.get("rank_down_signals"), limit=8),
        buying_triggers=_string_items(payload.get("buying_triggers"), limit=8),
        distribution_patterns=_string_items(payload.get("distribution_patterns"), limit=8),
        anti_patterns=_string_items(payload.get("anti_patterns"), limit=8),
        validation_playbook=_string_items(payload.get("validation_playbook"), limit=8),
        open_questions=_string_items(payload.get("open_questions"), limit=8),
    )


def _normalize_delta_payload(
    payload: dict[str, Any] | list[Any],
    *,
    now: datetime,
    delta_days: int,
    week_label: str,
    pack: dict[str, Any],
    model: str,
    synthesis_mode: str,
    model_error: str | None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TypeError("market lens weekly delta payload must be an object")
    return _weekly_delta(
        now=now,
        delta_days=delta_days,
        week_label=week_label,
        pack=pack,
        model=model,
        synthesis_mode=synthesis_mode,
        model_error=model_error,
        delta_summary=_text(payload.get("delta_summary"))
        or _text(payload.get("summary"))
        or _fallback_delta_summary(pack),
        reinforced_rules=_string_items(payload.get("reinforced_rules"), limit=8),
        new_signals=_string_items(payload.get("new_signals"), limit=8),
        weakened_or_contradicted_rules=_string_items(
            payload.get("weakened_or_contradicted_rules"),
            limit=8,
        ),
        radar_adjustments=_string_items(payload.get("radar_adjustments"), limit=8),
        watch_next_week=_string_items(payload.get("watch_next_week"), limit=8),
    )


def _fallback_baseline_lens(
    *,
    now: datetime,
    baseline_days: int,
    pack: dict[str, Any],
    model: str,
    model_error: str | None,
) -> dict[str, Any]:
    context = pack.get("analyst_context") if isinstance(pack.get("analyst_context"), dict) else {}
    return _baseline_lens(
        now=now,
        baseline_days=baseline_days,
        pack=pack,
        model=model,
        synthesis_mode="deterministic_fallback",
        model_error=model_error,
        executive_lens=_fallback_executive_lens(pack),
        decision_rules=[
            "Rank up candidates with explicit buying triggers, narrow ICP, and a validation path before build.",
            "Rank down candidates that depend on broad platforms, paid ads without LTV proof, or custom infrastructure novelty.",
            "Treat Telegram business commentary as market context, not as decision-grade demand proof.",
        ],
        rank_up_signals=_observation_texts(context.get("buying_triggers"))
        + _observation_texts(context.get("proof_points"), limit=3),
        rank_down_signals=_observation_texts(context.get("what_does_not_work")),
        buying_triggers=_observation_texts(context.get("buying_triggers")),
        distribution_patterns=_observation_texts(context.get("distribution_channels")),
        anti_patterns=_observation_texts(context.get("what_does_not_work")),
        validation_playbook=[
            "Find a non-Telegram public source confirming the same pain.",
            "Test one 3-4 minute workflow demo or landing page before building a product surface.",
            "Prefer founder-led or signal-based outreach when the ICP and trigger are visible.",
        ],
        open_questions=_string_items(context.get("open_questions"), limit=8),
    )


def _fallback_weekly_delta(
    *,
    now: datetime,
    delta_days: int,
    week_label: str,
    pack: dict[str, Any],
    model: str,
    model_error: str | None,
) -> dict[str, Any]:
    context = pack.get("analyst_context") if isinstance(pack.get("analyst_context"), dict) else {}
    return _weekly_delta(
        now=now,
        delta_days=delta_days,
        week_label=week_label,
        pack=pack,
        model=model,
        synthesis_mode="deterministic_fallback",
        model_error=model_error,
        delta_summary=_fallback_delta_summary(pack),
        reinforced_rules=_observation_texts(context.get("proof_points"), limit=4),
        new_signals=_observation_texts(context.get("market_pains"), limit=5),
        weakened_or_contradicted_rules=_observation_texts(context.get("what_does_not_work"), limit=5),
        radar_adjustments=[
            "Use this weekly delta to adjust ranking and validation questions, not to satisfy evidence gates.",
            "Promote candidates only when the weekly signal reinforces the persisted baseline and has external proof.",
        ],
        watch_next_week=_string_items(context.get("open_questions"), limit=5),
    )


def _baseline_lens(
    *,
    now: datetime,
    baseline_days: int,
    pack: dict[str, Any],
    model: str,
    synthesis_mode: str,
    model_error: str | None,
    executive_lens: str,
    decision_rules: list[str],
    rank_up_signals: list[str],
    rank_down_signals: list[str],
    buying_triggers: list[str],
    distribution_patterns: list[str],
    anti_patterns: list[str],
    validation_playbook: list[str],
    open_questions: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "kind": "baseline",
        "status": "available",
        "generated_at": _iso(now),
        "lookback_days": baseline_days,
        "context_only": True,
        "build_ready_evidence": False,
        "model": model,
        "synthesis_mode": synthesis_mode,
        "model_error": model_error,
        "source_pack_summary": summarize_market_pain_pack(pack),
        "channels_requested": pack.get("channels_requested") or [],
        "curated_atom_count": int(pack.get("curated_atom_count") or 0),
        "market_thread_count": int(pack.get("market_thread_count") or 0),
        "raw_fallback_posts_scanned": int(pack.get("raw_fallback_posts_scanned") or 0),
        "executive_lens": _truncate(executive_lens, 900),
        "decision_rules": decision_rules[:10],
        "rank_up_signals": rank_up_signals[:8],
        "rank_down_signals": rank_down_signals[:8],
        "buying_triggers": buying_triggers[:8],
        "distribution_patterns": distribution_patterns[:8],
        "anti_patterns": anti_patterns[:8],
        "validation_playbook": validation_playbook[:8],
        "open_questions": open_questions[:8],
        "source_urls": _source_urls_from_pack(pack),
    }


def _weekly_delta(
    *,
    now: datetime,
    delta_days: int,
    week_label: str,
    pack: dict[str, Any],
    model: str,
    synthesis_mode: str,
    model_error: str | None,
    delta_summary: str,
    reinforced_rules: list[str],
    new_signals: list[str],
    weakened_or_contradicted_rules: list[str],
    radar_adjustments: list[str],
    watch_next_week: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": DELTA_SCHEMA_VERSION,
        "kind": "weekly_delta",
        "status": "available",
        "generated_at": _iso(now),
        "week_label": week_label,
        "delta_days": delta_days,
        "context_only": True,
        "build_ready_evidence": False,
        "model": model,
        "synthesis_mode": synthesis_mode,
        "model_error": model_error,
        "source_pack_summary": summarize_market_pain_pack(pack),
        "curated_atom_count": int(pack.get("curated_atom_count") or 0),
        "market_thread_count": int(pack.get("market_thread_count") or 0),
        "raw_fallback_posts_scanned": int(pack.get("raw_fallback_posts_scanned") or 0),
        "delta_summary": _truncate(delta_summary, 700),
        "reinforced_rules": reinforced_rules[:8],
        "new_signals": new_signals[:8],
        "weakened_or_contradicted_rules": weakened_or_contradicted_rules[:8],
        "radar_adjustments": radar_adjustments[:8],
        "watch_next_week": watch_next_week[:8],
        "source_urls": _source_urls_from_pack(pack),
    }


def _empty_baseline_lens(*, now: datetime, baseline_days: int, pack: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "kind": "baseline",
        "status": "empty",
        "generated_at": _iso(now),
        "lookback_days": baseline_days,
        "context_only": True,
        "build_ready_evidence": False,
        "model": None,
        "synthesis_mode": "empty",
        "model_error": None,
        "source_pack_summary": summarize_market_pain_pack(pack),
        "channels_requested": pack.get("channels_requested") or [],
        "curated_atom_count": int(pack.get("curated_atom_count") or 0),
        "market_thread_count": int(pack.get("market_thread_count") or 0),
        "raw_fallback_posts_scanned": int(pack.get("raw_fallback_posts_scanned") or 0),
        "executive_lens": "",
        "decision_rules": [],
        "rank_up_signals": [],
        "rank_down_signals": [],
        "buying_triggers": [],
        "distribution_patterns": [],
        "anti_patterns": [],
        "validation_playbook": [],
        "open_questions": [],
        "source_urls": [],
    }


def _empty_weekly_delta(
    *,
    now: datetime,
    delta_days: int,
    week_label: str,
    pack: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": DELTA_SCHEMA_VERSION,
        "kind": "weekly_delta",
        "status": "empty",
        "generated_at": _iso(now),
        "week_label": week_label,
        "delta_days": delta_days,
        "context_only": True,
        "build_ready_evidence": False,
        "model": None,
        "synthesis_mode": "empty",
        "model_error": None,
        "source_pack_summary": summarize_market_pain_pack(pack),
        "curated_atom_count": int(pack.get("curated_atom_count") or 0),
        "market_thread_count": int(pack.get("market_thread_count") or 0),
        "raw_fallback_posts_scanned": int(pack.get("raw_fallback_posts_scanned") or 0),
        "delta_summary": "",
        "reinforced_rules": [],
        "new_signals": [],
        "weakened_or_contradicted_rules": [],
        "radar_adjustments": [],
        "watch_next_week": [],
        "source_urls": [],
    }


def _build_current_context(
    *,
    baseline: dict[str, Any],
    weekly_delta: dict[str, Any],
    now: datetime,
    week_label: str,
    baseline_path: Path,
    delta_path: Path,
    current_path: Path,
    baseline_pack_path: Path,
    weekly_pack_path: Path,
) -> dict[str, Any]:
    status = "available" if (
        baseline.get("status") == "available" or weekly_delta.get("status") == "available"
    ) else "empty"
    source_urls = _dedupe_strings(
        list(baseline.get("source_urls") or []) + list(weekly_delta.get("source_urls") or [])
    )[:24]
    current = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "kind": "current",
        "status": status,
        "generated_at": _iso(now),
        "week_label": week_label,
        "context_only": True,
        "build_ready_evidence": False,
        "baseline_path": str(baseline_path),
        "weekly_delta_path": str(delta_path),
        "current_path": str(current_path),
        "baseline_pack_path": str(baseline_pack_path),
        "weekly_pack_path": str(weekly_pack_path),
        "channels_requested": baseline.get("channels_requested") or [],
        "baseline": baseline,
        "weekly_delta": weekly_delta,
        "source_urls": source_urls,
    }
    current["context_text"] = _current_context_text(current)
    return current


def _current_context_text(current: dict[str, Any]) -> str:
    if current.get("status") != "available":
        return ""
    baseline = current.get("baseline") if isinstance(current.get("baseline"), dict) else {}
    weekly_delta = (
        current.get("weekly_delta")
        if isinstance(current.get("weekly_delta"), dict)
        else {}
    )
    lines = [
        "Persistent business-market lens for MVP Radar.",
        "Context only: use this to rank, demote, and shape validation questions; never use it as build-ready proof.",
        f"Week: {current.get('week_label')}",
        (
            "Baseline: "
            f"{baseline.get('lookback_days') or 0} days, "
            f"{baseline.get('curated_atom_count') or 0} atoms, "
            f"{baseline.get('market_thread_count') or 0} threads, "
            f"synthesis={baseline.get('synthesis_mode') or 'unknown'}."
        ),
        (
            "Weekly delta: "
            f"{weekly_delta.get('delta_days') or 0} days, "
            f"{weekly_delta.get('curated_atom_count') or 0} atoms, "
            f"{weekly_delta.get('market_thread_count') or 0} threads, "
            f"synthesis={weekly_delta.get('synthesis_mode') or 'unknown'}."
        ),
    ]
    if baseline.get("executive_lens"):
        lines.extend(["", "Baseline lens:", f"- {baseline.get('executive_lens')}"])
    _extend_section(lines, "Decision rules", baseline.get("decision_rules"))
    _extend_section(lines, "Rank up if", baseline.get("rank_up_signals"))
    _extend_section(lines, "Rank down if", baseline.get("rank_down_signals"))
    _extend_section(lines, "Buying triggers / WTP hints", baseline.get("buying_triggers"))
    _extend_section(lines, "Distribution patterns", baseline.get("distribution_patterns"))
    _extend_section(lines, "Anti-patterns / risks", baseline.get("anti_patterns"))
    _extend_section(lines, "Validation playbook", baseline.get("validation_playbook"))
    if weekly_delta.get("status") == "available":
        if weekly_delta.get("delta_summary"):
            lines.extend(["", "Weekly delta:", f"- {weekly_delta.get('delta_summary')}"])
        _extend_section(lines, "Reinforced this week", weekly_delta.get("reinforced_rules"))
        _extend_section(lines, "New signals this week", weekly_delta.get("new_signals"))
        _extend_section(
            lines,
            "Weakened or contradicted",
            weekly_delta.get("weakened_or_contradicted_rules"),
        )
        _extend_section(lines, "Radar adjustments", weekly_delta.get("radar_adjustments"))
    _extend_section(lines, "Open questions", baseline.get("open_questions"))
    return "\n".join(lines)


def _baseline_prompt(*, pack: dict[str, Any], context_text: str) -> str:
    return "\n".join(
        [
            "Create a persistent 12-week market lens for MVP selection.",
            "Use the evidence below as market/business context only.",
            "Return strict JSON only, no markdown, with keys:",
            "executive_lens, decision_rules, rank_up_signals, rank_down_signals,",
            "buying_triggers, distribution_patterns, anti_patterns, validation_playbook, open_questions.",
            "Keep executive_lens under 1400 characters.",
            "Each list may contain up to 10 high-signal actionable strings; keep each string source-grounded.",
            "Do not invent revenue numbers, channels, or legal claims.",
            "",
            f"Source pack summary: {summarize_market_pain_pack(pack)}",
            "",
            "Structured source pack excerpt:",
            json.dumps(_pack_prompt_payload(pack, atom_limit=120, thread_limit=24), ensure_ascii=False, indent=2),
            "",
            _truncate(context_text, 30000),
        ]
    )


def _delta_prompt(*, baseline: dict[str, Any], pack: dict[str, Any], context_text: str) -> str:
    baseline_brief = {
        "executive_lens": baseline.get("executive_lens"),
        "decision_rules": baseline.get("decision_rules"),
        "rank_up_signals": baseline.get("rank_up_signals"),
        "rank_down_signals": baseline.get("rank_down_signals"),
        "validation_playbook": baseline.get("validation_playbook"),
    }
    return "\n".join(
        [
            "Update the persistent market lens with this week's business-channel context.",
            "Return strict JSON only, no markdown, with keys:",
            "delta_summary, reinforced_rules, new_signals, weakened_or_contradicted_rules,",
            "radar_adjustments, watch_next_week.",
            "Keep delta_summary under 1200 characters.",
            "Each list may contain up to 10 high-signal actionable strings; keep each string source-grounded.",
            "Only describe changes supported by this week's evidence. Keep context-only boundaries.",
            "",
            "Existing baseline lens:",
            json.dumps(baseline_brief, ensure_ascii=False, indent=2),
            "",
            f"Weekly source pack summary: {summarize_market_pain_pack(pack)}",
            "",
            "Structured weekly source pack excerpt:",
            json.dumps(_pack_prompt_payload(pack, atom_limit=80, thread_limit=24), ensure_ascii=False, indent=2),
            "",
            _truncate(context_text, 20000),
        ]
    )


def _market_lens_system() -> str:
    return (
        "You are a pragmatic market analyst helping an MVP radar choose better bets. "
        "You produce source-grounded decision context, not candidate recommendations. "
        "Never treat Telegram commentary as build-ready proof."
    )


def _pack_prompt_payload(pack: dict[str, Any], *, atom_limit: int, thread_limit: int) -> dict[str, Any]:
    context = pack.get("analyst_context") if isinstance(pack.get("analyst_context"), dict) else {}
    atoms = pack.get("curated_atoms") if isinstance(pack.get("curated_atoms"), list) else []
    threads = pack.get("market_threads") if isinstance(pack.get("market_threads"), list) else []
    return {
        "schema_version": pack.get("schema_version"),
        "status": pack.get("status"),
        "cutoff": pack.get("cutoff"),
        "channels_requested": pack.get("channels_requested") or [],
        "channels_with_curated_atoms": pack.get("channels_with_curated_atoms") or [],
        "channels_using_raw_fallback": pack.get("channels_using_raw_fallback") or [],
        "curated_atom_count": pack.get("curated_atom_count") or 0,
        "market_thread_count": pack.get("market_thread_count") or 0,
        "analyst_context": context,
        "market_threads": threads[:thread_limit],
        "curated_atoms": atoms[:atom_limit],
        "radar_gate_audit": pack.get("radar_gate_audit") or {},
    }


def _fallback_executive_lens(pack: dict[str, Any]) -> str:
    return (
        "Use the 12-week business-channel context as a standing decision lens: prefer "
        "narrow MVPs with visible buying triggers, cheap validation, and a plausible "
        "distribution path; demote platform-sized ideas and channels that require "
        "unproven paid acquisition or heavy custom infrastructure."
    )


def _fallback_delta_summary(pack: dict[str, Any]) -> str:
    return (
        "Weekly business context is available but was summarized deterministically; "
        "use it only as ranking and validation context."
        if pack.get("status") == "available"
        else "No weekly market delta with usable observations."
    )


def _observation_texts(items: Any, *, limit: int = 5) -> list[str]:
    results = []
    for item in items or []:
        if isinstance(item, dict):
            text = _text(item.get("text"))
            source_url = _text(item.get("source_url"))
            if text and source_url:
                text = f"{text} ({source_url})"
        else:
            text = _text(item)
        if text:
            results.append(_truncate(text, 320))
        if len(results) >= limit:
            break
    return results


def _string_items(value: Any, *, limit: int) -> list[str]:
    if value is None:
        return []
    source = value if isinstance(value, list) else [value]
    results = []
    for item in source:
        if isinstance(item, dict):
            text = (
                _text(item.get("rule"))
                or _text(item.get("signal"))
                or _text(item.get("claim"))
                or _text(item.get("text"))
                or _text(item.get("summary"))
            )
        else:
            text = _text(item)
        if text:
            results.append(_truncate(text, 320))
        if len(results) >= limit:
            break
    return results


def _extend_section(lines: list[str], title: str, items: Any, *, limit: int = 5) -> None:
    values = _string_items(items, limit=limit)
    if not values:
        return
    lines.append("")
    lines.append(f"{title}:")
    for value in values:
        lines.append(f"- {value}")


def _source_urls_from_pack(pack: dict[str, Any]) -> list[str]:
    refs = pack.get("source_refs") if isinstance(pack.get("source_refs"), list) else []
    urls = [
        str(ref.get("source_url") or "")
        for ref in refs
        if isinstance(ref, dict) and ref.get("source_url")
    ]
    return _dedupe_strings(urls)[:24]


def _market_lens_model(model: str | None) -> str:
    return (
        str(model).strip()
        if model and str(model).strip()
        else os.environ.get("LLM_MODEL_MARKET_LENS", "").strip()
        or os.environ.get("STRONG_MODEL", "").strip()
        or STRONG_MODEL
    )


def _should_use_llm(use_llm: bool | None) -> bool:
    if use_llm is not None:
        return use_llm
    return bool(
        os.environ.get("LLM_API_KEY", "").strip()
        or os.environ.get("ANTHROPIC_API_KEY", "").strip()
    )


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _with_source_window(
    payload: dict[str, Any],
    *,
    source_window_start: str,
    source_window_end: str,
    reporting_period: ReportingPeriod | None,
) -> dict[str, Any]:
    bounded = {
        **payload,
        "source_window_start": source_window_start,
        "source_window_end": source_window_end,
    }
    if reporting_period is not None:
        bounded.update(reporting_period.to_dict())
    return bounded


def _baseline_cache_is_compatible(
    baseline: dict[str, Any],
    *,
    reporting_period: ReportingPeriod | None,
    source_window_start: str,
    source_window_end: str,
) -> bool:
    if reporting_period is None:
        return True
    cached_start = _parse_utc(baseline.get("source_window_start"))
    cached_end = _parse_utc(baseline.get("source_window_end"))
    expected_start = _parse_utc(source_window_start)
    expected_end = _parse_utc(source_window_end)
    if None in {cached_start, cached_end, expected_start, expected_end}:
        return False
    period_fields = reporting_period.to_dict()
    identity_matches = all(
        str(baseline.get(field) or "") == period_fields[field]
        for field in (
            "reporting_week",
            "week_label",
            "period_mode",
            "analysis_period_start",
            "analysis_period_end",
        )
    )
    return cached_start == expected_start and cached_end == expected_end and identity_matches


def _parse_utc(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _cutoff(current: datetime, days: int) -> str:
    return (current - timedelta(days=max(1, days))).isoformat().replace("+00:00", "Z")


def _week_label(current: datetime) -> str:
    year, week, _ = current.isocalendar()
    return f"{year}-W{week:02d}"


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _truncate(text: str, limit: int) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: max(1, limit - 3)].rstrip() + "..."


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    results = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        results.append(normalized)
    return results

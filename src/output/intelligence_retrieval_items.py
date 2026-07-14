from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import stat
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import quote

from config.settings import PROJECT_ROOT
from db.ai_report_feedback import summarize_ai_report_feedback
from db.idea_threads import fetch_idea_thread_atoms, fetch_idea_threads
from db.knowledge_atoms import fetch_knowledge_atoms
from output.mvp_radar_reader import (
    MvpRadarReaderError,
    adapt_legacy_mvp_radar_payload,
    invalid_mvp_radar_projection,
    load_bound_mvp_radar_reader,
    load_unbound_mvp_radar_reader,
)
from output.weekly_run_manifest import (
    WeeklyRunManifestError,
    load_manifest,
    validate_manifest,
)
from output.weekly_intelligence_brief_v2 import (
    BRIEF_V2_DIRECTORY,
    BRIEF_V2_JSON_FILENAME,
    BRIEF_V2_SCHEMA_VERSION,
    WeeklyIntelligenceBriefV2Error,
    _strict_check_manifest_json_sources,
    load_manifest_bound_weekly_intelligence_brief_v2,
)
from output.strategy_reviewer import build_strategy_review
from output.reaction_personalization import (
    ReactionPersonalizationError,
    validate_reaction_effect,
)


DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "output"
DEFAULT_VISUAL_OUTPUT_DIR = DEFAULT_OUTPUT_ROOT / "ai_visual_intelligence"
DEFAULT_AI_OUTPUT_DIR = DEFAULT_OUTPUT_ROOT / "ai_intelligence"
DEFAULT_KNOWLEDGE_ATLAS_OUTPUT_DIR = DEFAULT_OUTPUT_ROOT / "knowledge_atlas"
DEFAULT_WEEKLY_BRIEF_OUTPUT_DIR = DEFAULT_OUTPUT_ROOT / "weekly_intelligence_briefs"
DEFAULT_WEEKLY_BRIEF_V2_OUTPUT_DIR = DEFAULT_OUTPUT_ROOT / BRIEF_V2_DIRECTORY
DEFAULT_WEEKLY_RUN_ROOT = DEFAULT_OUTPUT_ROOT / "weekly_intelligence_runs"
DEFAULT_MVP_OUTPUT_DIR = DEFAULT_OUTPUT_ROOT / "mvp_weekly"
DEFAULT_RADAR_OUTPUT_DIR = PROJECT_ROOT.parent / "Demand-to-MVP-Radar" / "reports" / "mvp_of_week"
WEEK_RE = re.compile(r"(?P<week>\d{4}-W\d{2})")
TOKEN_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{1,}")
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
MAX_RETRIEVAL_JSON_BYTES = 8_000_000


@dataclass(frozen=True)
class IntelligenceRetrievalItem:
    id: str
    item_type: str
    week_label: str | None
    title: str
    text: str
    summary: str | None = None
    source_refs: list[str] | None = None
    atom_ids: list[int | str] | None = None
    thread_slug: str | None = None
    project_name: str | None = None
    confidence: float | None = None
    evidence_tier: str | None = None
    verification_status: str | None = None
    status: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


def build_retrieval_items(
    settings: Any,
    week_label: str | None = None,
    *,
    output_root: str | Path | None = None,
    visual_output_root: str | Path | None = None,
    ai_output_root: str | Path | None = None,
    mvp_output_root: str | Path | None = None,
    radar_output_root: str | Path | None = None,
    weekly_run_root: str | Path | None = None,
    v2_source_roots: Iterable[str | Path] = (),
) -> list[IntelligenceRetrievalItem]:
    """Build a read-only projection over curated intelligence objects."""
    trusted_v2_roots = tuple(v2_source_roots)
    clean_week = str(week_label).strip() if week_label else None
    workbook = load_latest_workbook_json(
        settings,
        clean_week,
        output_root=output_root,
        visual_output_root=visual_output_root,
        ai_output_root=ai_output_root,
    )
    if workbook and not clean_week:
        clean_week = _clean_text(workbook.get("week_label")) or _artifact_week_label(workbook)

    items: list[IntelligenceRetrievalItem] = []
    loaded_artifact_paths: set[str] = set()
    if workbook:
        items.extend(_items_from_workbook(workbook))
        paths = workbook.get("_artifact_paths") if isinstance(workbook.get("_artifact_paths"), Mapping) else {}
        if paths.get("json"):
            loaded_artifact_paths.add(str(paths["json"]))
    for split_artifact in _load_split_sidecar_jsons(clean_week, output_root=output_root):
        paths = split_artifact.get("_artifact_paths") if isinstance(split_artifact.get("_artifact_paths"), Mapping) else {}
        json_path = str(paths.get("json") or "")
        if json_path and json_path in loaded_artifact_paths:
            continue
        items.extend(_items_from_workbook(split_artifact))
        if json_path:
            loaded_artifact_paths.add(json_path)
    v2_briefs, v2_authority_present = _load_weekly_brief_v2_sidecars(
        clean_week,
        output_root=output_root,
        weekly_run_root=weekly_run_root,
        allowed_source_roots=trusted_v2_roots,
    )
    if v2_authority_present:
        items = [item for item in items if item.item_type != "mvp_dossier"]
    for v2_brief, manifest_path in v2_briefs:
        items.extend(
            _items_from_workbook(
                v2_brief,
                v2_expected_manifest_path=manifest_path,
                v2_allowed_source_roots=trusted_v2_roots,
            )
        )

    with _optional_readonly_connection(getattr(settings, "db_path", None)) as connection:
        if connection is not None:
            items.extend(_knowledge_atom_items(connection, week_label=clean_week))
            items.extend(_idea_thread_items(connection, week_label=clean_week))
            items.extend(_canonical_idea_thread_items(connection, week_label=clean_week))
            items.extend(_feedback_summary_items(connection, week_label=clean_week))
            weekly_run_root = (
                Path(output_root) / "weekly_intelligence_runs"
                if output_root is not None
                else DEFAULT_WEEKLY_RUN_ROOT
            )
            items.extend(
                _strategy_reviewer_items(
                    connection,
                    week_label=clean_week,
                    weekly_run_root=weekly_run_root,
                )
            )

    if (
        clean_week
        and not v2_authority_present
        and not any(item.item_type == "mvp_dossier" for item in items)
    ):
        mvp = load_mvp_radar_status(
            clean_week,
            output_root=output_root,
            mvp_output_root=mvp_output_root,
            radar_output_root=radar_output_root,
        )
        if mvp:
            items.append(_mvp_item(mvp, clean_week))

    return _dedupe_items(items)


def search_retrieval_items(
    items: Iterable[IntelligenceRetrievalItem],
    query: str,
    filters: dict | None = None,
    limit: int = 10,
) -> list[dict]:
    clean_filters = dict(filters or {})
    filtered = [item for item in items if _matches_filters(item, clean_filters)]
    tokens = _query_tokens(query)
    scored: list[tuple[float, IntelligenceRetrievalItem]] = []
    for item in filtered:
        score = _search_score(item, query, tokens)
        if tokens and score <= 0:
            continue
        scored.append((score, item))
    scored.sort(
        key=lambda pair: (
            pair[0],
            pair[1].updated_at or pair[1].created_at or "",
            pair[1].week_label or "",
            pair[1].id,
        ),
        reverse=True,
    )
    return [_public_item_dict(item, score=score) for score, item in scored[: max(1, int(limit or 10))]]


def load_latest_workbook_json(
    settings: Any | None = None,
    week_label: str | None = None,
    *,
    output_root: str | Path | None = None,
    visual_output_root: str | Path | None = None,
    ai_output_root: str | Path | None = None,
) -> dict | None:
    del settings
    paths = _candidate_workbook_paths(
        week_label=week_label,
        output_root=output_root,
        visual_output_root=visual_output_root,
        ai_output_root=ai_output_root,
    )
    for path, artifact_kind in paths:
        payload = _read_json_dict(path)
        if payload is None:
            continue
        html_path = _html_path_for_workbook(path, payload, artifact_kind)
        result = dict(payload)
        result["_artifact_kind"] = artifact_kind
        result["_artifact_paths"] = {
            "json": str(path),
            "html": str(html_path) if html_path else None,
        }
        if not result.get("week_label"):
            week = _week_from_path(path)
            if week:
                result["week_label"] = week
        return result
    return None


def find_latest_week_label(
    settings: Any | None = None,
    *,
    output_root: str | Path | None = None,
    visual_output_root: str | Path | None = None,
    ai_output_root: str | Path | None = None,
) -> str | None:
    del settings
    candidates = _candidate_workbook_paths(
        week_label=None,
        output_root=output_root,
        visual_output_root=visual_output_root,
        ai_output_root=ai_output_root,
    )
    for path, _kind in candidates:
        week = _week_from_path(path)
        if week:
            return week
    return None


def load_mvp_radar_status(
    week_label: str,
    *,
    output_root: str | Path | None = None,
    mvp_output_root: str | Path | None = None,
    radar_output_root: str | Path | None = None,
) -> dict | None:
    clean_week = str(week_label or "").strip()
    if not clean_week:
        return None
    for path in _candidate_mvp_paths(
        clean_week,
        output_root=output_root,
        mvp_output_root=mvp_output_root,
        radar_output_root=radar_output_root,
    ):
        if path.exists():
            return load_unbound_mvp_radar_reader(path, expected_week=clean_week)
    return None


def _load_split_sidecar_jsons(
    week_label: str | None,
    *,
    output_root: str | Path | None,
) -> list[dict]:
    clean_week = str(week_label or "").strip()
    if not clean_week:
        return []
    atlas_dir, brief_dir = _split_artifact_dirs(output_root=output_root)
    candidates = [
        (brief_dir / f"{clean_week}.weekly-brief.json", "weekly_intelligence_brief"),
        (atlas_dir / f"{clean_week}.knowledge-atlas.json", "knowledge_atlas"),
    ]
    artifacts = []
    for path, artifact_kind in candidates:
        payload = _read_json_dict(path)
        if payload is None:
            continue
        html_path = _html_path_for_workbook(path, payload, artifact_kind)
        result = dict(payload)
        result["_artifact_kind"] = artifact_kind
        result["_artifact_paths"] = {
            "json": str(path),
            "html": str(html_path) if html_path else None,
        }
        if not result.get("week_label"):
            result["week_label"] = clean_week
        artifacts.append(result)
    return artifacts


def _load_weekly_brief_v2_sidecars(
    week_label: str | None,
    *,
    output_root: str | Path | None,
    weekly_run_root: str | Path | None,
    allowed_source_roots: Iterable[str | Path],
) -> tuple[list[tuple[dict[str, Any], Path]], bool]:
    clean_week = str(week_label or "").strip()
    if not clean_week:
        return [], False
    requested_output = (
        Path(output_root).expanduser().absolute()
        if output_root is not None
        else DEFAULT_OUTPUT_ROOT.absolute()
    )
    try:
        output_base = requested_output.resolve()
    except (OSError, RuntimeError, ValueError):
        return [], True
    if requested_output != output_base:
        return [], True
    selected_run_root = (
        Path(weekly_run_root).expanduser()
        if weekly_run_root is not None
        else output_base / "weekly_intelligence_runs"
    )
    manifest_path = _select_weekly_v2_manifest(
        clean_week,
        weekly_run_root=selected_run_root,
    )
    if manifest_path is None:
        return [], False
    try:
        canonical_run_root = selected_run_root.resolve(strict=True)
        lexical_manifest = manifest_path.expanduser().absolute()
        resolved_manifest = lexical_manifest.resolve(strict=True)
        if (
            lexical_manifest != resolved_manifest
            or resolved_manifest.parent.parent != canonical_run_root
        ):
            return [], True
        strict_manifest, _raw = _read_retrieval_manifest(resolved_manifest)
        manifest = strict_manifest
        validate_manifest(
            manifest,
            path_base=resolved_manifest.parent,
            allowed_roots=(resolved_manifest.parent,),
            check_artifact_existence=False,
        )
        _strict_check_manifest_json_sources(manifest, resolved_manifest)
        validate_manifest(
            manifest,
            path_base=resolved_manifest.parent,
            allowed_roots=(resolved_manifest.parent,),
            check_artifact_existence=True,
        )
        if manifest.get("run_status") not in {"complete", "partial"}:
            return [], True
        run_id = str(manifest.get("run_id") or "")
        v2_root = output_base / BRIEF_V2_DIRECTORY
        if v2_root.is_symlink():
            return [], True
        if not v2_root.exists():
            return [], False
        if not v2_root.is_dir():
            return [], True
        run_directory = v2_root / run_id
        if run_directory.is_symlink():
            return [], True
        if not run_directory.exists():
            return [], False
        if not run_directory.is_dir():
            return [], True
        lexical_path = run_directory / BRIEF_V2_JSON_FILENAME
        if lexical_path.is_symlink():
            return [], True
        if not lexical_path.is_file():
            return [], True
        roots = (
            output_base,
            resolved_manifest.parent,
            *(Path(root) for root in allowed_source_roots),
        )
        payload = load_manifest_bound_weekly_intelligence_brief_v2(
            lexical_path,
            expected_manifest_path=resolved_manifest,
            allowed_source_roots=roots,
        )
        period = payload.get("reporting_period")
        paths = payload.get("artifact_paths")
        if (
            not isinstance(period, Mapping)
            or period.get("reporting_week") != clean_week
            or not isinstance(paths, Mapping)
        ):
            return [], True
        result = dict(payload)
        result["_artifact_kind"] = "weekly_intelligence_brief_v2"
        result["_artifact_paths"] = {
            "json": str(paths.get("json") or ""),
            "html": str(paths.get("html") or ""),
            "source_catalog": str(paths.get("source_catalog") or ""),
        }
        return [(result, resolved_manifest)], True
    except (
        OSError,
        RuntimeError,
        UnicodeError,
        TypeError,
        ValueError,
        RecursionError,
        OverflowError,
        WeeklyIntelligenceBriefV2Error,
    ):
        return [], True


def _select_weekly_v2_manifest(
    week_label: str,
    *,
    weekly_run_root: Path,
) -> Path | None:
    try:
        root = weekly_run_root.expanduser().resolve(strict=True)
        candidates = list(root.glob("*/manifest.json"))
    except (OSError, RuntimeError, ValueError):
        return None
    selected: tuple[tuple[int, str, str], Path] | None = None
    for lexical_path in candidates:
        try:
            path = lexical_path.resolve(strict=True)
            if lexical_path.absolute() != path or path.parent.parent != root:
                try:
                    raw = _read_retrieval_bytes(lexical_path)
                except (OSError, ValueError):
                    raw = b""
                if (
                    week_label in lexical_path.parent.name
                    or week_label.encode("utf-8") in raw
                ):
                    invalid_path = lexical_path.absolute()
                    key = (
                        2**63 - 1,
                        lexical_path.parent.name,
                        str(invalid_path),
                    )
                    if selected is None or key > selected[0]:
                        selected = (key, invalid_path)
                continue
            manifest, _raw = _read_retrieval_manifest(path)
            if manifest.get("reporting_week") != week_label:
                continue
            key = (
                _retrieval_manifest_generated_at_ns(manifest),
                str(manifest.get("run_id") or ""),
                str(path),
            )
            if selected is None or key > selected[0]:
                selected = (key, path)
        except (
            OSError,
            RuntimeError,
            UnicodeError,
            TypeError,
            ValueError,
            RecursionError,
            OverflowError,
            WeeklyRunManifestError,
        ):
            try:
                raw = _read_retrieval_bytes(lexical_path)
            except (OSError, ValueError):
                raw = b""
            if (
                week_label in lexical_path.parent.name
                or (
                    len(raw) <= MAX_RETRIEVAL_JSON_BYTES
                    and week_label.encode("utf-8") in raw
                )
            ):
                invalid_path = lexical_path.absolute()
                key = (
                    _retrieval_manifest_filesystem_ns(lexical_path),
                    lexical_path.parent.name,
                    str(invalid_path),
                )
                if selected is None or key > selected[0]:
                    selected = (key, invalid_path)
    return selected[1] if selected is not None else None


def _retrieval_manifest_generated_at_ns(manifest: Mapping[str, Any]) -> int:
    value = str(manifest.get("generated_at") or "")
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    instant = datetime.fromisoformat(normalized).astimezone(timezone.utc)
    delta = instant - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (
        (delta.days * 86_400 + delta.seconds) * 1_000_000
        + delta.microseconds
    ) * 1_000


def _retrieval_manifest_filesystem_ns(path: Path) -> int:
    try:
        path_stat = path.stat()
        parent_stat = path.parent.stat()
    except OSError:
        return 0
    return max(
        path_stat.st_mtime_ns,
        path_stat.st_ctime_ns,
        parent_stat.st_mtime_ns,
        parent_stat.st_ctime_ns,
    )


def _read_retrieval_manifest(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = _read_retrieval_bytes(path)
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_retrieval_json_object,
            parse_constant=_reject_retrieval_json_constant,
            parse_float=_strict_retrieval_json_float,
        )
    except (
        json.JSONDecodeError,
        UnicodeError,
        RecursionError,
        OverflowError,
        ValueError,
    ) as exc:
        raise WeeklyRunManifestError(f"invalid strict weekly manifest: {exc}") from exc
    if not isinstance(payload, dict):
        raise WeeklyRunManifestError("weekly manifest root must be an object")
    validate_manifest(payload)
    return payload, raw


def _read_retrieval_bytes(path: Path) -> bytes:
    file_descriptor: int | None = None
    try:
        file_descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
        metadata = os.fstat(file_descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("weekly manifest candidate is not a regular file")
        with os.fdopen(file_descriptor, "rb") as handle:
            file_descriptor = None
            raw = handle.read(MAX_RETRIEVAL_JSON_BYTES + 1)
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
    if len(raw) > MAX_RETRIEVAL_JSON_BYTES:
        raise ValueError("weekly manifest candidate exceeds byte limit")
    return raw


def _unique_retrieval_json_object(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _reject_retrieval_json_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON constant: {value}")


def _strict_retrieval_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite JSON number: {value}")
    return parsed


def _items_from_workbook(
    workbook: Mapping[str, Any],
    *,
    v2_expected_manifest_path: str | Path | None = None,
    v2_allowed_source_roots: Iterable[str | Path] = (),
) -> list[IntelligenceRetrievalItem]:
    if workbook.get("schema_version") == BRIEF_V2_SCHEMA_VERSION:
        return _items_from_weekly_brief_v2(
            workbook,
            expected_manifest_path=v2_expected_manifest_path,
            allowed_source_roots=v2_allowed_source_roots,
        )
    week = _clean_text(workbook.get("week_label")) or _artifact_week_label(workbook)
    generated_at = _clean_text(workbook.get("generated_at")) or None
    artifact_refs = _artifact_source_refs(workbook)
    items: list[IntelligenceRetrievalItem] = []
    items.extend(_workbook_section_items(workbook, week_label=week, generated_at=generated_at, artifact_refs=artifact_refs))
    items.extend(_atlas_thread_items(workbook, week_label=week, generated_at=generated_at, artifact_refs=artifact_refs))
    items.extend(
        _canonical_thread_registry_items(
            workbook,
            week_label=week,
            generated_at=generated_at,
            artifact_refs=artifact_refs,
        )
    )
    items.extend(_canonical_contract_items(workbook, week_label=week, generated_at=generated_at))
    items.extend(_claim_card_items(workbook, week_label=week, generated_at=generated_at))
    items.extend(_deep_explanation_items(workbook, week_label=week, generated_at=generated_at))
    items.extend(_action_card_items(workbook, week_label=week, generated_at=generated_at))
    items.extend(_project_diagnostic_items(workbook, week_label=week, generated_at=generated_at))
    items.extend(_project_learning_projection_items(workbook, week_label=week, generated_at=generated_at))
    items.extend(_reaction_effect_items(workbook, week_label=week, generated_at=generated_at))
    mvp = workbook.get("mvp_radar") if isinstance(workbook.get("mvp_radar"), Mapping) else None
    if mvp:
        projection, authoritative = _workbook_mvp_projection(workbook, mvp, week)
        items.append(
            _mvp_item(
                projection,
                week,
                authoritative=authoritative,
            )
        )
    return items


def _items_from_weekly_brief_v2(
    workbook: Mapping[str, Any],
    *,
    expected_manifest_path: str | Path | None,
    allowed_source_roots: Iterable[str | Path],
) -> list[IntelligenceRetrievalItem]:
    metadata = (
        workbook.get("_artifact_paths")
        if isinstance(workbook.get("_artifact_paths"), Mapping)
        else {}
    )
    if (
        workbook.get("_artifact_kind") != "weekly_intelligence_brief_v2"
        or expected_manifest_path is None
    ):
        return []
    source_path = _clean_text(metadata.get("json"))
    if not source_path or not Path(source_path).is_absolute():
        return []
    try:
        path = Path(source_path).resolve(strict=True)
        output_base = path.parent.parent.parent.resolve()
        loaded = load_manifest_bound_weekly_intelligence_brief_v2(
            path,
            expected_manifest_path=expected_manifest_path,
            allowed_source_roots=(
                output_base,
                Path(expected_manifest_path).resolve(strict=True).parent,
                *(Path(root) for root in allowed_source_roots),
            ),
        )
    except (
        OSError,
        UnicodeError,
        TypeError,
        ValueError,
        RecursionError,
        OverflowError,
        RuntimeError,
        WeeklyIntelligenceBriefV2Error,
    ):
        return []
    supplied = {
        key: copy_value
        for key, copy_value in workbook.items()
        if key not in {"_artifact_kind", "_artifact_paths"}
    }
    if supplied != loaded:
        return []
    artifact_paths = loaded.get("artifact_paths")
    period = loaded.get("reporting_period")
    if not isinstance(artifact_paths, Mapping) or not isinstance(period, Mapping):
        return []
    if (
        str(path) != str(artifact_paths.get("json") or "")
        or _clean_text(metadata.get("html"))
        != _clean_text(artifact_paths.get("html"))
        or _clean_text(metadata.get("source_catalog"))
        != _clean_text(artifact_paths.get("source_catalog"))
    ):
        return []
    run_id = _clean_text(loaded.get("run_id"))
    week = _clean_text(period.get("reporting_week")) or None
    generated_at = _clean_text(loaded.get("generated_at")) or None
    if not run_id or not week:
        return []
    artifact_refs = _unique(
        [
            artifact_paths.get("json"),
            artifact_paths.get("html"),
            artifact_paths.get("source_catalog"),
        ]
    )
    items: list[IntelligenceRetrievalItem] = []
    thesis = loaded.get("weekly_thesis")
    if isinstance(thesis, Mapping):
        evidence_refs = _string_values(thesis.get("evidence_refs"))
        items.append(
            IntelligenceRetrievalItem(
                id=f"brief_v2_thesis:{run_id}",
                item_type="weekly_thesis",
                week_label=week,
                title=_clean_text(thesis.get("title")) or "Главный вывод недели",
                summary=_clean_text(thesis.get("plain_language_summary")) or None,
                text=_join_text(
                    thesis.get("title"),
                    thesis.get("plain_language_summary"),
                    thesis.get("why_for_operator"),
                    _reader_confidence_label(thesis.get("confidence")),
                ),
                source_refs=_unique([*artifact_refs, *evidence_refs]),
                atom_ids=_atom_ids_from_refs(evidence_refs),
                verification_status=_clean_text(thesis.get("confidence")) or None,
                status=_clean_text(loaded.get("run_status")) or None,
                created_at=generated_at,
                updated_at=generated_at,
            )
        )

    signals = [
        item for item in _as_list(loaded.get("signals")) if isinstance(item, Mapping)
    ][:3]
    signal_by_ref = {
        _clean_text(signal.get("signal_id")): signal
        for signal in signals
        if _clean_text(signal.get("signal_id"))
    }
    for index, signal in enumerate(signals, start=1):
        signal_ref = _clean_text(signal.get("signal_id"))
        evidence_refs = _string_values(signal.get("evidence_refs"))
        evidence_summary = (
            signal.get("evidence_summary")
            if isinstance(signal.get("evidence_summary"), Mapping)
            else {}
        )
        items.append(
            IntelligenceRetrievalItem(
                id=f"brief_v2_signal:{run_id}:{index}:{_slug(signal_ref)}",
                item_type="brief_signal",
                week_label=week,
                title=_clean_text(signal.get("title")) or f"Сигнал {index}",
                summary=_clean_text(signal.get("what_changed")) or None,
                text=_join_text(
                    signal.get("what_happened"),
                    signal.get("plain_explanation"),
                    signal.get("what_changed"),
                    signal.get("why_for_operator"),
                    _clean_text(
                        (
                            signal.get("reaction_effect")
                            if isinstance(signal.get("reaction_effect"), Mapping)
                            else {}
                        ).get("reader_reason_ru")
                    ),
                    _clean_text(
                        (
                            signal.get("next_action")
                            if isinstance(signal.get("next_action"), Mapping)
                            else {}
                        ).get("title")
                    ),
                    (
                        signal.get("next_action")
                        if isinstance(signal.get("next_action"), Mapping)
                        else {}
                    ).get("acceptance_criteria"),
                    signal.get("do_not_do"),
                    evidence_summary.get("confidence_reason_ru"),
                ),
                source_refs=_unique([*artifact_refs, *evidence_refs]),
                atom_ids=_atom_ids_from_refs(evidence_refs),
                evidence_tier=_clean_text(
                    evidence_summary.get("evidence_maturity")
                )
                or None,
                verification_status=_clean_text(signal.get("confidence")) or None,
                status=_clean_text(signal.get("decision")) or None,
                created_at=generated_at,
                updated_at=generated_at,
            )
        )

    matrix = loaded.get("decision_matrix")
    if isinstance(matrix, Mapping):
        for bucket in ("act", "study", "watch", "ignore"):
            for index, row in enumerate(_as_list(matrix.get(bucket)), start=1):
                if not isinstance(row, Mapping):
                    continue
                signal_ref = _clean_text(row.get("signal_ref"))
                signal = signal_by_ref.get(signal_ref, {})
                evidence_refs = _string_values(signal.get("evidence_refs"))
                items.append(
                    IntelligenceRetrievalItem(
                        id=(
                            f"brief_v2_decision:{run_id}:{bucket}:{index}:"
                            f"{_slug(signal_ref)}"
                        ),
                        item_type="brief_decision",
                        week_label=week,
                        title=_clean_text(row.get("label_ru"))
                        or f"Решение {index}",
                        summary=_clean_text(signal.get("title")) or None,
                        text=_join_text(
                            row.get("label_ru"),
                            signal.get("title"),
                            signal.get("why_for_operator"),
                        ),
                        source_refs=_unique([*artifact_refs, *evidence_refs]),
                        atom_ids=_atom_ids_from_refs(evidence_refs),
                        evidence_tier=_clean_text(row.get("evidence_maturity"))
                        or None,
                        verification_status=_clean_text(row.get("confidence"))
                        or None,
                        status=bucket,
                        created_at=generated_at,
                        updated_at=generated_at,
                    )
                )

    actions = loaded.get("actions")
    if isinstance(actions, Mapping):
        action_rows = []
        if isinstance(actions.get("primary"), Mapping):
            action_rows.append(actions["primary"])
        action_rows.extend(
            item
            for item in _as_list(actions.get("secondary"))
            if isinstance(item, Mapping)
        )
        for index, action in enumerate(action_rows, start=1):
            signal_ref = _clean_text(action.get("signal_ref"))
            signal = signal_by_ref.get(signal_ref, {})
            evidence_refs = _string_values(signal.get("evidence_refs"))
            items.append(
                IntelligenceRetrievalItem(
                    id=f"brief_v2_action:{run_id}:{index}:{_slug(signal_ref)}",
                    item_type="brief_action",
                    week_label=week,
                    title=_clean_text(action.get("title")) or f"Действие {index}",
                    summary=(
                        "Основное действие"
                        if action.get("role") == "primary"
                        else "Дополнительное действие"
                    ),
                    text=_join_text(action.get("acceptance_criteria")),
                    source_refs=_unique([*artifact_refs, *evidence_refs]),
                    atom_ids=_atom_ids_from_refs(evidence_refs),
                    status=_clean_text(action.get("role")) or None,
                    created_at=generated_at,
                    updated_at=generated_at,
                )
            )

    for index, action in enumerate(
        (
            item
            for item in _as_list(loaded.get("project_actions"))
            if isinstance(item, Mapping)
        ),
        start=1,
    ):
        evidence_refs = _string_values(action.get("evidence_refs"))
        items.append(
            IntelligenceRetrievalItem(
                id=f"brief_v2_project:{run_id}:{index}",
                item_type="project_action",
                week_label=week,
                title=_clean_text(action.get("suggested_change"))
                or f"Проектное действие {index}",
                summary=_clean_text(action.get("why_this_project")) or None,
                text=_join_text(
                    action.get("project_name"),
                    action.get("suggested_change"),
                    action.get("why_this_project"),
                    action.get("acceptance_criteria"),
                    action.get("risk"),
                ),
                source_refs=_unique([*artifact_refs, *evidence_refs]),
                atom_ids=_atom_ids_from_refs(evidence_refs),
                project_name=_clean_text(action.get("project_name")) or None,
                verification_status=_clean_text(action.get("confidence")) or None,
                status="confirmed",
                created_at=generated_at,
                updated_at=generated_at,
            )
        )

    reaction = loaded.get("reaction_effect")
    if isinstance(reaction, Mapping):
        reaction_refs = _unique(
            [
                *artifact_refs,
                reaction.get("snapshot_ref"),
                reaction.get("run_id"),
            ]
        )
        items.append(
            IntelligenceRetrievalItem(
                id=f"brief_v2_reaction:{run_id}",
                item_type="reaction_effect",
                week_label=week,
                title="Влияние личных реакций на бриф",
                summary=_clean_text(reaction.get("reader_summary_ru")) or None,
                text=_join_text(
                    reaction.get("reader_summary_ru"),
                    (
                        "Обнаружено личных реакций: "
                        + str(
                            (
                                reaction.get("counts")
                                if isinstance(reaction.get("counts"), Mapping)
                                else {}
                            ).get("personal_reaction_events_detected")
                            or 0
                        )
                    ),
                ),
                source_refs=reaction_refs,
                status=_clean_text(reaction.get("status")) or None,
                created_at=generated_at,
                updated_at=generated_at,
            )
        )

    feedback = loaded.get("feedback_effect")
    if isinstance(feedback, Mapping):
        items.append(
            IntelligenceRetrievalItem(
                id=f"brief_v2_feedback_effect:{run_id}",
                item_type="confirmed_feedback_effect",
                week_label=week,
                title="Влияние подтверждённой обратной связи",
                summary=(
                    "Рассмотрено подтверждённых событий: "
                    + str(feedback.get("confirmed_events_considered") or 0)
                ),
                text=_join_text(
                    *[
                        row.get("reader_summary_ru")
                        for field in (
                            "applied_changes",
                            "unchanged",
                            "requires_code_or_config",
                        )
                        for row in _as_list(feedback.get(field))
                        if isinstance(row, Mapping)
                    ]
                ),
                source_refs=artifact_refs,
                status="confirmed_snapshot",
                created_at=generated_at,
                updated_at=generated_at,
            )
        )

    for index, target in enumerate(
        (
            item
            for item in _as_list(loaded.get("feedback_targets"))
            if isinstance(item, Mapping)
        ),
        start=1,
    ):
        items.append(
            IntelligenceRetrievalItem(
                id=f"brief_v2_feedback_target:{run_id}:{index}",
                item_type="feedback_target",
                week_label=week,
                title=_clean_text(target.get("prompt_ru"))
                or f"Вопрос обратной связи {index}",
                summary={
                    "weekly_brief": "Выпуск целиком",
                    "signal": "Сигнал выпуска",
                    "project_action": "Проектное действие",
                }.get(_clean_text(target.get("target_type")), "Выпуск целиком"),
                text=_clean_text(target.get("prompt_ru")),
                source_refs=artifact_refs,
                status="available",
                created_at=generated_at,
                updated_at=generated_at,
            )
        )

    radar = loaded.get("mvp_radar")
    if isinstance(radar, Mapping):
        radar_item = _mvp_item(radar, week, authoritative=True)
        items.append(
            replace(
                radar_item,
                source_refs=_unique(
                    [*artifact_refs, *(radar_item.source_refs or [])]
                ),
                created_at=generated_at,
                updated_at=generated_at,
            )
        )
    return items


def _atom_ids_from_refs(refs: Iterable[object]) -> list[int | str]:
    result: list[int | str] = []
    for raw in refs:
        value = str(raw or "")
        if not value.startswith("atom:"):
            continue
        atom_id = value.removeprefix("atom:")
        result.append(int(atom_id) if atom_id.isdigit() else atom_id)
    return _unique(result)


def _workbook_mvp_projection(
    workbook: Mapping[str, Any],
    embedded: Mapping[str, Any],
    week_label: str | None,
) -> tuple[dict, bool]:
    """Recover Radar authority only through the exact manifest-bound sidecar."""

    source_paths = (
        workbook.get("_artifact_paths")
        if isinstance(workbook.get("_artifact_paths"), Mapping)
        else {}
    )
    source_path = _clean_text(source_paths.get("json"))
    manifest_ref = _clean_text(workbook.get("manifest_path"))
    artifact_kind = _clean_text(workbook.get("_artifact_kind"))
    stage_name = {
        "weekly_intelligence_brief": "weekly_brief",
        "knowledge_atlas": "knowledge_atlas",
    }.get(artifact_kind)
    try:
        if not source_path or not manifest_ref or stage_name is None:
            raise ValueError("workbook has no manifest-bound reader identity")
        manifest_path = Path(manifest_ref)
        if not manifest_path.is_absolute():
            raise ValueError("workbook manifest path must be absolute")
        if manifest_path.stat().st_size > MAX_RETRIEVAL_JSON_BYTES:
            raise ValueError("weekly manifest exceeds the retrieval byte limit")
        manifest_path = manifest_path.resolve(strict=True)
        run_dir = manifest_path.parent
        artifact_path = Path(source_path).resolve(strict=True)
        if not artifact_path.is_relative_to(run_dir):
            raise ValueError("workbook artifact escapes its weekly run")
        manifest = load_manifest(
            manifest_path,
            path_base=run_dir,
            allowed_roots=(run_dir,),
            check_artifact_existence=True,
        )
        if manifest.get("run_status") not in {"complete", "partial"}:
            raise ValueError("workbook manifest is not terminal")
        stage = manifest["stages"][stage_name]
        if stage.get("status") != "succeeded":
            raise ValueError("workbook stage did not succeed")
        expected_path = (run_dir / str(stage.get("json_path") or "")).resolve()
        if artifact_path != expected_path:
            raise ValueError("workbook is not the JSON bound by its manifest")
        if workbook.get("run_id") != manifest.get("run_id"):
            raise ValueError("workbook/manifest run identity mismatch")
        expected_week = _clean_text(manifest.get("reporting_week"))
        if week_label != expected_week:
            raise ValueError("workbook/manifest reporting week mismatch")
        projection = load_bound_mvp_radar_reader(
            manifest,
            path_base=run_dir,
            allowed_roots=(run_dir,),
        )
        authoritative = (
            projection.get("schema_version") == "mvp_radar_reader.v1"
            and projection.get("reader_state") in {"available", "no_candidate"}
        )
        return projection, authoritative
    except (
        OSError,
        UnicodeError,
        TypeError,
        ValueError,
        RecursionError,
        OverflowError,
        RuntimeError,
    ):
        pass
    try:
        return (
            adapt_legacy_mvp_radar_payload(
                embedded,
                source_path=source_path or None,
                expected_week=week_label or "",
            ),
            False,
        )
    except (
        MvpRadarReaderError,
        TypeError,
        ValueError,
        RecursionError,
        OverflowError,
    ) as exc:
        return (
            invalid_mvp_radar_projection(
                week_label or "",
                source_path=source_path or None,
                reason=f"MVP Radar workbook projection is invalid: {exc}",
            ),
            False,
        )


def _canonical_thread_registry_items(
    workbook: Mapping[str, Any],
    *,
    week_label: str | None,
    generated_at: str | None,
    artifact_refs: list[str],
) -> list[IntelligenceRetrievalItem]:
    """Project IRX-4 registry rows without replacing V1 atlas/raw items."""

    threads = [
        item
        for item in _as_list(workbook.get("canonical_threads"))
        if isinstance(item, Mapping)
    ][:12]
    result: list[IntelligenceRetrievalItem] = []
    for index, thread in enumerate(threads, start=1):
        canonical_id = _clean_text(thread.get("canonical_thread_id"))
        stable_slug = _clean_text(thread.get("stable_slug") or thread.get("slug"))
        if not canonical_id or not stable_slug:
            continue
        title = (
            _clean_text(thread.get("title_ru"))
            or _clean_text(thread.get("title_en"))
            or stable_slug
        )
        aliases: list[str] = []
        for raw_alias in _as_list(
            thread.get("aliases") or thread.get("raw_thread_aliases")
        ):
            if isinstance(raw_alias, Mapping):
                value = _clean_text(
                    raw_alias.get("alias_value") or raw_alias.get("value")
                )
            else:
                value = _clean_text(raw_alias)
            if value and value not in aliases:
                aliases.append(value)
        atom_ids = _unique(
            [
                *_list_values(thread.get("atom_ids")),
                *[
                    atom.get("id")
                    for atom in _as_list(thread.get("atoms"))
                    if isinstance(atom, Mapping) and atom.get("id") not in (None, "")
                ],
            ]
        )
        source_refs = _unique(
            [
                *artifact_refs,
                *_string_values(thread.get("source_refs")),
                *_string_values(thread.get("source_urls")),
            ]
        )
        result.append(
            IntelligenceRetrievalItem(
                id=f"canonical_thread:{stable_slug}",
                item_type="canonical_thread",
                week_label=week_label,
                title=title or f"Canonical thread {index}",
                summary=_clean_text(thread.get("thesis") or thread.get("summary")) or None,
                text=_join_text(
                    title,
                    thread.get("title_en"),
                    thread.get("thesis"),
                    canonical_id,
                    " ".join(aliases),
                    " ".join(_string_values(thread.get("entities"))),
                    " ".join(_string_values(thread.get("merged_from"))),
                    " ".join(_string_values(thread.get("split_from"))),
                    thread.get("curator_version"),
                ),
                source_refs=source_refs,
                atom_ids=atom_ids,
                thread_slug=stable_slug,
                evidence_tier=_clean_text(thread.get("evidence_maturity")) or None,
                status=_clean_text(thread.get("status")) or None,
                created_at=_clean_text(thread.get("first_seen_at")) or generated_at,
                updated_at=_clean_text(thread.get("last_seen_at")) or generated_at,
            )
        )
    return result


def _reaction_effect_items(
    workbook: Mapping[str, Any],
    *,
    week_label: str | None,
    generated_at: str | None,
) -> list[IntelligenceRetrievalItem]:
    """Expose the additive IRX-3 receipt as audit-friendly retrieval items.

    The reader HTML deliberately hides snapshot and lineage identifiers.  The
    retrieval projection is the compatible machine-facing surface where those
    already-validated sidecar references remain queryable.
    """

    effect = workbook.get("reaction_effect")
    if not isinstance(effect, Mapping):
        return []
    schema_version = _clean_text(effect.get("schema_version"))
    if schema_version != "reaction_personalization.v1":
        return []
    try:
        effect = validate_reaction_effect(effect)
    except (TypeError, ValueError, ReactionPersonalizationError):
        return []
    surface = _clean_text(effect.get("surface")) or _clean_text(workbook.get("artifact_type")) or "unknown"
    snapshot_ref = _clean_text(effect.get("snapshot_ref"))
    run_id = _clean_text(effect.get("run_id"))
    status = _clean_text(effect.get("status")) or "unavailable"
    counts = effect.get("counts") if isinstance(effect.get("counts"), Mapping) else {}
    source_refs = _unique(
        value
        for value in (
            snapshot_ref,
            run_id,
            *_artifact_source_refs(workbook),
        )
        if value
    )
    result = [
        IntelligenceRetrievalItem(
            id=f"reaction_effect:{week_label or 'unknown'}:{_slug(surface)}",
            item_type="reaction_effect",
            week_label=week_label,
            title="Reaction personalization receipt",
            summary=_clean_text(effect.get("reader_summary_ru")) or None,
            text=_join_text(
                effect.get("reader_summary_ru"),
                {"status": status, "snapshot_status": effect.get("snapshot_status"), "counts": counts},
            ),
            source_refs=source_refs,
            status=status,
            created_at=generated_at,
            updated_at=generated_at,
        )
    ]

    selected_thread_refs: set[str] = set()
    for bucket_name, item_type in (
        ("influenced_items", "reaction_influence"),
        ("linked_only_items", "reaction_linked_only"),
    ):
        for index, raw_item in enumerate(_as_list(effect.get(bucket_name)), start=1):
            if not isinstance(raw_item, Mapping):
                continue
            item_ref = _clean_text(raw_item.get("surface_item_ref")) or f"item-{index}"
            compatibility_ref = _clean_text(
                raw_item.get("compatibility_thread_ref") or raw_item.get("current_thread_ref")
            )
            if compatibility_ref:
                selected_thread_refs.add(compatibility_ref)
            evidence_refs = _string_values(raw_item.get("evidence_refs"))
            reacted_post_refs = _string_values(raw_item.get("reacted_post_refs"))
            item_source_refs = _string_values(raw_item.get("source_refs"))
            atom_ids: list[int | str] = []
            for ref in evidence_refs:
                if ref.startswith("atom:"):
                    value = ref.removeprefix("atom:")
                    atom_ids.extend(_list_values(int(value) if value.isdigit() else value))
            result.append(
                IntelligenceRetrievalItem(
                    id=f"{item_type}:{week_label or 'unknown'}:{_slug(surface)}:{_slug(item_ref)}",
                    item_type=item_type,
                    week_label=week_label,
                    title=_clean_text(raw_item.get("reader_reason_ru")) or item_ref,
                    summary=_clean_text(raw_item.get("effect")) or None,
                    text=_json_text(dict(raw_item)),
                    source_refs=_unique(
                        [
                            *source_refs,
                            *reacted_post_refs,
                            *item_source_refs,
                            *evidence_refs,
                        ]
                    ),
                    atom_ids=_unique(atom_ids),
                    thread_slug=_reaction_thread_slug(compatibility_ref),
                    status=_clean_text(raw_item.get("effect")) or None,
                    created_at=generated_at,
                    updated_at=generated_at,
                )
            )

    for index, raw_item in enumerate(
        _as_list(effect.get("eligible_thread_audit")),
        start=1,
    ):
        if not isinstance(raw_item, Mapping):
            continue
        compatibility_ref = _clean_text(
            raw_item.get("compatibility_thread_ref")
            or raw_item.get("current_thread_ref")
        )
        if compatibility_ref and compatibility_ref in selected_thread_refs:
            continue
        item_ref = _clean_text(raw_item.get("surface_item_ref")) or f"item-{index}"
        evidence_refs = _string_values(raw_item.get("evidence_refs"))
        reacted_post_refs = _string_values(raw_item.get("reacted_post_refs"))
        item_source_refs = _string_values(raw_item.get("source_refs"))
        atom_ids: list[int | str] = []
        for ref in evidence_refs:
            if ref.startswith("atom:"):
                value = ref.removeprefix("atom:")
                atom_ids.extend(_list_values(int(value) if value.isdigit() else value))
        result.append(
            IntelligenceRetrievalItem(
                id=(
                    f"reaction_eligible_unselected:{week_label or 'unknown'}:"
                    f"{_slug(surface)}:{_slug(item_ref)}"
                ),
                item_type="reaction_eligible_unselected",
                week_label=week_label,
                title=_clean_text(raw_item.get("reader_reason_ru")) or item_ref,
                summary=_clean_text(raw_item.get("counterfactual_effect")) or None,
                text=_json_text(dict(raw_item)),
                source_refs=_unique(
                    [
                        *source_refs,
                        *reacted_post_refs,
                        *item_source_refs,
                        *evidence_refs,
                    ]
                ),
                atom_ids=_unique(atom_ids),
                thread_slug=_reaction_thread_slug(compatibility_ref),
                status=_clean_text(raw_item.get("counterfactual_effect")) or None,
                created_at=generated_at,
                updated_at=generated_at,
            )
        )

    for index, raw_item in enumerate(_as_list(effect.get("unconsumed")), start=1):
        if not isinstance(raw_item, Mapping):
            continue
        reaction_ref = _clean_text(raw_item.get("reaction_ref")) or f"event-{index}"
        reason = _clean_text(raw_item.get("reason")) or "snapshot_unverified"
        result.append(
            IntelligenceRetrievalItem(
                id=f"reaction_unconsumed:{week_label or 'unknown'}:{_slug(surface)}:{_slug(reaction_ref)}",
                item_type="reaction_unconsumed",
                week_label=week_label,
                title="Unconsumed reaction signal",
                summary=reason,
                text=_json_text(dict(raw_item)),
                source_refs=_unique([*source_refs, reaction_ref]),
                status=reason,
                created_at=generated_at,
                updated_at=generated_at,
            )
        )
    return result


def _reaction_thread_slug(reference: str) -> str | None:
    clean = _clean_text(reference)
    if not clean:
        return None
    for prefix in ("idea_thread:", "thread:"):
        if clean.startswith(prefix):
            return clean[len(prefix) :] or None
    return clean


def _canonical_contract_items(
    workbook: Mapping[str, Any],
    *,
    week_label: str | None,
    generated_at: str | None,
) -> list[IntelligenceRetrievalItem]:
    contract = workbook.get("intelligence_contract") if isinstance(workbook.get("intelligence_contract"), Mapping) else {}
    if not contract:
        return []
    evidence_by_id = {
        str(item.get("id")): item
        for item in _as_list(contract.get("evidence_items"))
        if isinstance(item, Mapping) and str(item.get("id") or "").strip()
    }
    result: list[IntelligenceRetrievalItem] = []
    for index, evidence in enumerate(evidence_by_id.values(), start=1):
        evidence_id = _clean_text(evidence.get("id")) or f"evidence-{index}"
        source_ref = _clean_text(evidence.get("source_observation_id"))
        result.append(
            IntelligenceRetrievalItem(
                id=f"canonical_evidence:{week_label or 'unknown'}:{evidence_id}",
                item_type="canonical_evidence",
                week_label=week_label,
                title=_clean_text(evidence.get("quote")) or _clean_text(evidence.get("evidence_role")) or f"Evidence item {index}",
                summary=_clean_text(evidence.get("verification_status")) or None,
                text=_join_text(
                    evidence.get("quote"),
                    evidence.get("verified_excerpt"),
                    evidence.get("evidence_role"),
                    evidence.get("evidence_tier"),
                    evidence.get("polarity"),
                    evidence.get("verification_status"),
                ),
                source_refs=[source_ref] if source_ref else [],
                atom_ids=_list_values(evidence.get("atom_ids")),
                confidence=None,
                evidence_tier=_clean_text(evidence.get("evidence_tier")) or None,
                verification_status=_clean_text(evidence.get("verification_status")) or None,
                status=_clean_text(evidence.get("polarity")) or None,
                created_at=generated_at,
                updated_at=generated_at,
            )
        )
    for index, claim in enumerate(_as_list(contract.get("claims")), start=1):
        if not isinstance(claim, Mapping):
            continue
        claim_id = _clean_text(claim.get("id")) or f"claim-{index}"
        evidence_refs = [
            evidence_by_id[ref].get("source_observation_id")
            for ref in [
                *_string_values(claim.get("supporting_evidence_item_ids")),
                *_string_values(claim.get("contradicting_evidence_item_ids")),
            ]
            if ref in evidence_by_id and evidence_by_id[ref].get("source_observation_id")
        ]
        result.append(
            IntelligenceRetrievalItem(
                id=f"canonical_claim:{week_label or 'unknown'}:{claim_id}",
                item_type="canonical_claim",
                week_label=week_label,
                title=_clean_text(claim.get("statement")) or f"Canonical claim {index}",
                summary=_join_text(*_string_values(claim.get("uncertainty_reasons"))) or None,
                text=_join_text(
                    claim.get("statement"),
                    " ".join(_string_values(claim.get("uncertainty_reasons"))),
                    claim.get("verification_state"),
                    claim.get("wording_policy"),
                    claim.get("next_verification_step"),
                ),
                source_refs=_unique(evidence_refs),
                atom_ids=_list_values(claim.get("atom_ids")),
                confidence=_float_or_none(claim.get("confidence_band")),
                evidence_tier="decision_grade" if claim.get("decision_grade") is True else "insufficient_evidence",
                verification_status=_clean_text(claim.get("verification_state")) or None,
                status="decision_grade" if claim.get("decision_grade") is True else "insufficient_evidence",
                created_at=generated_at,
                updated_at=generated_at,
            )
        )
    return result


def _workbook_section_items(
    workbook: Mapping[str, Any],
    *,
    week_label: str | None,
    generated_at: str | None,
    artifact_refs: list[str],
) -> list[IntelligenceRetrievalItem]:
    sections = workbook.get("workbook_sections")
    if isinstance(sections, list):
        section_rows = [section for section in sections if isinstance(section, Mapping)]
    else:
        raw_sections = _as_list(workbook.get("sections"))
        section_rows = [
            {
                "id": _slug(str(title)),
                "title": str(title),
                "title_en": str(title),
                "kind": _slug(str(title)).replace("-", "_"),
            }
            for title in raw_sections
            if str(title).strip()
        ]
    result: list[IntelligenceRetrievalItem] = []
    for section in section_rows:
        section_id = _clean_text(section.get("id")) or _slug(section.get("title") or "section")
        title = _clean_text(section.get("title_en")) or _clean_text(section.get("title")) or section_id
        section_items = _section_payload(workbook, section_id, _clean_text(section.get("kind")))
        text = _json_text(section_items) if section_items else _clean_text(section.get("summary"))
        result.append(
            IntelligenceRetrievalItem(
                id=f"workbook_section:{week_label or 'unknown'}:{section_id}",
                item_type="workbook_section",
                week_label=week_label,
                title=title,
                summary=_section_summary(section_items),
                text=text or title,
                source_refs=artifact_refs,
                atom_ids=_atom_ids_from_objects(section_items),
                status=_clean_text(section.get("kind")) or None,
                created_at=generated_at,
                updated_at=generated_at,
            )
        )
    return result


def _atlas_thread_items(
    workbook: Mapping[str, Any],
    *,
    week_label: str | None,
    generated_at: str | None,
    artifact_refs: list[str],
) -> list[IntelligenceRetrievalItem]:
    navigation = workbook.get("thread_navigation") if isinstance(workbook.get("thread_navigation"), Mapping) else {}
    threads = [item for item in _as_list(navigation.get("threads")) if isinstance(item, Mapping)]
    result: list[IntelligenceRetrievalItem] = []
    for index, thread in enumerate(threads, start=1):
        title = _clean_text(thread.get("title")) or _clean_text(thread.get("slug")) or f"Atlas thread {index}"
        evidence_items = [item for item in _as_list(thread.get("evidence_items")) if isinstance(item, Mapping)]
        source_refs = _unique(
            [
                *artifact_refs,
                *_string_values(thread.get("source_urls")),
                *[
                    source_url
                    for evidence in evidence_items
                    for source_url in _string_values(evidence.get("source_urls"))
                ],
            ]
        )
        atom_ids = _unique(
            [
                *[
                    evidence.get("atom_id")
                    for evidence in evidence_items
                    if evidence.get("atom_id") not in (None, "")
                ],
                *_list_values(thread.get("atom_ids")),
            ]
        )
        result.append(
            IntelligenceRetrievalItem(
                id=f"atlas_thread:{week_label or 'unknown'}:{_slug(thread.get('slug') or title)}",
                item_type="atlas_thread",
                week_label=week_label,
                title=title,
                summary=_clean_text(thread.get("current_understanding")) or None,
                text=_join_text(
                    title,
                    thread.get("current_understanding"),
                    thread.get("change_since_previous_period"),
                    " ".join(_string_values(thread.get("claims"))),
                    " ".join(_string_values(thread.get("contradictions"))),
                    " ".join(_string_values(thread.get("open_questions"))),
                    " ".join(_string_values(thread.get("study_next"))),
                    _json_text(thread.get("source_diversity")),
                    _json_text(thread.get("project_connections")),
                    _json_text(thread.get("decisions")),
                ),
                source_refs=source_refs,
                atom_ids=atom_ids,
                thread_slug=_clean_text(thread.get("slug")) or None,
                confidence=None,
                evidence_tier="atlas_curated_thread",
                verification_status=None,
                status=_clean_text(thread.get("status")) or None,
                created_at=generated_at,
                updated_at=generated_at,
            )
        )
    return result


def _claim_card_items(
    workbook: Mapping[str, Any],
    *,
    week_label: str | None,
    generated_at: str | None,
) -> list[IntelligenceRetrievalItem]:
    cards = [card for card in _as_list(workbook.get("claim_cards")) if isinstance(card, Mapping)]
    result: list[IntelligenceRetrievalItem] = []
    for index, card in enumerate(cards, start=1):
        claim = _clean_text(card.get("claim")) or f"Claim card {index}"
        item_id = _clean_text(card.get("id")) or _slug(claim)
        atom_ids = _list_values(card.get("evidence_atom_ids"))
        result.append(
            IntelligenceRetrievalItem(
                id=f"claim_card:{week_label or 'unknown'}:{item_id}",
                item_type="claim_card",
                week_label=week_label,
                title=claim,
                summary=_clean_text(card.get("caveat")) or None,
                text=_join_text(
                    claim,
                    card.get("evidence_quote"),
                    card.get("caveat"),
                    card.get("next_verification_step"),
                    card.get("wording_policy"),
                ),
                source_refs=_string_values(card.get("source_urls")),
                atom_ids=atom_ids,
                confidence=_float_or_none(card.get("confidence")),
                evidence_tier=_clean_text(card.get("evidence_tier")) or None,
                verification_status=_clean_text(card.get("verification_status")) or None,
                status=_clean_text(card.get("staleness_status")) or None,
                created_at=generated_at,
                updated_at=generated_at,
            )
        )
    return result


def _deep_explanation_items(
    workbook: Mapping[str, Any],
    *,
    week_label: str | None,
    generated_at: str | None,
) -> list[IntelligenceRetrievalItem]:
    cards = [card for card in _as_list(workbook.get("deep_explanation_cards")) if isinstance(card, Mapping)]
    result: list[IntelligenceRetrievalItem] = []
    for index, card in enumerate(cards, start=1):
        title = _clean_text(card.get("title")) or _clean_text(card.get("claim_card_id")) or f"Deep explanation {index}"
        item_id = _clean_text(card.get("id")) or _slug(title)
        result.append(
            IntelligenceRetrievalItem(
                id=f"deep_explanation_card:{week_label or 'unknown'}:{item_id}",
                item_type="deep_explanation_card",
                week_label=week_label,
                title=title,
                summary=_clean_text(card.get("what_is_this")) or None,
                text=_join_text(
                    title,
                    card.get("what_is_this"),
                    card.get("why_now"),
                    card.get("how_it_works"),
                    card.get("where_is_hype"),
                    card.get("what_to_do"),
                    card.get("what_not_to_do"),
                    card.get("what_would_change_my_mind"),
                    card.get("caveat"),
                ),
                source_refs=_string_values(card.get("source_urls")),
                atom_ids=[],
                evidence_tier=_clean_text(card.get("evidence_tier")) or None,
                verification_status=_clean_text(card.get("quote_verification_status")) or None,
                status="explanatory_only" if card.get("explanatory_only") is True else None,
                created_at=generated_at,
                updated_at=generated_at,
            )
        )
    return result


def _action_card_items(
    workbook: Mapping[str, Any],
    *,
    week_label: str | None,
    generated_at: str | None,
) -> list[IntelligenceRetrievalItem]:
    cards = [card for card in _as_list(workbook.get("action_cards")) if isinstance(card, Mapping)]
    result: list[IntelligenceRetrievalItem] = []
    for index, card in enumerate(cards, start=1):
        title = _clean_text(card.get("title")) or f"Action {index}"
        item_id = _clean_text(card.get("id")) or _clean_text(card.get("target_ref")) or _slug(title)
        result.append(
            IntelligenceRetrievalItem(
                id=f"action_card:{week_label or 'unknown'}:{item_id}",
                item_type="action_card",
                week_label=week_label,
                title=title,
                summary=_clean_text(card.get("next_step")) or None,
                text=_join_text(
                    title,
                    card.get("next_step"),
                    card.get("success_criterion"),
                    card.get("kill_condition"),
                    card.get("follow_up_hint"),
                    card.get("outcome_policy"),
                ),
                source_refs=[],
                atom_ids=[],
                project_name=_clean_text(card.get("project")) or None,
                status=_clean_text(card.get("action_kind")) or _clean_text(card.get("scope")) or None,
                created_at=generated_at,
                updated_at=generated_at,
            )
        )
    return result


def _project_diagnostic_items(
    workbook: Mapping[str, Any],
    *,
    week_label: str | None,
    generated_at: str | None,
) -> list[IntelligenceRetrievalItem]:
    diagnostic = workbook.get("project_diagnostic") if isinstance(workbook.get("project_diagnostic"), Mapping) else {}
    suggestions = [item for item in _as_list(diagnostic.get("implementation_suggestions")) if isinstance(item, Mapping)]
    result: list[IntelligenceRetrievalItem] = []
    for index, suggestion in enumerate(suggestions, start=1):
        project = _clean_text(suggestion.get("project")) or None
        title = _clean_text(suggestion.get("title")) or _clean_text(suggestion.get("next_step")) or f"Project action {index}"
        item_id = _clean_text(suggestion.get("id")) or _slug(f"{project or 'project'} {title}")
        result.append(
            IntelligenceRetrievalItem(
                id=f"project_diagnostic:{week_label or 'unknown'}:{item_id}",
                item_type="project_diagnostic",
                week_label=week_label,
                title=title,
                summary=_clean_text(suggestion.get("next_step")) or None,
                text=_join_text(
                    title,
                    suggestion.get("next_step"),
                    suggestion.get("risk_caveat"),
                    " ".join(_string_values(suggestion.get("acceptance_criteria"))),
                    suggestion.get("source_policy"),
                ),
                source_refs=_string_values(suggestion.get("source_urls")),
                atom_ids=_list_values(suggestion.get("source_atom_ids")),
                thread_slug=_clean_text(suggestion.get("thread_slug")) or None,
                project_name=project,
                status=_clean_text(suggestion.get("suggestion_type")) or None,
                created_at=generated_at,
                updated_at=generated_at,
            )
        )
    return result


def _project_learning_projection_items(
    workbook: Mapping[str, Any],
    *,
    week_label: str | None,
    generated_at: str | None,
) -> list[IntelligenceRetrievalItem]:
    projection = (
        workbook.get("project_learning_projection")
        if isinstance(workbook.get("project_learning_projection"), Mapping)
        else {}
    )
    if not projection:
        return []
    project = projection.get("project_intelligence") if isinstance(projection.get("project_intelligence"), Mapping) else {}
    learning = projection.get("learning_intelligence") if isinstance(projection.get("learning_intelligence"), Mapping) else {}
    result: list[IntelligenceRetrievalItem] = []
    project_rows = [
        ("external_signal", _as_list(project.get("external_signals"))),
        ("confirmed_implication", _as_list(project.get("confirmed_implications"))),
        ("weak_watch", _as_list(project.get("weak_watches"))),
        ("rejected_overlap", _as_list(project.get("rejected_overlaps"))),
        ("tiny_pr_idea", _as_list(project.get("tiny_pr_ideas"))),
        ("stale_decision", _as_list(project.get("stale_decisions"))),
        ("research_debt", _as_list(project.get("research_debt"))),
        ("repeated_theme_without_action", _as_list(project.get("repeated_themes_without_action"))),
    ]
    for kind, rows in project_rows:
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, Mapping):
                continue
            title = (
                _clean_text(row.get("title"))
                or _clean_text(row.get("thread_title"))
                or _clean_text(row.get("theme"))
                or _clean_text(row.get("term"))
                or _clean_text(row.get("description"))
                or f"Project intelligence {index}"
            )
            project_name = _clean_text(row.get("project")) or None
            item_id = _clean_text(row.get("id")) or _slug(f"{kind} {project_name or ''} {title}")
            result.append(
                IntelligenceRetrievalItem(
                    id=f"project_intelligence:{week_label or 'unknown'}:{kind}:{item_id}",
                    item_type="project_intelligence",
                    week_label=week_label,
                    title=title,
                    summary=_clean_text(row.get("confirmation_state"))
                    or _clean_text(row.get("reason"))
                    or _clean_text(row.get("debt_type"))
                    or kind,
                    text=_join_text(
                        title,
                        row.get("why"),
                        row.get("next_step"),
                        row.get("reason"),
                        row.get("needed_evidence"),
                        row.get("description"),
                        row.get("source_policy"),
                        _json_text(row.get("acceptance_criteria")),
                    ),
                    source_refs=_string_values(row.get("source_refs") or row.get("source_urls") or row.get("evidence_urls")),
                    atom_ids=_list_values(row.get("source_atom_ids") or row.get("atom_ids")),
                    thread_slug=_clean_text(row.get("thread_slug")) or None,
                    project_name=project_name,
                    evidence_tier="project_learning_projection",
                    verification_status=_clean_text(row.get("confirmation_state")) or None,
                    status=kind,
                    created_at=generated_at,
                    updated_at=generated_at,
                )
            )
    for index, objective in enumerate(_as_list(learning.get("objectives")), start=1):
        if not isinstance(objective, Mapping):
            continue
        title = _clean_text(objective.get("topic")) or f"Learning objective {index}"
        objective_id = _clean_text(objective.get("id")) or _slug(title)
        stage = _clean_text(objective.get("stage")) or "unknown"
        result.append(
            IntelligenceRetrievalItem(
                id=f"learning_objective:{week_label or 'unknown'}:{objective_id}",
                item_type="learning_objective",
                week_label=week_label,
                title=title,
                summary=stage,
                text=_join_text(
                    title,
                    objective.get("stage"),
                    objective.get("target_stage"),
                    objective.get("stage_evidence"),
                    objective.get("feedback_state"),
                    objective.get("mastery_claim"),
                ),
                source_refs=_string_values(objective.get("source_refs")),
                atom_ids=_list_values(objective.get("source_atom_ids")),
                evidence_tier="learning_stage_projection",
                verification_status=_clean_text(objective.get("feedback_state")) or None,
                status=stage,
                created_at=generated_at,
                updated_at=generated_at,
            )
        )
    return result


def _mvp_item(
    payload: Mapping[str, Any],
    week_label: str | None,
    *,
    authoritative: bool = False,
) -> IntelligenceRetrievalItem:
    raw_candidate = (
        _clean_text(payload.get("selected_candidate"))
        or _clean_text(payload.get("selected_title"))
        or "MVP Radar status"
    )
    reader_state = _clean_text(payload.get("reader_state")) or "unbound_legacy"
    strict_available = (
        authoritative
        and payload.get("schema_version") == "mvp_radar_reader.v1"
        and reader_state == "available"
    )
    strict_no_candidate = (
        authoritative
        and payload.get("schema_version") == "mvp_radar_reader.v1"
        and reader_state == "no_candidate"
    )
    candidate = (
        raw_candidate
        if strict_available
        else (
            "MVP Radar: кандидат не выбран"
            if strict_no_candidate
            else f"Диагностика MVP Radar — {raw_candidate}"
        )
    )
    source_path = _clean_text(payload.get("source_path"))
    candidate_record = (
        payload.get("candidate") if isinstance(payload.get("candidate"), Mapping) else {}
    )
    candidate_ref = _clean_text(candidate_record.get("candidate_id")) or _slug(
        raw_candidate
    )
    recommendation = _clean_text(payload.get("recommendation")) or _clean_text(
        payload.get("dossier_status")
    )
    reason = _clean_text(payload.get("decision_reason_ru"))
    strict_decision = _clean_text(payload.get("reader_decision"))
    decision_label = {
        "investigate": "Продолжить проверку кандидата.",
        "reject": "Отклонить кандидата.",
        "build_allowed": "Radar разрешил сборку.",
    }.get(strict_decision, "Решение требует дополнительной проверки.")
    summary = (
        _reader_radar_text(reason, "Основание решения") or decision_label
        if strict_available
        else (
            reason or "Radar завершил проверку без выбора кандидата."
            if strict_no_candidate
            else reason or "Решение Radar недоступно."
        )
    )
    decision_text = (
        decision_label
        if strict_available
        else (
            "Radar успешно завершил запуск; кандидат для решения не выбран."
            if strict_no_candidate
            else _join_text(
                "Решение Radar недоступно; показан только диагностический контекст.",
                f"Диагностический кандидат: {raw_candidate}" if raw_candidate else "",
            )
        )
    )
    return IntelligenceRetrievalItem(
        id=f"mvp_dossier:{week_label or 'unknown'}:{_slug(candidate_ref)}",
        item_type="mvp_dossier",
        week_label=week_label,
        title=candidate,
        summary=summary or None,
        text=_join_text(
            candidate,
            decision_text,
            _reader_radar_text(reason, "Основание решения"),
            *[
                _reader_radar_text(value, "Пробел доказательств")
                for value in _string_values(payload.get("missing_evidence"))
            ],
            *[
                _reader_radar_text(value, "Следующая проверка")
                for value in _string_values(payload.get("next_validation"))
            ],
            _reader_radar_text(
                payload.get("change_condition"),
                "Условие изменения решения",
            ),
            *[
                _reader_radar_text(value, "Критерий остановки")
                for value in _string_values(payload.get("kill_criteria"))
            ],
            (
                "Связанных внешних доказательств: "
                + str(len(_as_list(payload.get("matched_external_proof"))))
                if strict_available
                else ""
            ),
            (
                "Отделённых контекстных записей: "
                + str(len(_as_list(payload.get("unmatched_context"))))
            ),
        ),
        source_refs=[source_path] if source_path else [],
        atom_ids=[],
        status=(
            _clean_text(payload.get("dossier_status")) or recommendation or None
            if strict_available
            else "no_candidate"
            if strict_no_candidate
            else reader_state
        ),
        created_at=None,
        updated_at=None,
    )


def _reader_radar_text(value: object, label: str) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    if CYRILLIC_RE.search(text):
        return (
            text.replace(
                "Добавить совпавший свежий KIR Knowledge Thread для кандидата.",
                "Добавить свежую тему знаний, совпадающую с кандидатом.",
            )
            .replace(
                "Обновить совпавший KIR Knowledge Thread свежими данными.",
                "Обновить совпадающую тему знаний свежими данными.",
            )
            .replace(
                "Обновить совпавшую KIR-провенанс и повторить тот же bounded Radar run.",
                "Обновить происхождение совпадающей темы знаний и повторить тот же ограниченный запуск Radar.",
            )
            .replace("KIR Knowledge Thread", "тему знаний с проверяемым происхождением")
            .replace("KIR-провенанс", "происхождение темы знаний")
            .replace("KIR-тему", "тему знаний")
            .replace("KIR", "внутренней темы знаний")
            .replace("Knowledge Thread", "тему знаний")
            .replace("bounded Radar run", "ограниченный запуск Radar")
            .replace("manifest-bound", "связанное с манифестом")
        )
    return f"{label} сохранено в техническом аудите Radar."


def _reader_confidence_label(value: object) -> str:
    return {
        "low": "Уверенность: низкая.",
        "medium": "Уверенность: средняя.",
        "high": "Уверенность: высокая.",
    }.get(_clean_text(value), "")


def _knowledge_atom_items(
    connection: sqlite3.Connection,
    *,
    week_label: str | None,
) -> list[IntelligenceRetrievalItem]:
    if not _table_exists(connection, "knowledge_atoms"):
        return []
    try:
        atoms = fetch_knowledge_atoms(connection, week_label=week_label, limit=200) if week_label else fetch_knowledge_atoms(connection, limit=200)
    except sqlite3.Error:
        return []
    result: list[IntelligenceRetrievalItem] = []
    for atom in atoms:
        result.append(
            IntelligenceRetrievalItem(
                id=f"knowledge_atom:{atom.get('id')}",
                item_type="knowledge_atom",
                week_label=_clean_text(atom.get("week_label")) or None,
                title=_clean_text(atom.get("claim")) or f"Knowledge atom {atom.get('id')}",
                summary=_clean_text(atom.get("summary")) or None,
                text=_join_text(
                    atom.get("claim"),
                    atom.get("summary"),
                    atom.get("why_it_matters"),
                    atom.get("evidence_quote"),
                    " ".join(_string_values(atom.get("entities"))),
                    " ".join(_string_values(atom.get("tools"))),
                    " ".join(_string_values(atom.get("models"))),
                    " ".join(_string_values(atom.get("practices"))),
                ),
                source_refs=_string_values(atom.get("source_urls")),
                atom_ids=[atom.get("id")] if atom.get("id") is not None else [],
                confidence=_float_or_none(atom.get("confidence")),
                evidence_tier=_clean_text(atom.get("atom_type")) or None,
                verification_status=None,
                status=_clean_text(atom.get("staleness_status")) or None,
                created_at=_clean_text(atom.get("created_at")) or None,
                updated_at=_clean_text(atom.get("updated_at")) or _clean_text(atom.get("last_seen_at")) or None,
            )
        )
    return result


def _idea_thread_items(
    connection: sqlite3.Connection,
    *,
    week_label: str | None,
) -> list[IntelligenceRetrievalItem]:
    if not _table_exists(connection, "idea_threads") or not _table_exists(connection, "idea_thread_atoms"):
        return []
    try:
        threads = fetch_idea_threads(connection, limit=200)
    except sqlite3.Error:
        return []
    result: list[IntelligenceRetrievalItem] = []
    for thread in threads:
        if week_label and not _thread_in_week_window(thread, week_label):
            continue
        try:
            atoms = fetch_idea_thread_atoms(connection, thread_id=int(thread["id"]), limit=50)
        except (KeyError, sqlite3.Error, TypeError, ValueError):
            atoms = []
        source_refs = _unique(
            url
            for atom in atoms
            for url in _string_values(atom.get("source_urls"))
        )
        atom_ids = [atom.get("id") for atom in atoms if atom.get("id") is not None]
        result.append(
            IntelligenceRetrievalItem(
                id=f"idea_thread:{thread.get('slug')}",
                item_type="idea_thread",
                week_label=week_label,
                title=_clean_text(thread.get("title")) or _clean_text(thread.get("slug")) or "Idea thread",
                summary=_clean_text(thread.get("summary")) or None,
                text=_join_text(
                    thread.get("title"),
                    thread.get("summary"),
                    " ".join(_string_values(thread.get("current_claims"))),
                    " ".join(_string_values(thread.get("superseded_claims"))),
                    " ".join(_string_values(thread.get("contradictions"))),
                    " ".join(_clean_text(atom.get("claim")) for atom in atoms),
                ),
                source_refs=source_refs,
                atom_ids=atom_ids,
                thread_slug=_clean_text(thread.get("slug")) or None,
                confidence=None,
                status=_clean_text(thread.get("status")) or None,
                created_at=_clean_text(thread.get("created_at")) or _clean_text(thread.get("first_seen_at")) or None,
                updated_at=_clean_text(thread.get("updated_at")) or _clean_text(thread.get("last_seen_at")) or None,
            )
        )
    return result


def _canonical_idea_thread_items(
    connection: sqlite3.Connection,
    *,
    week_label: str | None,
) -> list[IntelligenceRetrievalItem]:
    """Expose versioned IRX-4 identities beside unchanged raw Idea Threads."""

    if not _table_exists(connection, "canonical_idea_threads"):
        return []
    from db.canonical_idea_threads import fetch_canonical_threads

    as_of = None
    if week_label:
        try:
            _start, end = _week_bounds(week_label)
        except ValueError:
            return []
        as_of = end.isoformat().replace("+00:00", "Z")
    try:
        threads = fetch_canonical_threads(
            connection,
            as_of=as_of,
            limit=200,
            include_atoms=True,
        )
    except sqlite3.Error:
        return []
    result: list[IntelligenceRetrievalItem] = []
    for thread in threads:
        canonical_id = _clean_text(thread.get("canonical_thread_id"))
        stable_slug = _clean_text(thread.get("stable_slug"))
        if not canonical_id or not stable_slug:
            continue
        aliases: list[str] = []
        for raw_alias in _as_list(
            thread.get("aliases") or thread.get("raw_thread_aliases")
        ):
            if isinstance(raw_alias, Mapping):
                value = _clean_text(
                    raw_alias.get("alias_value") or raw_alias.get("value")
                )
            else:
                value = _clean_text(raw_alias)
            if value and value not in aliases:
                aliases.append(value)
        atoms = [
            atom
            for atom in _as_list(thread.get("atoms"))
            if isinstance(atom, Mapping)
        ]
        atom_ids = _unique(
            [
                *_list_values(thread.get("atom_ids")),
                *[
                    atom.get("id") or atom.get("atom_id")
                    for atom in atoms
                    if atom.get("id") or atom.get("atom_id")
                ],
            ]
        )
        source_refs = _unique(
            [
                *_string_values(thread.get("source_urls")),
                *[
                    url
                    for atom in atoms
                    for url in _string_values(atom.get("source_urls"))
                ],
            ]
        )
        title = (
            _clean_text(thread.get("title_ru"))
            or _clean_text(thread.get("title_en"))
            or stable_slug
        )
        result.append(
            IntelligenceRetrievalItem(
                id=f"canonical_thread:{stable_slug}",
                item_type="canonical_thread",
                week_label=week_label,
                title=title,
                summary=_clean_text(thread.get("thesis")) or None,
                text=_join_text(
                    title,
                    thread.get("title_en"),
                    thread.get("thesis"),
                    canonical_id,
                    stable_slug,
                    " ".join(aliases),
                    " ".join(_string_values(thread.get("entities"))),
                    " ".join(_string_values(thread.get("merged_from"))),
                    " ".join(_string_values(thread.get("split_from"))),
                    " ".join(_clean_text(atom.get("claim")) for atom in atoms),
                    thread.get("curator_version"),
                ),
                source_refs=source_refs,
                atom_ids=atom_ids,
                thread_slug=stable_slug,
                evidence_tier=_clean_text(thread.get("evidence_maturity")) or None,
                status=_clean_text(thread.get("status")) or None,
                created_at=_clean_text(thread.get("first_seen_at")) or None,
                updated_at=_clean_text(thread.get("last_seen_at")) or None,
            )
        )
    return result


def _feedback_summary_items(
    connection: sqlite3.Connection,
    *,
    week_label: str | None,
) -> list[IntelligenceRetrievalItem]:
    if not _table_exists(connection, "ai_report_feedback_events"):
        return []
    try:
        summary = summarize_ai_report_feedback(connection, week_label=week_label, limit=100)
    except sqlite3.Error:
        return []
    if int(summary.get("event_count") or 0) <= 0:
        return []
    changes = summary.get("feedback_changes") or {}
    recent = [event for event in _as_list(summary.get("recent_events")) if isinstance(event, Mapping)]
    source_refs = _unique(event.get("source_url") for event in recent if event.get("source_url"))
    return [
        IntelligenceRetrievalItem(
            id=f"feedback_summary:{week_label or 'all'}",
            item_type="feedback_summary",
            week_label=week_label,
            title=f"Feedback Summary {week_label or 'all'}",
            summary=_clean_text(changes.get("summary")) or None,
            text=_join_text(
                changes.get("summary"),
                " ".join(_string_values(changes.get("items"))),
                _json_text(summary.get("counts_by_feedback")),
                _json_text(recent),
            ),
            source_refs=source_refs,
            atom_ids=[],
            status=_clean_text(changes.get("status")) or None,
        )
    ]


def _strategy_reviewer_items(
    connection: sqlite3.Connection,
    *,
    week_label: str | None,
    weekly_run_root: str | Path,
) -> list[IntelligenceRetrievalItem]:
    if not _table_exists(connection, "ai_report_feedback_events"):
        return []
    try:
        review = build_strategy_review(
            connection,
            week_label=week_label,
            weekly_run_root=weekly_run_root,
        )
    except sqlite3.Error:
        return []
    suggestions = review.get("suggestions") or {}
    tasks = [task for task in _as_list(review.get("codex_tasks")) if isinstance(task, Mapping)]
    proposals = [
        item
        for item in _as_list(review.get("reaction_pattern_proposals"))
        if isinstance(item, Mapping)
    ]
    title = f"Strategy Reviewer {week_label or 'all'}"
    return [
        IntelligenceRetrievalItem(
            id=f"strategy_reviewer_note:{week_label or 'all'}",
            item_type="strategy_reviewer_note",
            week_label=week_label,
            title=title,
            summary=(
                f"{len(proposals)} unapproved reaction pattern proposal(s)."
                if proposals
                else _join_text(*(suggestions.get("test_next_week") or [])) or None
            ),
            text=_join_text(
                _json_text(suggestions),
                _json_text(review.get("memory_only_updates")),
                _json_text(review.get("approval_required")),
                _json_text(tasks),
                _json_text(proposals),
            ),
            source_refs=[],
            atom_ids=[],
            status="advisory_only",
            created_at=_clean_text(review.get("generated_at")) or None,
            updated_at=_clean_text(review.get("generated_at")) or None,
        )
    ]


def _candidate_workbook_paths(
    *,
    week_label: str | None,
    output_root: str | Path | None,
    visual_output_root: str | Path | None,
    ai_output_root: str | Path | None,
) -> list[tuple[Path, str]]:
    visual_dir, ai_dir = _workbook_dirs(
        output_root=output_root,
        visual_output_root=visual_output_root,
        ai_output_root=ai_output_root,
    )
    atlas_dir, brief_dir = _split_artifact_dirs(output_root=output_root)
    clean_week = str(week_label or "").strip()
    if clean_week:
        return [
            (visual_dir / f"{clean_week}.visual.json", "visual_workbook"),
            (brief_dir / f"{clean_week}.weekly-brief.json", "weekly_intelligence_brief"),
            (atlas_dir / f"{clean_week}.knowledge-atlas.json", "knowledge_atlas"),
            (ai_dir / f"{clean_week}.json", "ai_intelligence_report"),
        ]
    candidates: list[tuple[str, int, float, Path, str]] = []
    for path in visual_dir.glob("*.visual.json") if visual_dir.exists() else ():
        week = _week_from_path(path)
        if week:
            candidates.append((week, 3, _mtime(path), path, "visual_workbook"))
    for path in brief_dir.glob("*.weekly-brief.json") if brief_dir.exists() else ():
        week = _week_from_path(path)
        if week:
            candidates.append((week, 2, _mtime(path), path, "weekly_intelligence_brief"))
    for path in atlas_dir.glob("*.knowledge-atlas.json") if atlas_dir.exists() else ():
        week = _week_from_path(path)
        if week:
            candidates.append((week, 1, _mtime(path), path, "knowledge_atlas"))
    for path in ai_dir.glob("*.json") if ai_dir.exists() else ():
        week = _week_from_path(path)
        if week:
            candidates.append((week, 0, _mtime(path), path, "ai_intelligence_report"))
    candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return [(path, kind) for _week, _priority, _mtime_value, path, kind in candidates]


def _candidate_mvp_paths(
    week_label: str,
    *,
    output_root: str | Path | None,
    mvp_output_root: str | Path | None,
    radar_output_root: str | Path | None,
) -> list[Path]:
    mvp_dir, radar_dir = _mvp_dirs(
        output_root=output_root,
        mvp_output_root=mvp_output_root,
        radar_output_root=radar_output_root,
    )
    return [
        mvp_dir / f"mvp-weekly-{week_label}.json",
        mvp_dir / f"{week_label}.json",
        radar_dir / f"mvp-weekly-{week_label}.json",
    ]


def _workbook_dirs(
    *,
    output_root: str | Path | None,
    visual_output_root: str | Path | None,
    ai_output_root: str | Path | None,
) -> tuple[Path, Path]:
    root = Path(output_root) if output_root is not None else DEFAULT_OUTPUT_ROOT
    visual = Path(visual_output_root) if visual_output_root is not None else root / "ai_visual_intelligence"
    ai = Path(ai_output_root) if ai_output_root is not None else root / "ai_intelligence"
    return visual, ai


def _split_artifact_dirs(*, output_root: str | Path | None) -> tuple[Path, Path]:
    if output_root is None:
        return DEFAULT_KNOWLEDGE_ATLAS_OUTPUT_DIR, DEFAULT_WEEKLY_BRIEF_OUTPUT_DIR
    root = Path(output_root) if output_root is not None else DEFAULT_OUTPUT_ROOT
    return root / "knowledge_atlas", root / "weekly_intelligence_briefs"


def _mvp_dirs(
    *,
    output_root: str | Path | None,
    mvp_output_root: str | Path | None,
    radar_output_root: str | Path | None,
) -> tuple[Path, Path]:
    root = Path(output_root) if output_root is not None else DEFAULT_OUTPUT_ROOT
    mvp = Path(mvp_output_root) if mvp_output_root is not None else root / "mvp_weekly"
    radar = (
        Path(radar_output_root)
        if radar_output_root is not None
        else (root / "mvp_weekly" if output_root is not None else DEFAULT_RADAR_OUTPUT_DIR)
    )
    return mvp, radar


def _public_item_dict(item: IntelligenceRetrievalItem, *, score: float | None) -> dict:
    return {
        "id": item.id,
        "item_type": item.item_type,
        "week_label": item.week_label,
        "title": item.title,
        "summary": item.summary,
        "text": item.text,
        "source_refs": list(item.source_refs or []),
        "atom_ids": list(item.atom_ids or []),
        "thread_slug": item.thread_slug,
        "project_name": item.project_name,
        "score": score,
        "evidence_tier": item.evidence_tier,
        "verification_status": item.verification_status,
    }


def _matches_filters(item: IntelligenceRetrievalItem, filters: Mapping[str, Any]) -> bool:
    for key in ("week_label", "item_type", "project_name", "thread_slug", "status"):
        value = filters.get(key)
        if value in (None, "", [], ()):
            continue
        item_value = getattr(item, key)
        accepted = {_normalize_filter_value(candidate) for candidate in _as_list(value)}
        if _normalize_filter_value(item_value) not in accepted:
            return False
    return True


def _search_score(item: IntelligenceRetrievalItem, query: str, tokens: list[str]) -> float:
    if not tokens:
        return 0.0
    title = (item.title or "").lower()
    summary = (item.summary or "").lower()
    text = (item.text or "").lower()
    item_id = item.id.lower()
    phrase = str(query or "").strip().lower()
    score = 0.0
    if phrase:
        if phrase in title:
            score += 8.0
        if phrase in summary:
            score += 4.0
        if phrase in text:
            score += 2.0
    for token in tokens:
        if token in title:
            score += 5.0
        if token in summary:
            score += 3.0
        if token in text:
            score += 1.0
        if token in item_id:
            score += 0.5
    return score


def _query_tokens(query: str) -> list[str]:
    seen: list[str] = []
    for match in TOKEN_RE.findall(str(query or "").lower()):
        if match not in seen:
            seen.append(match)
    return seen


def _optional_readonly_connection(db_path: object):
    class _ConnectionContext:
        def __init__(self, path_value: object) -> None:
            self.path_value = path_value
            self.connection: sqlite3.Connection | None = None

        def __enter__(self) -> sqlite3.Connection | None:
            if not self.path_value:
                return None
            path = Path(str(self.path_value))
            if not path.exists():
                return None
            uri = f"file:{quote(str(path.resolve()), safe='/')}?mode=ro"
            try:
                self.connection = sqlite3.connect(uri, uri=True)
                self.connection.row_factory = sqlite3.Row
                return self.connection
            except sqlite3.Error:
                return None

        def __exit__(self, exc_type, exc, traceback) -> None:
            if self.connection is not None:
                self.connection.close()

    return _ConnectionContext(db_path)


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    try:
        row = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            LIMIT 1
            """,
            (table_name,),
        ).fetchone()
    except sqlite3.Error:
        return False
    return row is not None


def _thread_in_week_window(thread: Mapping[str, Any], week_label: str) -> bool:
    try:
        start, end = _week_bounds(week_label)
    except ValueError:
        return True
    del start
    last_seen = _parse_iso(thread.get("last_seen_at"))
    if last_seen is None:
        return True
    return last_seen < end


def _week_bounds(week_label: str) -> tuple[datetime, datetime]:
    year_str, week_str = str(week_label).split("-W", maxsplit=1)
    start_date = date.fromisocalendar(int(year_str), int(week_str), 1)
    start = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    return start, start + timedelta(days=7)


def _parse_iso(value: object) -> datetime | None:
    text = _clean_text(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _section_payload(workbook: Mapping[str, Any], section_id: str, kind: str) -> object:
    normalized = f"{section_id} {kind}".replace("-", "_")
    if "thread_navigation" in normalized:
        return workbook.get("thread_navigation") or {}
    if "project_learning" in normalized:
        return workbook.get("project_learning_projection") or {}
    for section in _as_list(workbook.get("artifact_sections")):
        if not isinstance(section, Mapping):
            continue
        if _clean_text(section.get("id")) == section_id:
            return section
        if kind and _clean_text(section.get("kind")) == kind:
            return section
    if "decision" in normalized:
        return workbook.get("decision_cards") or []
    if "strong" in normalized:
        return workbook.get("claim_cards") or []
    if "deep" in normalized:
        return workbook.get("deep_explanation_cards") or []
    if "project" in normalized:
        diagnostic = workbook.get("project_diagnostic") if isinstance(workbook.get("project_diagnostic"), Mapping) else {}
        return {
            "confirmed_leads": diagnostic.get("confirmed_leads") or [],
            "project_watch": diagnostic.get("project_watch") or [],
            "implementation_suggestions": diagnostic.get("implementation_suggestions") or [],
        }
    if "mvp" in normalized:
        return workbook.get("mvp_radar") or {}
    if "read" in normalized or "try" in normalized or "build" in normalized or "action" in normalized:
        return workbook.get("action_cards") or workbook.get("actions") or []
    if "feedback" in normalized:
        return workbook.get("feedback_targets") or []
    return []


def _section_summary(section_items: object) -> str | None:
    if isinstance(section_items, Mapping):
        values = [
            _section_summary(value)
            for value in section_items.values()
            if value not in (None, "", [], {})
        ]
        return next((value for value in values if value), None)
    for item in _as_list(section_items):
        if isinstance(item, Mapping):
            for key in ("title", "claim", "summary", "next_step", "recommendation"):
                text = _clean_text(item.get(key))
                if text:
                    return text
        else:
            text = _clean_text(item)
            if text:
                return text
    return None


def _atom_ids_from_objects(value: object) -> list[int | str]:
    ids: list[int | str] = []
    if isinstance(value, Mapping):
        for key in ("evidence_atom_ids", "source_atom_ids", "atom_ids"):
            ids.extend(_list_values(value.get(key)))
        for nested in value.values():
            ids.extend(_atom_ids_from_objects(nested))
    elif isinstance(value, list):
        for item in value:
            ids.extend(_atom_ids_from_objects(item))
    return _unique(ids)


def _artifact_source_refs(workbook: Mapping[str, Any]) -> list[str]:
    paths = workbook.get("_artifact_paths") if isinstance(workbook.get("_artifact_paths"), Mapping) else {}
    return _unique([paths.get("html"), paths.get("json"), workbook.get("html_path"), workbook.get("json_path")])


def _artifact_week_label(workbook: Mapping[str, Any]) -> str | None:
    paths = workbook.get("_artifact_paths") if isinstance(workbook.get("_artifact_paths"), Mapping) else {}
    for value in (paths.get("json"), paths.get("html"), workbook.get("json_path"), workbook.get("html_path")):
        match = WEEK_RE.search(str(value or ""))
        if match:
            return match.group("week")
    return None


def _html_path_for_workbook(path: Path, payload: Mapping[str, Any], artifact_kind: str) -> Path | None:
    html_path = _clean_text(payload.get("html_path"))
    if html_path:
        return Path(html_path)
    if artifact_kind == "visual_workbook":
        return path.with_name(path.name.replace(".visual.json", ".visual.html"))
    if artifact_kind == "ai_intelligence_report":
        return path.with_suffix(".html")
    if artifact_kind == "knowledge_atlas":
        return path.with_name(path.name.replace(".knowledge-atlas.json", ".knowledge-atlas.html"))
    if artifact_kind == "weekly_intelligence_brief":
        return path.with_name(path.name.replace(".weekly-brief.json", ".weekly-brief.html"))
    return None


def _read_json_dict(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        if path.stat().st_size > MAX_RETRIEVAL_JSON_BYTES:
            return None
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_json_constant,
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        RecursionError,
        OverflowError,
    ):
        return None
    return payload if isinstance(payload, dict) else None


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _week_from_path(path: Path) -> str | None:
    match = WEEK_RE.search(path.name)
    return match.group("week") if match else None


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _as_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _string_values(value: object) -> list[str]:
    return _unique(_clean_text(item) for item in _as_list(value) if _clean_text(item))


def _list_values(value: object) -> list[int | str]:
    result: list[int | str] = []
    for item in _as_list(value):
        if item is None:
            continue
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            result.append(item)
            continue
        text = _clean_text(item)
        if text:
            result.append(text)
    return _unique(result)


def _unique(values: Iterable[Any]) -> list:
    result = []
    seen = set()
    for value in values:
        if value in (None, ""):
            continue
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _join_text(*values: object) -> str:
    parts = []
    for value in values:
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (dict, list, tuple)):
            text = _json_text(value)
        else:
            text = _clean_text(value)
        if text:
            parts.append(text)
    return " ".join(parts)


def _json_text(value: object) -> str:
    if value in (None, "", [], {}):
        return ""
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return _clean_text(value)


def _slug(value: object) -> str:
    text = _clean_text(value).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return slug[:80] or "item"


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_filter_value(value: object) -> str:
    return _clean_text(value).lower()


def _dedupe_items(items: Iterable[IntelligenceRetrievalItem]) -> list[IntelligenceRetrievalItem]:
    result: list[IntelligenceRetrievalItem] = []
    positions: dict[str, int] = {}
    for item in items:
        if item.id in positions:
            # Canonical DB rows are appended after artifact projections and
            # carry the complete as-of alias/atom/source search text.  Prefer
            # that richer projection while keeping one stable retrieval ref.
            if item.item_type == "canonical_thread":
                result[positions[item.id]] = item
            continue
        positions[item.id] = len(result)
        result.append(item)
    return result

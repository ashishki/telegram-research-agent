"""Deterministic compatibility adapter for the detailed Knowledge Atlas V1.

The Audit Explorer is deliberately not a second intelligence renderer.  It
keeps the detailed V1 Atlas as the technical surface, binds it to immutable
source descriptors, and adds stable anchors for every V1 thread-navigation
record.  Publication, filesystem trust, and alias selection belong to the
calling package loader.
"""

from __future__ import annotations

import copy
import hashlib
import html
import json
import math
import os
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Mapping, Sequence
from urllib.parse import unquote, urlsplit

from output.weekly_run_manifest import MANIFEST_SCHEMA_VERSION


AUDIT_EXPLORER_SCHEMA_VERSION = "knowledge_audit_explorer.v1"
AUDIT_EXPLORER_SURFACE = "knowledge_audit_explorer"
AUDIT_EXPLORER_RENDERER_VERSION = "knowledge_audit_explorer.renderer.v1"
V1_ATLAS_SCHEMA_VERSION = "split_ai_report.v1"
V1_ATLAS_ARTIFACT_TYPE = "knowledge_atlas"
V1_THREAD_NAVIGATION_SCHEMA_VERSION = "knowledge_atlas_thread_navigation.v1"

TECHNICAL_NOTICE_RU = (
    "Knowledge Audit Explorer — техническая поверхность для проверки исходных "
    "тем, доказательств, идентификаторов и происхождения данных. Она может быть "
    "длинной и не является читательским Knowledge Atlas V2."
)

_MAX_JSON_BYTES = 8_000_000
_MAX_HTML_BYTES = 8_000_000
_MAX_RAW_THREADS = 64
_MAX_CANONICAL_THREADS = 12
_MAX_NAVIGATION_THREADS = 12
_MAX_DEEP_LINKS = _MAX_NAVIGATION_THREADS + _MAX_CANONICAL_THREADS
_MAX_TEXT = 20_000
_MAX_PATH = 4_096
_MAX_SOURCE_SIZE = 8_000_000

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RAW_ANCHOR_RE = re.compile(r"^atlas-thread-[a-z0-9][a-z0-9-]{0,239}$")
_CANONICAL_ANCHOR_RE = re.compile(r"^canonical-thread-[a-z0-9][a-z0-9-]{0,119}$")
_STABLE_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_AUDIT_HTML_FILENAME = "knowledge-audit-explorer.v1.html"
_AUDIT_JSON_FILENAME = "knowledge-audit-explorer.v1.json"
_SAFE_HTML_TAGS = {
    "a",
    "article",
    "aside",
    "b",
    "body",
    "br",
    "code",
    "details",
    "div",
    "h1",
    "h2",
    "h3",
    "h4",
    "head",
    "header",
    "html",
    "li",
    "main",
    "meta",
    "nav",
    "ol",
    "p",
    "section",
    "span",
    "strong",
    "style",
    "summary",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "title",
    "tr",
    "ul",
}
_GLOBAL_HTML_ATTRIBUTES = {
    "aria-label",
    "class",
    "data-run-status",
    "data-thread-ref",
    "id",
    "role",
}
_TAG_HTML_ATTRIBUTES = {
    "a": {"href"},
    "aside": {"style"},
    "html": {"lang"},
    "meta": {"charset", "content", "name"},
    "span": {"style"},
}
_SAFE_BANNER_STYLE = (
    "max-width:1180px;margin:16px auto;padding:16px 24px;"
    "border:2px solid #a16207;background:#fffbeb"
)
_V1_STYLESHEET_SHA256 = (
    "ba665cef109f0ff22ba8201b3ae85d2e4843377a142d487bc220231462a2aa01"
)

_ROOT_FIELDS = {
    "schema_version",
    "surface",
    "renderer_version",
    "source_schema_version",
    "run_id",
    "generated_at",
    "period_mode",
    "reporting_period",
    "as_of",
    "source_run_status",
    "run_status",
    "partial",
    "technical_notice_ru",
    "thread_navigation",
    "raw_threads",
    "canonical_threads",
    "canonical_thread_snapshot",
    "raw_thread_count",
    "canonical_thread_count",
    "deep_links",
    "source_artifacts",
    "artifact_paths",
    "technical_refs",
}
_PERIOD_FIELDS = {
    "reporting_week",
    "analysis_period_start",
    "analysis_period_end",
}
_SOURCE_ARTIFACT_FIELDS = {"manifest", "v1_atlas_html", "v1_atlas_json"}
_SOURCE_DESCRIPTOR_FIELDS = {"path", "sha256", "size"}
_ARTIFACT_PATH_FIELDS = {"html", "json"}
_TECHNICAL_REF_FIELDS = {
    "manifest_path",
    "v1_atlas_html_path",
    "v1_atlas_json_path",
}
_DEEP_LINK_FIELDS = {"thread_ref", "title", "anchor", "href"}
_NAVIGATION_FIELDS = {
    "schema_version",
    "week_label",
    "thread_count",
    "source_atom_count",
    "threads",
    "bounded_context_note",
}
_NAVIGATION_THREAD_FIELDS = {
    "id",
    "slug",
    "title",
    "status",
    "maturity",
    "momentum_30d",
    "evidence_growth",
    "current_understanding",
    "change_since_previous_period",
    "timeline",
    "claims",
    "evidence_items",
    "contradictions",
    "superseded_claims",
    "source_diversity",
    "project_connections",
    "decisions",
    "open_questions",
    "study_next",
    "source_urls",
}
_RAW_THREAD_FIELDS = {
    "id",
    "thread_slug",
    "title",
    "status",
    "atom_ids",
    "claim_ids",
    "evidence_item_ids",
    "previous_state",
    "current_state",
    "delta_basis",
    "new_evidence_atom_ids",
    "momentum_vs_evidence",
    "contradictions",
    "merge_split_audit_status",
}
_CANONICAL_THREAD_FIELDS = {
    "canonical_thread_id",
    "stable_slug",
    "title_ru",
    "title_en",
    "thesis",
    "status",
    "first_seen_at",
    "last_seen_at",
    "as_of",
    "evidence_maturity",
    "operator_interest",
    "aliases",
    "raw_thread_aliases",
    "merged_from",
    "merged_into",
    "split_from",
    "split_into",
    "lineage",
    "raw_thread_ids",
    "raw_thread_refs",
    "atom_ids",
    "source_post_ids",
    "source_urls",
    "source_refs",
    "current_claims",
    "superseded_claims",
    "contradictions",
    "atoms",
    "provenance_counts",
    "provenance_truncated",
    "curator_version",
    "current_version",
    "snapshot_fingerprint",
}
_CANONICAL_SNAPSHOT_FIELDS = {
    "schema_version",
    "as_of",
    "thread_count",
    "canonical_thread_ids",
    "fingerprint",
}
_TIMELINE_FIELDS = {"date", "atom_id", "claim", "relation", "source_urls"}
_EVIDENCE_FIELDS = {
    "atom_id",
    "claim",
    "summary",
    "evidence_quote",
    "relation",
    "atom_type",
    "week_label",
    "last_seen_at",
    "confidence",
    "source_urls",
}
_PROJECT_CONNECTION_FIELDS = {"project", "connection_type", "rationale"}
_DECISION_FIELDS = {"decision", "rationale"}
_ATOM_FIELDS = {
    "id",
    "relation",
    "week_label",
    "atom_type",
    "claim",
    "summary",
    "evidence_quote",
    "source_post_ids",
    "source_urls",
    "entities",
    "tools",
    "models",
    "practices",
    "confidence",
    "novelty_score",
    "practical_utility_score",
    "staleness_status",
    "why_it_matters",
    "first_seen_at",
    "last_seen_at",
    "source_posts",
}
_SOURCE_POST_FIELDS = {
    "post_id",
    "content",
    "channel_username",
    "posted_at",
    "message_url",
}


class KnowledgeAuditExplorerValidationError(ValueError):
    """Raised when the closed Audit Explorer sidecar is invalid."""

    def __init__(self, errors: Sequence[str]):
        self.errors = tuple(str(item) for item in errors if str(item).strip())
        super().__init__(
            "; ".join(self.errors) or "Knowledge Audit Explorer validation failed"
        )


def build_knowledge_audit_explorer(
    manifest: Mapping[str, object],
    manifest_path: str | Path,
    v1_sidecar: Mapping[str, object],
    v1_html_path: str | Path,
    v1_json_path: str | Path,
    artifact_paths: Mapping[str, object],
    source_artifacts: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    """Build the closed Audit Explorer DTO from an authorized Atlas V1 DTO."""

    manifest_value = _json_object(manifest, "manifest")
    source = _json_object(v1_sidecar, "v1_sidecar")
    manifest_ref = _absolute_path(manifest_path, "manifest_path")
    v1_html_ref = _absolute_path(v1_html_path, "v1_html_path")
    v1_json_ref = _absolute_path(v1_json_path, "v1_json_path")

    errors: list[str] = []
    _validate_manifest(manifest_value, manifest_ref, errors)
    _validate_v1_identity(
        source,
        manifest=manifest_value,
        manifest_path=manifest_ref,
        html_path=v1_html_ref,
        json_path=v1_json_ref,
        errors=errors,
    )
    if errors:
        raise KnowledgeAuditExplorerValidationError(errors)

    navigation = copy.deepcopy(_mapping(source["thread_navigation"]))
    raw_source = _mapping(source.get("intelligence_contract")).get("idea_threads")
    raw_threads = [
        _normalize_raw_thread(item)
        for item in _mapping_list(
            raw_source,
            "v1_sidecar.intelligence_contract.idea_threads",
            _MAX_RAW_THREADS,
        )
    ]
    canonical_threads = [
        _normalize_canonical_thread(
            item, as_of=str(manifest_value["analysis_period_end"])
        )
        for item in _mapping_list(
            source.get("canonical_threads"),
            "v1_sidecar.canonical_threads",
            _MAX_CANONICAL_THREADS,
        )
    ]
    canonical_snapshot = _normalize_snapshot(
        source.get("canonical_thread_snapshot"),
        as_of=str(manifest_value["analysis_period_end"]),
        canonical_thread_ids=[
            str(item["canonical_thread_id"]) for item in canonical_threads
        ],
    )
    links = [
        _deep_link(item)
        for item in _mapping_list(
            navigation.get("threads"),
            "v1_sidecar.thread_navigation.threads",
            _MAX_NAVIGATION_THREADS,
        )
    ]
    links.extend(_canonical_deep_link(item) for item in canonical_threads)
    sources = _normalize_source_artifacts(source_artifacts)
    paths = _normalize_artifact_paths(artifact_paths)
    refs = {
        "manifest_path": manifest_ref,
        "v1_atlas_html_path": v1_html_ref,
        "v1_atlas_json_path": v1_json_ref,
    }
    expected_sources = {
        "manifest": manifest_ref,
        "v1_atlas_html": v1_html_ref,
        "v1_atlas_json": v1_json_ref,
    }
    for name, expected_path in expected_sources.items():
        if _mapping(sources.get(name)).get("path") != expected_path:
            errors.append(
                f"source_artifacts.{name}.path does not match its bound source"
            )
    if errors:
        raise KnowledgeAuditExplorerValidationError(errors)

    period = {
        "reporting_week": str(manifest_value["reporting_week"]),
        "analysis_period_start": str(manifest_value["analysis_period_start"]),
        "analysis_period_end": str(manifest_value["analysis_period_end"]),
    }
    payload: dict[str, object] = {
        "schema_version": AUDIT_EXPLORER_SCHEMA_VERSION,
        "surface": AUDIT_EXPLORER_SURFACE,
        "renderer_version": AUDIT_EXPLORER_RENDERER_VERSION,
        "source_schema_version": V1_ATLAS_SCHEMA_VERSION,
        "run_id": str(manifest_value["run_id"]),
        "generated_at": str(manifest_value["generated_at"]),
        "period_mode": str(manifest_value["period_mode"]),
        "reporting_period": period,
        "as_of": period["analysis_period_end"],
        "source_run_status": str(source["run_status"]),
        "run_status": str(manifest_value["run_status"]),
        "partial": bool(manifest_value["partial"]),
        "technical_notice_ru": TECHNICAL_NOTICE_RU,
        "thread_navigation": navigation,
        "raw_threads": raw_threads,
        "canonical_threads": canonical_threads,
        "canonical_thread_snapshot": canonical_snapshot,
        "raw_thread_count": len(raw_threads),
        "canonical_thread_count": len(canonical_threads),
        "deep_links": links,
        "source_artifacts": sources,
        "artifact_paths": paths,
        "technical_refs": refs,
    }
    return validate_knowledge_audit_explorer(payload, manifest=manifest_value)


def validate_knowledge_audit_explorer(
    payload: Mapping[str, object],
    manifest: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Validate and return a JSON-detached Audit Explorer DTO."""

    value = _json_object(payload, "payload")
    errors: list[str] = []
    _exact_fields(value, _ROOT_FIELDS, "payload", errors)

    _equal(
        value.get("schema_version"),
        AUDIT_EXPLORER_SCHEMA_VERSION,
        "schema_version",
        errors,
    )
    _equal(value.get("surface"), AUDIT_EXPLORER_SURFACE, "surface", errors)
    _equal(
        value.get("renderer_version"),
        AUDIT_EXPLORER_RENDERER_VERSION,
        "renderer_version",
        errors,
    )
    _equal(
        value.get("source_schema_version"),
        V1_ATLAS_SCHEMA_VERSION,
        "source_schema_version",
        errors,
    )
    _bounded_string(value.get("run_id"), "run_id", errors, maximum=128)
    if not _RUN_ID_RE.fullmatch(str(value.get("run_id") or "")):
        errors.append("run_id is invalid")
    _bounded_string(value.get("generated_at"), "generated_at", errors)
    if value.get("period_mode") not in {"completed_iso_week", "explicit_iso_week"}:
        errors.append("period_mode is invalid")
    period = _object(value.get("reporting_period"), "reporting_period", errors)
    _exact_fields(period, _PERIOD_FIELDS, "reporting_period", errors)
    for field in _PERIOD_FIELDS:
        _bounded_string(period.get(field), f"reporting_period.{field}", errors)
    if value.get("as_of") != period.get("analysis_period_end"):
        errors.append("as_of must equal reporting_period.analysis_period_end")
    if value.get("run_status") not in {"complete", "partial"}:
        errors.append("run_status is invalid")
    if value.get("source_run_status") != value.get("run_status"):
        errors.append("source_run_status must match run_status")
    if not isinstance(value.get("partial"), bool):
        errors.append("partial must be boolean")
    elif value.get("partial") is not (value.get("run_status") == "partial"):
        errors.append("partial does not match run_status")
    _equal(
        value.get("technical_notice_ru"),
        TECHNICAL_NOTICE_RU,
        "technical_notice_ru",
        errors,
    )

    navigation = _validate_navigation(value.get("thread_navigation"), period, errors)
    raw_threads = _validate_raw_threads(value.get("raw_threads"), errors)
    canonical_threads = _validate_canonical_threads(
        value.get("canonical_threads"),
        as_of=str(value.get("as_of") or ""),
        errors=errors,
    )
    _validate_snapshot(
        value.get("canonical_thread_snapshot"),
        canonical_threads=canonical_threads,
        as_of=str(value.get("as_of") or ""),
        errors=errors,
    )
    if value.get("raw_thread_count") != len(raw_threads):
        errors.append("raw_thread_count mismatch")
    if value.get("canonical_thread_count") != len(canonical_threads):
        errors.append("canonical_thread_count mismatch")
    _validate_deep_links(value.get("deep_links"), navigation, canonical_threads, errors)
    sources = _validate_source_artifacts(value.get("source_artifacts"), errors)
    paths = _validate_artifact_paths(value.get("artifact_paths"), errors)
    refs = _validate_technical_refs(value.get("technical_refs"), errors)
    _validate_source_bindings(sources, refs, errors)
    all_paths = [
        *[str(item.get("path") or "") for item in sources.values()],
        *[str(item) for item in paths.values()],
    ]
    if len(all_paths) != len(set(all_paths)):
        errors.append("source and output artifact paths must be duplicate-free")

    if manifest is not None:
        manifest_value = _json_object(manifest, "manifest")
        manifest_path = str(refs.get("manifest_path") or "")
        _validate_manifest(manifest_value, manifest_path, errors)
        _validate_payload_manifest_identity(value, manifest_value, errors)

    if errors:
        raise KnowledgeAuditExplorerValidationError(errors)
    return _json_object(value, "payload")


def render_knowledge_audit_explorer_html(
    payload: Mapping[str, object],
    source_html: str,
    manifest: Mapping[str, object] | None = None,
) -> str:
    """Relabel the exact V1 HTML and append closed records for missing anchors."""

    value = validate_knowledge_audit_explorer(payload, manifest=manifest)
    if not isinstance(source_html, str):
        raise KnowledgeAuditExplorerValidationError(["source_html must be text"])
    encoded = source_html.encode("utf-8")
    errors: list[str] = []
    if not encoded or len(encoded) > _MAX_HTML_BYTES:
        errors.append("source_html size is invalid")
    descriptor = _mapping(_mapping(value["source_artifacts"])["v1_atlas_html"])
    if descriptor.get("size") != len(encoded):
        errors.append("source_html size does not match source_artifacts.v1_atlas_html")
    if descriptor.get("sha256") != hashlib.sha256(encoded).hexdigest():
        errors.append(
            "source_html checksum does not match source_artifacts.v1_atlas_html"
        )
    lowered = source_html.lower()
    if "<!doctype html>" not in lowered or "<html" not in lowered:
        errors.append("source_html must be standalone HTML")
    if 'id="thread-navigation"' not in source_html:
        errors.append("source_html is not the detailed Atlas V1 surface")
    if AUDIT_EXPLORER_SCHEMA_VERSION in source_html:
        errors.append("source_html is already an Audit Explorer rendering")
    parser = _IdentityParser()
    try:
        parser.feed(source_html)
        parser.close()
    except (ValueError, RecursionError) as exc:
        errors.append(f"source_html cannot be parsed: {exc}")
    duplicate_ids = sorted(
        item for item, count in parser.identities.items() if count != 1
    )
    if duplicate_ids:
        errors.append("source_html contains duplicate id attributes")
    if parser.body_count != 1 or parser.main_count != 1:
        errors.append("source_html must contain exactly one body and one main")
    for tag in ("html", "head", "title", "style", "body", "main"):
        if parser.tag_counts.get(tag) != 1:
            errors.append(f"source_html must contain exactly one <{tag}> element")
        if parser.end_tag_counts.get(tag) != 1:
            errors.append(f"source_html must contain exactly one </{tag}> element")
    if parser.doctype_count != 1:
        errors.append("source_html must contain exactly one HTML5 doctype")
    errors.extend(f"source_html {item}" for item in parser.security_errors)
    if _unsafe_css(source_html):
        errors.append("source_html contains active, remote, or hidden CSS")
    if errors:
        raise KnowledgeAuditExplorerValidationError(errors)

    rendered = _relabel_document(source_html, value)
    existing = set(parser.identities)
    navigation_items = _mapping_list(
        _mapping(value["thread_navigation"])["threads"],
        "thread_navigation.threads",
        _MAX_NAVIGATION_THREADS,
    )
    missing = [item for item in navigation_items if str(item["id"]) not in existing]
    if missing:
        appendix = _render_missing_records(missing)
        if "</main>" not in rendered:
            raise KnowledgeAuditExplorerValidationError(
                ["source_html main element is not closed"]
            )
        rendered = rendered.replace("</main>", f"{appendix}\n</main>", 1)
    canonical_items = _mapping_list(
        value["canonical_threads"],
        "canonical_threads",
        _MAX_CANONICAL_THREADS,
    )
    missing_canonical = [
        item for item in canonical_items if _canonical_anchor(item) not in existing
    ]
    if missing_canonical:
        appendix = _render_canonical_records(missing_canonical)
        if "</main>" not in rendered:
            raise KnowledgeAuditExplorerValidationError(
                ["source_html main element is not closed"]
            )
        rendered = rendered.replace("</main>", f"{appendix}\n</main>", 1)

    result_parser = _IdentityParser()
    result_parser.feed(rendered)
    result_parser.close()
    rendered_security_errors = list(result_parser.security_errors)
    if _unsafe_css(rendered):
        rendered_security_errors.append("contains active, remote, or hidden CSS")
    if rendered_security_errors:
        raise KnowledgeAuditExplorerValidationError(
            [f"rendered HTML {item}" for item in rendered_security_errors]
        )
    if (
        result_parser.body_count != 1
        or result_parser.main_count != 1
        or result_parser.doctype_count != 1
    ):
        raise KnowledgeAuditExplorerValidationError(
            ["rendered HTML document structure is invalid"]
        )
    for tag in ("html", "head", "title", "style", "body", "main"):
        if (
            result_parser.tag_counts.get(tag) != 1
            or result_parser.end_tag_counts.get(tag) != 1
        ):
            raise KnowledgeAuditExplorerValidationError(
                [f"rendered HTML has ambiguous <{tag}> structure"]
            )
    duplicated = sorted(
        identity for identity, count in result_parser.identities.items() if count != 1
    )
    if duplicated:
        raise KnowledgeAuditExplorerValidationError(
            ["rendered HTML contains duplicate ids: " + ", ".join(duplicated)]
        )
    expected_anchors = [str(item["anchor"]) for item in value["deep_links"]]
    absent = [
        anchor
        for anchor in expected_anchors
        if result_parser.identities.get(anchor) != 1
    ]
    if absent:
        raise KnowledgeAuditExplorerValidationError(
            ["rendered HTML is missing stable thread anchors: " + ", ".join(absent)]
        )
    return rendered


def _validate_v1_identity(
    source: Mapping[str, object],
    *,
    manifest: Mapping[str, object],
    manifest_path: str,
    html_path: str,
    json_path: str,
    errors: list[str],
) -> None:
    if source.get("schema_version") != V1_ATLAS_SCHEMA_VERSION:
        errors.append("v1_sidecar schema_version mismatch")
    if source.get("artifact_type") != V1_ATLAS_ARTIFACT_TYPE:
        errors.append("v1_sidecar artifact_type mismatch")
    identity = (
        "run_id",
        "generated_at",
        "period_mode",
        "reporting_week",
        "week_label",
        "analysis_period_start",
        "analysis_period_end",
        "pipeline_profile",
        "run_status",
        "partial",
    )
    for field in identity:
        if source.get(field) != manifest.get(field):
            errors.append(f"v1_sidecar {field} mismatch")
    expected_paths = {
        "manifest_path": manifest_path,
        "html_path": html_path,
        "json_path": json_path,
    }
    for field, expected in expected_paths.items():
        try:
            actual = _absolute_path(source.get(field), f"v1_sidecar.{field}")
        except KnowledgeAuditExplorerValidationError as exc:
            errors.extend(exc.errors)
        else:
            if actual != expected:
                errors.append(f"v1_sidecar {field} mismatch")
    source_paths = _mapping(source.get("artifact_paths"))
    if set(source_paths) != {"html", "json"}:
        errors.append("v1_sidecar artifact_paths fields mismatch")
    else:
        for field, expected in (("html", html_path), ("json", json_path)):
            try:
                actual = _absolute_path(
                    source_paths.get(field), f"v1_sidecar.artifact_paths.{field}"
                )
            except KnowledgeAuditExplorerValidationError as exc:
                errors.extend(exc.errors)
            else:
                if actual != expected:
                    errors.append(f"v1_sidecar artifact_paths.{field} mismatch")
    navigation = _mapping(source.get("thread_navigation"))
    if navigation.get("schema_version") != V1_THREAD_NAVIGATION_SCHEMA_VERSION:
        errors.append("v1_sidecar thread_navigation schema mismatch")
    if not isinstance(
        _mapping(source.get("intelligence_contract")).get("idea_threads"), list
    ):
        errors.append("v1_sidecar raw idea-thread audit projection is missing")
    if not isinstance(source.get("canonical_threads"), list):
        errors.append("v1_sidecar canonical_threads must be a list")
    snapshot = _mapping(source.get("canonical_thread_snapshot"))
    if snapshot and not _same_utc_instant(
        snapshot.get("as_of"), manifest.get("analysis_period_end")
    ):
        errors.append("v1_sidecar canonical snapshot as_of mismatch")


def _validate_manifest(
    manifest: Mapping[str, object], manifest_path: str, errors: list[str]
) -> None:
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append("manifest schema mismatch")
    run_id = str(manifest.get("run_id") or "")
    if not _RUN_ID_RE.fullmatch(run_id):
        errors.append("manifest run_id is invalid")
    if manifest.get("run_status") not in {"complete", "partial"}:
        errors.append("Audit Explorer requires a terminal reader manifest")
    if manifest.get("period_mode") not in {"completed_iso_week", "explicit_iso_week"}:
        errors.append("Audit Explorer requires a complete ISO-week period")
    if not isinstance(manifest.get("partial"), bool):
        errors.append("manifest partial must be boolean")
    elif manifest.get("partial") is not (manifest.get("run_status") == "partial"):
        errors.append("manifest partial does not match run_status")
    for field in (
        "generated_at",
        "reporting_week",
        "week_label",
        "analysis_period_start",
        "analysis_period_end",
        "pipeline_profile",
    ):
        _bounded_string(manifest.get(field), f"manifest.{field}", errors)
    try:
        path = _absolute_path(manifest_path, "manifest_path")
    except KnowledgeAuditExplorerValidationError as exc:
        errors.extend(exc.errors)
        return
    if Path(path).name != "manifest.json" or Path(path).parent.name != run_id:
        errors.append("manifest_path does not match run identity")


def _validate_payload_manifest_identity(
    value: Mapping[str, object], manifest: Mapping[str, object], errors: list[str]
) -> None:
    period = _mapping(value.get("reporting_period"))
    expected = {
        "run_id": manifest.get("run_id"),
        "generated_at": manifest.get("generated_at"),
        "period_mode": manifest.get("period_mode"),
        "as_of": manifest.get("analysis_period_end"),
        "run_status": manifest.get("run_status"),
        "partial": manifest.get("partial"),
    }
    for field, expected_value in expected.items():
        if value.get(field) != expected_value:
            errors.append(f"payload {field} does not match manifest")
    for field in _PERIOD_FIELDS:
        if period.get(field) != manifest.get(field):
            errors.append(f"payload reporting_period.{field} does not match manifest")


def _normalize_raw_thread(item: Mapping[str, object]) -> dict[str, object]:
    momentum = _mapping(item.get("momentum_vs_evidence"))
    return {
        "id": str(item.get("id") or ""),
        "thread_slug": str(item.get("thread_slug") or ""),
        "title": str(item.get("title") or ""),
        "status": str(item.get("status") or ""),
        "atom_ids": copy.deepcopy(list(item.get("atom_ids") or [])),
        "claim_ids": copy.deepcopy(list(item.get("claim_ids") or [])),
        "evidence_item_ids": copy.deepcopy(list(item.get("evidence_item_ids") or [])),
        "previous_state": str(item.get("previous_state") or ""),
        "current_state": str(item.get("current_state") or ""),
        "delta_basis": str(item.get("delta_basis") or ""),
        "new_evidence_atom_ids": copy.deepcopy(
            list(item.get("new_evidence_atom_ids") or [])
        ),
        "momentum_vs_evidence": {
            "momentum_7d": momentum.get("momentum_7d"),
            "momentum_30d": momentum.get("momentum_30d"),
            "evidence_growth": momentum.get("evidence_growth"),
            "momentum_is_not_evidence": momentum.get("momentum_is_not_evidence"),
        },
        "contradictions": copy.deepcopy(list(item.get("contradictions") or [])),
        "merge_split_audit_status": str(item.get("merge_split_audit_status") or ""),
    }


def _normalize_canonical_thread(
    item: Mapping[str, object], *, as_of: str
) -> dict[str, object]:
    source_as_of = item.get("as_of")
    if source_as_of and not _same_utc_instant(source_as_of, as_of):
        raise KnowledgeAuditExplorerValidationError(
            ["canonical_thread.as_of does not match the manifest boundary"]
        )
    return {
        "canonical_thread_id": str(item.get("canonical_thread_id") or ""),
        "stable_slug": str(item.get("stable_slug") or ""),
        "title_ru": str(item.get("title_ru") or item.get("title") or ""),
        "title_en": str(item.get("title_en") or ""),
        "thesis": str(item.get("thesis") or item.get("summary") or ""),
        "status": str(item.get("status") or ""),
        "first_seen_at": str(item.get("first_seen_at") or ""),
        "last_seen_at": str(item.get("last_seen_at") or ""),
        "as_of": as_of,
        "evidence_maturity": str(item.get("evidence_maturity") or ""),
        "operator_interest": (
            item.get("operator_interest")
            if item.get("operator_interest") is not None
            else 0.0
        ),
        "aliases": _normalize_aliases(item.get("aliases") or []),
        "raw_thread_aliases": _normalize_aliases(item.get("raw_thread_aliases") or []),
        "merged_from": copy.deepcopy(list(item.get("merged_from") or [])),
        "merged_into": copy.deepcopy(list(item.get("merged_into") or [])),
        "split_from": copy.deepcopy(list(item.get("split_from") or [])),
        "split_into": copy.deepcopy(list(item.get("split_into") or [])),
        "lineage": _normalize_lineage(item.get("lineage") or []),
        "raw_thread_ids": copy.deepcopy(list(item.get("raw_thread_ids") or [])),
        "raw_thread_refs": _normalize_raw_thread_refs(
            item.get("raw_thread_refs") or []
        ),
        "atom_ids": copy.deepcopy(list(item.get("atom_ids") or [])),
        "source_post_ids": copy.deepcopy(list(item.get("source_post_ids") or [])),
        "source_urls": copy.deepcopy(list(item.get("source_urls") or [])),
        "source_refs": copy.deepcopy(list(item.get("source_refs") or [])),
        "current_claims": copy.deepcopy(list(item.get("current_claims") or [])),
        "superseded_claims": copy.deepcopy(list(item.get("superseded_claims") or [])),
        "contradictions": copy.deepcopy(list(item.get("contradictions") or [])),
        "atoms": [
            _normalize_atom(atom)
            for atom in _mapping_list(
                item.get("atoms") or [], "canonical_thread.atoms", 100
            )
        ],
        "provenance_counts": {
            "atom_ids": _count_or_length(
                _mapping(item.get("provenance_counts")).get("atom_ids"),
                item.get("atom_ids"),
                "canonical_thread.provenance_counts.atom_ids",
            ),
            "source_post_ids": _count_or_length(
                _mapping(item.get("provenance_counts")).get("source_post_ids"),
                item.get("source_post_ids"),
                "canonical_thread.provenance_counts.source_post_ids",
            ),
            "source_urls": _count_or_length(
                _mapping(item.get("provenance_counts")).get("source_urls"),
                item.get("source_urls"),
                "canonical_thread.provenance_counts.source_urls",
            ),
        },
        "provenance_truncated": bool(item.get("provenance_truncated", False)),
        "curator_version": str(item.get("curator_version") or ""),
        "current_version": _positive_int(
            item.get("current_version") or item.get("version") or 1,
            "canonical_thread.current_version",
        ),
        "snapshot_fingerprint": str(item.get("snapshot_fingerprint") or ""),
    }


def _normalize_atom(item: Mapping[str, object]) -> dict[str, object]:
    return {
        "id": item.get("id"),
        "relation": str(item.get("relation") or ""),
        "week_label": str(item.get("week_label") or ""),
        "atom_type": str(item.get("atom_type") or ""),
        "claim": str(item.get("claim") or ""),
        "summary": str(item.get("summary") or ""),
        "evidence_quote": str(item.get("evidence_quote") or ""),
        "source_post_ids": copy.deepcopy(list(item.get("source_post_ids") or [])),
        "source_urls": copy.deepcopy(list(item.get("source_urls") or [])),
        "entities": copy.deepcopy(list(item.get("entities") or [])),
        "tools": copy.deepcopy(list(item.get("tools") or [])),
        "models": copy.deepcopy(list(item.get("models") or [])),
        "practices": copy.deepcopy(list(item.get("practices") or [])),
        "confidence": item.get("confidence"),
        "novelty_score": item.get("novelty_score"),
        "practical_utility_score": item.get("practical_utility_score"),
        "staleness_status": str(item.get("staleness_status") or ""),
        "why_it_matters": str(item.get("why_it_matters") or ""),
        "first_seen_at": str(item.get("first_seen_at") or ""),
        "last_seen_at": str(item.get("last_seen_at") or ""),
        "source_posts": [
            {
                "post_id": post.get("post_id"),
                "content": str(post.get("content") or ""),
                "channel_username": str(post.get("channel_username") or ""),
                "posted_at": str(post.get("posted_at") or ""),
                "message_url": str(post.get("message_url") or ""),
            }
            for post in _mapping_list(
                item.get("source_posts") or [],
                "canonical_thread.atom.source_posts",
                100,
            )
        ],
    }


def _normalize_aliases(value: object) -> list[dict[str, str]]:
    return [
        {
            "alias_type": str(item.get("alias_type") or ""),
            "alias_value": str(item.get("alias_value") or item.get("value") or ""),
        }
        for item in _mapping_list(value, "canonical_thread.aliases", 100)
    ]


def _normalize_lineage(value: object) -> list[dict[str, object]]:
    return [
        {
            "relation_type": str(item.get("relation_type") or ""),
            "from_thread_id": str(item.get("from_thread_id") or ""),
            "to_thread_id": str(item.get("to_thread_id") or ""),
            "decision_id": str(item.get("decision_id") or ""),
            "event_at": str(item.get("event_at") or ""),
            "reason": str(item.get("reason") or ""),
        }
        for item in _mapping_list(value, "canonical_thread.lineage", 100)
    ]


def _normalize_raw_thread_refs(value: object) -> list[dict[str, object]]:
    return [
        {
            "raw_thread_id": item.get("raw_thread_id"),
            "slug": str(item.get("slug") or ""),
            "title": str(item.get("title") or ""),
            "status": str(item.get("status") or ""),
        }
        for item in _mapping_list(value, "canonical_thread.raw_thread_refs", 100)
    ]


def _normalize_snapshot(
    value: object, *, as_of: str, canonical_thread_ids: Sequence[str]
) -> dict[str, object]:
    source = _mapping(value)
    if not source:
        return {}
    source_as_of = source.get("as_of")
    if source_as_of and not _same_utc_instant(source_as_of, as_of):
        raise KnowledgeAuditExplorerValidationError(
            ["canonical_thread_snapshot.as_of does not match the manifest boundary"]
        )
    source_ids = source.get("canonical_thread_ids")
    normalized_ids = (
        copy.deepcopy(list(source_ids))
        if isinstance(source_ids, list)
        else list(canonical_thread_ids)
    )
    return {
        "schema_version": str(source.get("schema_version") or ""),
        "as_of": as_of,
        "thread_count": source.get("thread_count", len(normalized_ids)),
        "canonical_thread_ids": normalized_ids,
        "fingerprint": str(source.get("fingerprint") or ""),
    }


def _deep_link(item: Mapping[str, object]) -> dict[str, str]:
    slug = str(item.get("slug") or "")
    anchor = str(item.get("id") or "")
    return {
        "thread_ref": f"thread:{slug}",
        "title": str(item.get("title") or slug),
        "anchor": anchor,
        "href": f"{_AUDIT_HTML_FILENAME}#{anchor}",
    }


def _canonical_deep_link(item: Mapping[str, object]) -> dict[str, str]:
    slug = str(item.get("stable_slug") or "")
    anchor = _canonical_anchor(item)
    return {
        "thread_ref": f"canonical_thread:{slug}",
        "title": str(item.get("title_ru") or slug),
        "anchor": anchor,
        "href": f"{_AUDIT_HTML_FILENAME}#{anchor}",
    }


def _canonical_anchor(item: Mapping[str, object]) -> str:
    return f"canonical-thread-{str(item.get('stable_slug') or '')}"


def _normalize_source_artifacts(
    value: Mapping[str, Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    source = _json_object(value, "source_artifacts")
    errors: list[str] = []
    result = _validate_source_artifacts(source, errors)
    if errors:
        raise KnowledgeAuditExplorerValidationError(errors)
    return result


def _normalize_artifact_paths(value: Mapping[str, object]) -> dict[str, str]:
    source = _json_object(value, "artifact_paths")
    errors: list[str] = []
    result = _validate_artifact_paths(source, errors)
    if errors:
        raise KnowledgeAuditExplorerValidationError(errors)
    return result


def _validate_navigation(
    value: object, period: Mapping[str, object], errors: list[str]
) -> list[dict[str, object]]:
    navigation = _object(value, "thread_navigation", errors)
    _exact_fields(navigation, _NAVIGATION_FIELDS, "thread_navigation", errors)
    if navigation.get("schema_version") != V1_THREAD_NAVIGATION_SCHEMA_VERSION:
        errors.append("thread_navigation schema mismatch")
    if navigation.get("week_label") != period.get("reporting_week"):
        errors.append("thread_navigation week_label mismatch")
    threads = _object_list(
        navigation.get("threads"),
        "thread_navigation.threads",
        errors,
        _MAX_NAVIGATION_THREADS,
    )
    if navigation.get("thread_count") != len(threads):
        errors.append("thread_navigation thread_count mismatch")
    if not _non_negative_int(navigation.get("source_atom_count")):
        errors.append("thread_navigation source_atom_count is invalid")
    _bounded_string(
        navigation.get("bounded_context_note"),
        "thread_navigation.bounded_context_note",
        errors,
    )
    anchors: list[str] = []
    refs: list[str] = []
    for index, item in enumerate(threads):
        path = f"thread_navigation.threads[{index}]"
        _exact_fields(item, _NAVIGATION_THREAD_FIELDS, path, errors)
        anchor = str(item.get("id") or "")
        slug = str(item.get("slug") or "")
        if not _RAW_ANCHOR_RE.fullmatch(anchor):
            errors.append(f"{path}.id is not a stable Atlas anchor")
        _bounded_string(slug, f"{path}.slug", errors, maximum=240)
        _bounded_string(item.get("title"), f"{path}.title", errors)
        _bounded_string(
            item.get("current_understanding"), f"{path}.current_understanding", errors
        )
        _bounded_string(
            item.get("change_since_previous_period"),
            f"{path}.change_since_previous_period",
            errors,
        )
        anchors.append(anchor)
        refs.append(f"thread:{slug}")
        _validate_navigation_thread_details(item, path, errors)
    _duplicates(anchors, "thread_navigation anchors", errors)
    _duplicates(refs, "thread_navigation thread refs", errors)
    return threads


def _validate_navigation_thread_details(
    item: Mapping[str, object], path: str, errors: list[str]
) -> None:
    growth = _object(item.get("evidence_growth"), f"{path}.evidence_growth", errors)
    _exact_fields(
        growth,
        {
            "atom_count",
            "rendered_evidence_count",
            "source_channel_count",
            "changed_this_week",
        },
        f"{path}.evidence_growth",
        errors,
    )
    diversity = _object(
        item.get("source_diversity"), f"{path}.source_diversity", errors
    )
    _exact_fields(
        diversity,
        {"source_count", "source_channel_count", "channels"},
        f"{path}.source_diversity",
        errors,
    )
    sequences: dict[str, list[object]] = {}
    for field, maximum in (
        ("timeline", 6),
        ("claims", 5),
        ("evidence_items", 6),
        ("contradictions", 5),
        ("superseded_claims", 5),
        ("project_connections", 3),
        ("decisions", 3),
        ("open_questions", 3),
        ("study_next", 3),
        ("source_urls", 8),
    ):
        sequence = item.get(field)
        if not isinstance(sequence, list) or len(sequence) > maximum:
            errors.append(f"{path}.{field} must be a list bounded to {maximum}")
            sequences[field] = []
        else:
            sequences[field] = sequence
    _validate_urls(item.get("source_urls"), f"{path}.source_urls", errors)
    for index, row in enumerate(sequences.get("timeline", [])):
        row_path = f"{path}.timeline[{index}]"
        if not isinstance(row, Mapping):
            errors.append(f"{row_path} must be an object")
            continue
        _exact_fields(row, _TIMELINE_FIELDS, row_path, errors)
        _validate_urls(row.get("source_urls"), f"{row_path}.source_urls", errors)
    for index, row in enumerate(sequences.get("evidence_items", [])):
        row_path = f"{path}.evidence_items[{index}]"
        if not isinstance(row, Mapping):
            errors.append(f"{row_path} must be an object")
            continue
        _exact_fields(row, _EVIDENCE_FIELDS, row_path, errors)
        _validate_urls(row.get("source_urls"), f"{row_path}.source_urls", errors)
    for field, expected in (
        ("project_connections", _PROJECT_CONNECTION_FIELDS),
        ("decisions", _DECISION_FIELDS),
    ):
        for index, row in enumerate(sequences.get(field, [])):
            row_path = f"{path}.{field}[{index}]"
            if not isinstance(row, Mapping):
                errors.append(f"{row_path} must be an object")
                continue
            _exact_fields(row, expected, row_path, errors)


def _validate_raw_threads(value: object, errors: list[str]) -> list[dict[str, object]]:
    rows = _object_list(value, "raw_threads", errors, _MAX_RAW_THREADS)
    identities: list[str] = []
    slugs: list[str] = []
    for index, item in enumerate(rows):
        path = f"raw_threads[{index}]"
        _exact_fields(item, _RAW_THREAD_FIELDS, path, errors)
        identity = str(item.get("id") or "")
        slug = str(item.get("thread_slug") or "")
        _bounded_string(identity, f"{path}.id", errors, maximum=300)
        _bounded_string(slug, f"{path}.thread_slug", errors, maximum=240)
        _bounded_string(item.get("title"), f"{path}.title", errors)
        identities.append(identity)
        slugs.append(slug)
        momentum = _object(
            item.get("momentum_vs_evidence"), f"{path}.momentum_vs_evidence", errors
        )
        _exact_fields(
            momentum,
            {
                "momentum_7d",
                "momentum_30d",
                "evidence_growth",
                "momentum_is_not_evidence",
            },
            f"{path}.momentum_vs_evidence",
            errors,
        )
        if momentum.get("momentum_is_not_evidence") is not True:
            errors.append(
                f"{path}.momentum_vs_evidence must preserve the evidence boundary"
            )
    _duplicates(identities, "raw thread ids", errors)
    _duplicates(slugs, "raw thread slugs", errors)
    return rows


def _validate_canonical_threads(
    value: object, *, as_of: str, errors: list[str]
) -> list[dict[str, object]]:
    rows = _object_list(value, "canonical_threads", errors, _MAX_CANONICAL_THREADS)
    identities: list[str] = []
    slugs: list[str] = []
    for index, item in enumerate(rows):
        path = f"canonical_threads[{index}]"
        _exact_fields(item, _CANONICAL_THREAD_FIELDS, path, errors)
        identity = str(item.get("canonical_thread_id") or "")
        slug = str(item.get("stable_slug") or "")
        _bounded_string(identity, f"{path}.canonical_thread_id", errors, maximum=200)
        _bounded_string(slug, f"{path}.stable_slug", errors, maximum=200)
        if not _STABLE_SLUG_RE.fullmatch(slug) or len(slug) > 96:
            errors.append(f"{path}.stable_slug is invalid")
        _bounded_string(item.get("title_ru"), f"{path}.title_ru", errors)
        _bounded_string(item.get("thesis"), f"{path}.thesis", errors)
        if item.get("as_of") != as_of:
            errors.append(f"{path}.as_of mismatch")
        if not _finite_number(item.get("operator_interest")):
            errors.append(f"{path}.operator_interest is invalid")
        elif not 0 <= float(item["operator_interest"]) <= 1:
            errors.append(f"{path}.operator_interest is outside 0..1")
        if (
            not isinstance(item.get("current_version"), int)
            or isinstance(item.get("current_version"), bool)
            or int(item["current_version"]) < 1
        ):
            errors.append(f"{path}.current_version is invalid")
        if not isinstance(item.get("provenance_truncated"), bool):
            errors.append(f"{path}.provenance_truncated must be boolean")
        snapshot_fingerprint = str(item.get("snapshot_fingerprint") or "")
        if snapshot_fingerprint and not _SHA256_RE.fullmatch(snapshot_fingerprint):
            errors.append(f"{path}.snapshot_fingerprint is invalid")
        identities.append(identity)
        slugs.append(slug)
        _validate_canonical_provenance(item, path, errors)
    _duplicates(identities, "canonical thread ids", errors)
    _duplicates(slugs, "canonical stable slugs", errors)
    return rows


def _validate_canonical_provenance(
    item: Mapping[str, object], path: str, errors: list[str]
) -> None:
    for field in ("aliases", "raw_thread_aliases"):
        aliases = _object_list(item.get(field), f"{path}.{field}", errors, 100)
        alias_keys: list[str] = []
        for index, alias in enumerate(aliases):
            alias_path = f"{path}.{field}[{index}]"
            _exact_fields(alias, {"alias_type", "alias_value"}, alias_path, errors)
            alias_keys.append(f"{alias.get('alias_type')}\0{alias.get('alias_value')}")
        _duplicates(alias_keys, f"{path} {field}", errors)
    lineage = _object_list(item.get("lineage"), f"{path}.lineage", errors, 100)
    lineage_keys: list[str] = []
    lineage_fields = {
        "relation_type",
        "from_thread_id",
        "to_thread_id",
        "decision_id",
        "event_at",
        "reason",
    }
    for index, row in enumerate(lineage):
        row_path = f"{path}.lineage[{index}]"
        _exact_fields(row, lineage_fields, row_path, errors)
        lineage_keys.append(
            "\0".join(str(row.get(field) or "") for field in sorted(lineage_fields))
        )
    _duplicates(lineage_keys, f"{path} lineage rows", errors)
    _unique_scalar_list(item.get("atom_ids"), f"{path}.atom_ids", errors, 100)
    _unique_scalar_list(
        item.get("raw_thread_ids"), f"{path}.raw_thread_ids", errors, 100
    )
    raw_refs = _object_list(
        item.get("raw_thread_refs"), f"{path}.raw_thread_refs", errors, 100
    )
    raw_ref_ids: list[str] = []
    for index, raw_ref in enumerate(raw_refs):
        raw_path = f"{path}.raw_thread_refs[{index}]"
        _exact_fields(
            raw_ref, {"raw_thread_id", "slug", "title", "status"}, raw_path, errors
        )
        raw_ref_ids.append(str(raw_ref.get("raw_thread_id") or ""))
    _duplicates(raw_ref_ids, f"{path} raw thread refs", errors)
    for field in ("merged_from", "merged_into", "split_from", "split_into"):
        _unique_scalar_list(item.get(field), f"{path}.{field}", errors, 100)
    _unique_scalar_list(
        item.get("source_post_ids"), f"{path}.source_post_ids", errors, 100
    )
    _unique_scalar_list(item.get("source_urls"), f"{path}.source_urls", errors, 100)
    _validate_urls(item.get("source_urls"), f"{path}.source_urls", errors)
    atoms = _object_list(item.get("atoms"), f"{path}.atoms", errors, 100)
    _duplicates([str(atom.get("id")) for atom in atoms], f"{path} atom records", errors)
    for index, atom in enumerate(atoms):
        atom_path = f"{path}.atoms[{index}]"
        _exact_fields(atom, _ATOM_FIELDS, atom_path, errors)
        _validate_urls(atom.get("source_urls"), f"{atom_path}.source_urls", errors)
        posts = _object_list(
            atom.get("source_posts"), f"{atom_path}.source_posts", errors, 100
        )
        for post_index, post in enumerate(posts):
            post_path = f"{atom_path}.source_posts[{post_index}]"
            _exact_fields(post, _SOURCE_POST_FIELDS, post_path, errors)
            message_url = post.get("message_url")
            if message_url and not _safe_http_url(message_url):
                errors.append(f"{post_path}.message_url must be an HTTP(S) URL")
    counts = _object(item.get("provenance_counts"), f"{path}.provenance_counts", errors)
    _exact_fields(
        counts,
        {"atom_ids", "source_post_ids", "source_urls"},
        f"{path}.provenance_counts",
        errors,
    )
    for field in ("atom_ids", "source_post_ids", "source_urls"):
        if not _non_negative_int(counts.get(field)):
            errors.append(f"{path}.provenance_counts.{field} is invalid")


def _validate_snapshot(
    value: object,
    *,
    canonical_threads: Sequence[Mapping[str, object]],
    as_of: str,
    errors: list[str],
) -> None:
    snapshot = _object(value, "canonical_thread_snapshot", errors)
    if not snapshot:
        if canonical_threads:
            errors.append(
                "canonical_thread_snapshot is required when canonical threads exist"
            )
        return
    _exact_fields(
        snapshot, _CANONICAL_SNAPSHOT_FIELDS, "canonical_thread_snapshot", errors
    )
    if snapshot.get("schema_version") != "canonical_idea_threads.snapshot.v1":
        errors.append("canonical_thread_snapshot schema mismatch")
    if snapshot.get("as_of") != as_of:
        errors.append("canonical_thread_snapshot as_of mismatch")
    ids = snapshot.get("canonical_thread_ids")
    if not isinstance(ids, list) or len(ids) > 500:
        errors.append("canonical_thread_snapshot canonical_thread_ids is invalid")
    else:
        _duplicates(
            [str(item) for item in ids], "canonical snapshot thread ids", errors
        )
        primary_ids = {
            str(item.get("canonical_thread_id")) for item in canonical_threads
        }
        if not primary_ids.issubset({str(item) for item in ids}):
            errors.append("canonical threads are absent from canonical_thread_snapshot")
    if not _non_negative_int(snapshot.get("thread_count")):
        errors.append("canonical_thread_snapshot thread_count is invalid")
    elif isinstance(ids, list) and snapshot.get("thread_count") != len(ids):
        errors.append("canonical_thread_snapshot thread_count mismatch")
    fingerprint = str(snapshot.get("fingerprint") or "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", fingerprint):
        errors.append("canonical_thread_snapshot fingerprint is invalid")


def _validate_deep_links(
    value: object,
    navigation: Sequence[Mapping[str, object]],
    canonical_threads: Sequence[Mapping[str, object]],
    errors: list[str],
) -> None:
    links = _object_list(value, "deep_links", errors, _MAX_DEEP_LINKS)
    expected = [
        *[_deep_link(item) for item in navigation],
        *[_canonical_deep_link(item) for item in canonical_threads],
    ]
    for index, item in enumerate(links):
        path = f"deep_links[{index}]"
        _exact_fields(item, _DEEP_LINK_FIELDS, path, errors)
        _bounded_string(item.get("title"), f"{path}.title", errors)
        anchor = str(item.get("anchor") or "")
        if not (
            _RAW_ANCHOR_RE.fullmatch(anchor) or _CANONICAL_ANCHOR_RE.fullmatch(anchor)
        ):
            errors.append(f"{path}.anchor is invalid")
        if item.get("href") != f"{_AUDIT_HTML_FILENAME}#{anchor}":
            errors.append(f"{path}.href must be package-local")
    if links != expected:
        errors.append(
            "deep_links must exactly project thread_navigation order and anchors"
        )
    _duplicates(
        [str(item.get("anchor")) for item in links], "deep-link anchors", errors
    )
    _duplicates(
        [str(item.get("thread_ref")) for item in links], "deep-link refs", errors
    )


def _validate_source_artifacts(
    value: object, errors: list[str]
) -> dict[str, dict[str, object]]:
    sources = _object(value, "source_artifacts", errors)
    _exact_fields(sources, _SOURCE_ARTIFACT_FIELDS, "source_artifacts", errors)
    result: dict[str, dict[str, object]] = {}
    for name in sorted(_SOURCE_ARTIFACT_FIELDS):
        descriptor = _object(sources.get(name), f"source_artifacts.{name}", errors)
        _exact_fields(
            descriptor, _SOURCE_DESCRIPTOR_FIELDS, f"source_artifacts.{name}", errors
        )
        try:
            path = _absolute_path(
                descriptor.get("path"), f"source_artifacts.{name}.path"
            )
        except KnowledgeAuditExplorerValidationError as exc:
            errors.extend(exc.errors)
            path = ""
        sha = str(descriptor.get("sha256") or "")
        if not _SHA256_RE.fullmatch(sha):
            errors.append(f"source_artifacts.{name}.sha256 is invalid")
        size = descriptor.get("size")
        if not _non_negative_int(size) or not 0 < int(size) <= _MAX_SOURCE_SIZE:
            errors.append(f"source_artifacts.{name}.size is invalid")
        result[name] = {"path": path, "sha256": sha, "size": size}
    return result


def _validate_artifact_paths(value: object, errors: list[str]) -> dict[str, str]:
    paths = _object(value, "artifact_paths", errors)
    _exact_fields(paths, _ARTIFACT_PATH_FIELDS, "artifact_paths", errors)
    result: dict[str, str] = {}
    for field in sorted(_ARTIFACT_PATH_FIELDS):
        try:
            result[field] = _absolute_path(paths.get(field), f"artifact_paths.{field}")
        except KnowledgeAuditExplorerValidationError as exc:
            errors.extend(exc.errors)
            result[field] = ""
    if result.get("html") == result.get("json"):
        errors.append("artifact_paths html and json must be distinct")
    if result.get("html") and Path(result["html"]).name != _AUDIT_HTML_FILENAME:
        errors.append(f"artifact_paths.html must end with {_AUDIT_HTML_FILENAME}")
    if result.get("json") and Path(result["json"]).name != _AUDIT_JSON_FILENAME:
        errors.append(f"artifact_paths.json must end with {_AUDIT_JSON_FILENAME}")
    return result


def _validate_technical_refs(value: object, errors: list[str]) -> dict[str, str]:
    refs = _object(value, "technical_refs", errors)
    _exact_fields(refs, _TECHNICAL_REF_FIELDS, "technical_refs", errors)
    result: dict[str, str] = {}
    for field in sorted(_TECHNICAL_REF_FIELDS):
        try:
            result[field] = _absolute_path(refs.get(field), f"technical_refs.{field}")
        except KnowledgeAuditExplorerValidationError as exc:
            errors.extend(exc.errors)
            result[field] = ""
    return result


def _validate_source_bindings(
    sources: Mapping[str, Mapping[str, object]],
    refs: Mapping[str, str],
    errors: list[str],
) -> None:
    expected = {
        "manifest": refs.get("manifest_path"),
        "v1_atlas_html": refs.get("v1_atlas_html_path"),
        "v1_atlas_json": refs.get("v1_atlas_json_path"),
    }
    for name, path in expected.items():
        if _mapping(sources.get(name)).get("path") != path:
            errors.append(f"source_artifacts.{name}.path does not match technical_refs")


def _relabel_document(source: str, payload: Mapping[str, object]) -> str:
    run_id = html.escape(str(payload["run_id"]), quote=True)
    as_of = html.escape(str(payload["as_of"]), quote=True)
    schema = html.escape(AUDIT_EXPLORER_SCHEMA_VERSION, quote=True)
    title = (
        "<title>Knowledge Audit Explorer — технический аудит — "
        + html.escape(str(_mapping(payload["reporting_period"])["reporting_week"]))
        + "</title>"
    )
    rendered, count = re.subn(r"(?is)<title>.*?</title>", title, source, count=1)
    if count != 1:
        raise KnowledgeAuditExplorerValidationError(
            ["source_html title is missing or ambiguous"]
        )
    meta = (
        f'<meta name="knowledge-audit-explorer-schema" content="{schema}">\n'
        '<meta name="knowledge-audit-explorer-surface" '
        f'content="{AUDIT_EXPLORER_SURFACE}">\n'
    )
    if "</head>" not in rendered:
        raise KnowledgeAuditExplorerValidationError(
            ["source_html head element is not closed"]
        )
    rendered = rendered.replace("</head>", f"{meta}</head>", 1)
    notice = (
        '<aside id="knowledge-audit-explorer-banner" role="note" '
        'aria-label="Технический аудит" '
        'style="max-width:1180px;margin:16px auto;padding:16px 24px;'
        'border:2px solid #a16207;background:#fffbeb">'
        '<p class="kicker">Knowledge Audit Explorer · технический аудит</p>'
        f"<p><strong>{html.escape(TECHNICAL_NOTICE_RU)}</strong></p>"
        f'<p class="muted">Run: {run_id}. Состояние данных на: {as_of}. '
        "Исходные Atlas V1 JSON/HTML защищены дескрипторами в sidecar.</p>"
        "</aside>"
    )
    body_match = re.search(r"(?is)<body(?:\s[^>]*)?>", rendered)
    if body_match is None:
        raise KnowledgeAuditExplorerValidationError(
            ["source_html body element is missing"]
        )
    return rendered[: body_match.end()] + "\n" + notice + rendered[body_match.end() :]


def _render_missing_records(items: Sequence[Mapping[str, object]]) -> str:
    records = "".join(_render_missing_record(item) for item in items)
    return (
        '<section id="audit-collapsed-thread-records">'
        "<h2>Дополнительные технические записи тем</h2>"
        "<p>Эти записи добавлены закрытыми, чтобы каждый стабильный deep link "
        "из V1 thread navigation указывал на реальный элемент документа.</p>"
        f"{records}</section>"
    )


def _render_missing_record(item: Mapping[str, object]) -> str:
    anchor = html.escape(str(item.get("id") or ""), quote=True)
    slug = html.escape(str(item.get("slug") or ""), quote=True)
    title = html.escape(str(item.get("title") or "Тема"))
    status = html.escape(str(item.get("status") or "unknown"))
    maturity = html.escape(str(item.get("maturity") or "unknown"))
    understanding = html.escape(
        str(item.get("current_understanding") or "Нет описания.")
    )
    claims = _escaped_list(item.get("claims"), "Нет зафиксированных утверждений.")
    contradictions = _escaped_list(
        item.get("contradictions"), "Нет зафиксированных противоречий."
    )
    superseded = _escaped_list(item.get("superseded_claims"), "Нет superseded claims.")
    evidence = (
        "".join(
            "<li>"
            + html.escape(
                str(
                    row.get("claim")
                    or row.get("summary")
                    or "Доказательство без описания"
                )
            )
            + (
                f" — {html.escape(str(row.get('evidence_quote')))}"
                if row.get("evidence_quote")
                else ""
            )
            + "</li>"
            for row in _mapping_list(item.get("evidence_items"), "evidence_items", 6)
        )
        or "<li>Нет отображаемых доказательств.</li>"
    )
    sources = (
        "".join(
            f'<li><a href="{html.escape(str(url), quote=True)}">'
            f"{html.escape(str(url))}</a></li>"
            for url in item.get("source_urls") or []
            if _safe_http_url(url)
        )
        or "<li>Нет безопасных исходных ссылок.</li>"
    )
    timeline = _escaped_object_list(
        item.get("timeline"),
        empty="Timeline observations отсутствуют.",
    )
    project_connections = _escaped_object_list(
        item.get("project_connections"),
        empty="Project connections отсутствуют.",
    )
    decisions = _escaped_object_list(
        item.get("decisions"),
        empty="Decision diagnostics отсутствуют.",
    )
    diagnostics = html.escape(
        _audit_json(
            {
                "evidence_growth": item.get("evidence_growth"),
                "source_diversity": item.get("source_diversity"),
                "momentum_30d": item.get("momentum_30d"),
                "change_since_previous_period": item.get(
                    "change_since_previous_period"
                ),
            }
        )
    )
    return (
        f'<details id="{anchor}" class="thread-detail audit-collapsed-thread" '
        f'data-thread-ref="thread:{slug}">'
        f"<summary>{title} · {status} · {maturity}</summary>"
        f"<p>{understanding}</p>"
        f"<h3>Утверждения</h3>{claims}"
        f"<h3>Противоречия</h3>{contradictions}"
        f"<h3>Superseded claims</h3>{superseded}"
        f"<h3>Доказательства</h3><ul>{evidence}</ul>"
        f"<h3>Timeline</h3>{timeline}"
        f"<h3>Project connections</h3>{project_connections}"
        f"<h3>Decision diagnostics</h3>{decisions}"
        f"<h3>Open questions</h3>{_escaped_list(item.get('open_questions'), 'Нет open questions.')}"
        f"<h3>Study next</h3>{_escaped_list(item.get('study_next'), 'Нет study-next items.')}"
        f"<h3>Growth/source diagnostics</h3><p><code>{diagnostics}</code></p>"
        f"<h3>Исходные ссылки</h3><ul>{sources}</ul>"
        "</details>"
    )


def _render_canonical_records(items: Sequence[Mapping[str, object]]) -> str:
    records = "".join(_render_canonical_record(item) for item in items)
    return (
        '<section id="audit-canonical-thread-records">'
        "<h2>Канонический реестр и история идентичности</h2>"
        "<p>Закрытые записи сохраняют стабильные идентификаторы, aliases, "
        "raw memberships и merge/split provenance на границе периода.</p>"
        f"{records}</section>"
    )


def _render_canonical_record(item: Mapping[str, object]) -> str:
    anchor = html.escape(_canonical_anchor(item), quote=True)
    slug = html.escape(str(item.get("stable_slug") or ""), quote=True)
    canonical_id = html.escape(str(item.get("canonical_thread_id") or ""), quote=True)
    title = html.escape(str(item.get("title_ru") or slug or "Каноническая тема"))
    thesis = html.escape(str(item.get("thesis") or "Нет тезиса."))
    status = html.escape(str(item.get("status") or "unknown"))
    maturity = html.escape(str(item.get("evidence_maturity") or "unknown"))
    aliases = (
        "".join(
            "<li><code>"
            + html.escape(str(alias.get("alias_type") or "alias"))
            + ":</code> "
            + html.escape(str(alias.get("alias_value") or ""))
            + "</li>"
            for alias in _mapping_list(item.get("aliases"), "aliases", 100)
        )
        or "<li>Aliases отсутствуют.</li>"
    )
    raw_aliases = (
        "".join(
            "<li><code>"
            + html.escape(str(alias.get("alias_type") or "alias"))
            + ":</code> "
            + html.escape(str(alias.get("alias_value") or ""))
            + "</li>"
            for alias in _mapping_list(
                item.get("raw_thread_aliases"), "raw_thread_aliases", 100
            )
        )
        or "<li>Raw aliases отсутствуют.</li>"
    )
    raw_refs = (
        "".join(
            "<li><code>raw_thread:"
            + html.escape(str(ref.get("raw_thread_id") or ""))
            + "</code> · "
            + html.escape(str(ref.get("slug") or ref.get("title") or ""))
            + "</li>"
            for ref in _mapping_list(
                item.get("raw_thread_refs"), "raw_thread_refs", 100
            )
        )
        or "<li>Raw memberships отсутствуют.</li>"
    )
    ancestry = (
        "".join(
            f"<li><strong>{html.escape(label)}:</strong> "
            + html.escape(", ".join(str(value) for value in item.get(field) or []))
            + "</li>"
            for field, label in (
                ("merged_from", "merged from"),
                ("merged_into", "merged into"),
                ("split_from", "split from"),
                ("split_into", "split into"),
            )
            if item.get(field)
        )
        or "<li>Merge/split ancestry отсутствует.</li>"
    )
    lineage = (
        "".join(
            "<li><code>"
            + html.escape(str(row.get("relation_type") or "event"))
            + "</code> · "
            + html.escape(str(row.get("from_thread_id") or ""))
            + " → "
            + html.escape(str(row.get("to_thread_id") or ""))
            + " · "
            + html.escape(str(row.get("event_at") or ""))
            + (
                f" · decision {html.escape(str(row.get('decision_id')))}"
                if row.get("decision_id")
                else ""
            )
            + (f" · {html.escape(str(row.get('reason')))}" if row.get("reason") else "")
            + "</li>"
            for row in _mapping_list(item.get("lineage"), "lineage", 100)
        )
        or "<li>Lineage events отсутствуют.</li>"
    )
    sources = (
        "".join(
            f'<li><a href="{html.escape(str(url), quote=True)}">'
            f"{html.escape(str(url))}</a></li>"
            for url in item.get("source_urls") or []
            if _safe_http_url(url)
        )
        or "<li>Исходные ссылки отсутствуют.</li>"
    )
    claims = _escaped_list(item.get("current_claims"), "Current claims отсутствуют.")
    superseded = _escaped_list(
        item.get("superseded_claims"), "Superseded claims отсутствуют."
    )
    contradictions = _escaped_list(
        item.get("contradictions"), "Противоречия отсутствуют."
    )
    atoms = (
        "".join(
            _render_canonical_atom(atom)
            for atom in _mapping_list(item.get("atoms"), "atoms", 100)
        )
        or "<p>Полные atom records отсутствуют в bounded V1 projection.</p>"
    )
    membership = html.escape(
        _audit_json(
            {
                "raw_thread_ids": item.get("raw_thread_ids"),
                "atom_ids": item.get("atom_ids"),
                "source_post_ids": item.get("source_post_ids"),
                "source_refs": item.get("source_refs"),
            }
        )
    )
    diagnostics = html.escape(
        _audit_json(
            {
                "as_of": item.get("as_of"),
                "curator_version": item.get("curator_version"),
                "current_version": item.get("current_version"),
                "snapshot_fingerprint": item.get("snapshot_fingerprint"),
                "operator_interest": item.get("operator_interest"),
                "provenance_counts": item.get("provenance_counts"),
                "provenance_truncated": item.get("provenance_truncated"),
            }
        )
    )
    return (
        f'<details id="{anchor}" class="thread-detail audit-canonical-thread" '
        f'data-thread-ref="canonical_thread:{slug}">'
        f"<summary>{title} · {status} · {maturity}</summary>"
        f"<p>{thesis}</p>"
        f"<p><strong>Canonical ID:</strong> <code>{canonical_id}</code>; "
        f"<strong>stable slug:</strong> <code>{slug}</code>.</p>"
        f"<h3>Aliases</h3><ul>{aliases}</ul>"
        f"<h3>Raw aliases</h3><ul>{raw_aliases}</ul>"
        f"<h3>Raw memberships</h3><ul>{raw_refs}</ul>"
        f"<p><code>{membership}</code></p>"
        f"<h3>Merge/split ancestry</h3><ul>{ancestry}</ul>"
        f"<h3>Полная lineage history</h3><ol>{lineage}</ol>"
        f"<h3>Current claims</h3>{claims}"
        f"<h3>Superseded claims</h3>{superseded}"
        f"<h3>Contradictions</h3>{contradictions}"
        f"<h3>Atoms, quotes and source posts</h3>{atoms}"
        f"<h3>Исходные ссылки</h3><ul>{sources}</ul>"
        f"<h3>Curator/provenance diagnostics</h3><p><code>{diagnostics}</code></p>"
        "</details>"
    )


def _render_canonical_atom(atom: Mapping[str, object]) -> str:
    atom_id = html.escape(str(atom.get("id") or "unknown"))
    claim = html.escape(str(atom.get("claim") or "Claim отсутствует."))
    summary = html.escape(str(atom.get("summary") or ""))
    quote = html.escape(str(atom.get("evidence_quote") or ""))
    sources = (
        "".join(
            f'<li><a href="{html.escape(str(url), quote=True)}">'
            f"{html.escape(str(url))}</a></li>"
            for url in atom.get("source_urls") or []
            if _safe_http_url(url)
        )
        or "<li>Source URLs отсутствуют.</li>"
    )
    posts = (
        "".join(
            "<li><code>post:"
            + html.escape(str(post.get("post_id") or "unknown"))
            + "</code> · "
            + html.escape(str(post.get("channel_username") or ""))
            + " · "
            + html.escape(str(post.get("posted_at") or ""))
            + "<p>"
            + html.escape(str(post.get("content") or ""))
            + "</p></li>"
            for post in _mapping_list(atom.get("source_posts"), "source_posts", 100)
        )
        or "<li>Bound source posts отсутствуют.</li>"
    )
    diagnostics = html.escape(
        _audit_json(
            {
                key: atom.get(key)
                for key in (
                    "relation",
                    "atom_type",
                    "week_label",
                    "confidence",
                    "novelty_score",
                    "practical_utility_score",
                    "staleness_status",
                    "first_seen_at",
                    "last_seen_at",
                    "source_post_ids",
                )
            }
        )
    )
    return (
        '<article class="evidence-item">'
        f"<h4>Atom <code>{atom_id}</code></h4><p>{claim}</p>"
        + (f"<p>{summary}</p>" if summary else "")
        + (f"<p><strong>Evidence quote:</strong> {quote}</p>" if quote else "")
        + f"<p><code>{diagnostics}</code></p>"
        + f"<h4>Source URLs</h4><ul>{sources}</ul>"
        + f"<h4>Source posts</h4><ul>{posts}</ul>"
        + "</article>"
    )


def _escaped_list(value: object, empty: str) -> str:
    rows = value if isinstance(value, list) else []
    content = "".join(f"<li>{html.escape(str(item))}</li>" for item in rows)
    return f"<ul>{content or f'<li>{html.escape(empty)}</li>'}</ul>"


def _escaped_object_list(value: object, *, empty: str) -> str:
    rows = value if isinstance(value, list) else []
    content = "".join(
        f"<li><code>{html.escape(_audit_json(item))}</code></li>" for item in rows
    )
    return f"<ul>{content or f'<li>{html.escape(empty)}</li>'}</ul>"


def _audit_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


class _IdentityParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.identities: dict[str, int] = {}
        self.body_count = 0
        self.main_count = 0
        self.security_errors: list[str] = []
        self.doctype_count = 0
        self.tag_counts: dict[str, int] = {}
        self.end_tag_counts: dict[str, int] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        self.tag_counts[lowered] = self.tag_counts.get(lowered, 0) + 1
        if lowered not in _SAFE_HTML_TAGS:
            self.security_errors.append(f"uses forbidden <{lowered}> tag")
        if lowered == "body":
            self.body_count += 1
        elif lowered == "main":
            self.main_count += 1
        names = [name.lower() for name, _value in attrs]
        if len(names) != len(set(names)):
            self.security_errors.append(f"contains duplicate attributes on <{lowered}>")
        allowed = _GLOBAL_HTML_ATTRIBUTES | _TAG_HTML_ATTRIBUTES.get(lowered, set())
        for name, value in attrs:
            lowered_name = name.lower()
            if lowered_name not in allowed:
                self.security_errors.append(
                    f"uses forbidden {lowered_name} attribute on <{lowered}>"
                )
            if lowered_name == "id" and value is not None:
                self.identities[value] = self.identities.get(value, 0) + 1
                if not re.fullmatch(r"[A-Za-z][A-Za-z0-9._:-]{0,255}", value):
                    self.security_errors.append("contains an invalid id attribute")
            if lowered_name == "class" and value is not None:
                if not re.fullmatch(r"[A-Za-z0-9 _-]{1,500}", value):
                    self.security_errors.append("contains an invalid class attribute")
            if lowered_name == "href" and not _safe_html_href(value):
                self.security_errors.append("contains a non-HTTP(S)/fragment href")
            if lowered_name == "style" and not _safe_inline_style(value):
                self.security_errors.append("contains a forbidden inline style")
        if lowered == "meta" and not _safe_meta_attributes(attrs):
            self.security_errors.append("contains an invalid or active meta element")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        self.end_tag_counts[lowered] = self.end_tag_counts.get(lowered, 0) + 1
        if lowered not in _SAFE_HTML_TAGS:
            self.security_errors.append(f"uses forbidden </{lowered}> tag")

    def handle_comment(self, data: str) -> None:
        self.security_errors.append("contains an HTML comment")

    def handle_decl(self, decl: str) -> None:
        if decl.strip().lower() != "doctype html":
            self.security_errors.append("contains a non-HTML5 declaration")
        self.doctype_count += 1

    def handle_pi(self, data: str) -> None:
        self.security_errors.append("contains a processing instruction")


def _safe_html_href(value: object) -> bool:
    if not isinstance(value, str) or value != value.strip():
        return False
    if re.fullmatch(r"#[A-Za-z][A-Za-z0-9._:-]{0,255}", value):
        return True
    return _safe_http_url(value)


def _safe_inline_style(value: object) -> bool:
    if not isinstance(value, str) or value != value.strip():
        return False
    if value == _SAFE_BANNER_STYLE:
        return True
    return re.fullmatch(r"width:(?:100|[1-9]?\d)%", value) is not None


def _safe_meta_attributes(attrs: Sequence[tuple[str, str | None]]) -> bool:
    values = {name.lower(): value for name, value in attrs}
    if set(values) == {"charset"}:
        return str(values["charset"] or "").lower() == "utf-8"
    if set(values) != {"name", "content"}:
        return False
    name = str(values["name"] or "")
    content = str(values["content"] or "")
    return (
        re.fullmatch(r"[A-Za-z][A-Za-z0-9._:-]{0,127}", name) is not None
        and len(content) <= _MAX_PATH
        and not any(ord(character) < 32 for character in content)
    )


def _unsafe_css(value: str) -> bool:
    blocks = re.findall(r"(?is)<style(?:\s[^>]*)?>(.*?)</style>", value)
    if len(blocks) != 1:
        return True
    encoded = blocks[0].encode("utf-8")
    return (
        len(encoded) > 100_000
        or hashlib.sha256(encoded).hexdigest() != _V1_STYLESHEET_SHA256
    )


def _json_object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise KnowledgeAuditExplorerValidationError([f"{label} must be an object"])
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError, OverflowError) as exc:
        raise KnowledgeAuditExplorerValidationError(
            [f"{label} must be strict JSON"]
        ) from exc
    if len(encoded) > _MAX_JSON_BYTES:
        raise KnowledgeAuditExplorerValidationError(
            [f"{label} exceeds {_MAX_JSON_BYTES} bytes"]
        )
    result = json.loads(encoded)
    if not isinstance(result, dict):
        raise KnowledgeAuditExplorerValidationError([f"{label} must be an object"])
    return result


def _absolute_path(value: object, label: str) -> str:
    if not isinstance(value, (str, os.PathLike)):
        raise KnowledgeAuditExplorerValidationError(
            [f"{label} must be an absolute path"]
        )
    text = os.fspath(value)
    if (
        not text
        or len(text) > _MAX_PATH
        or "\x00" in text
        or any(ord(character) < 32 for character in text)
        or text.startswith("//")
        or not Path(text).is_absolute()
    ):
        raise KnowledgeAuditExplorerValidationError(
            [f"{label} must be an absolute path"]
        )
    if ".." in Path(text).parts:
        raise KnowledgeAuditExplorerValidationError(
            [f"{label} must not contain traversal"]
        )
    normalized = os.path.normpath(text)
    if normalized != text:
        raise KnowledgeAuditExplorerValidationError(
            [f"{label} must be lexically canonical"]
        )
    return normalized


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_list(value: object, label: str, maximum: int) -> list[dict[str, object]]:
    if (
        not isinstance(value, list)
        or len(value) > maximum
        or any(not isinstance(item, Mapping) for item in value)
    ):
        raise KnowledgeAuditExplorerValidationError(
            [f"{label} must be an object list bounded to {maximum}"]
        )
    return [dict(item) for item in value]


def _object(value: object, path: str, errors: list[str]) -> dict[str, object]:
    if not isinstance(value, Mapping):
        errors.append(f"{path} must be an object")
        return {}
    return dict(value)


def _object_list(
    value: object, path: str, errors: list[str], maximum: int
) -> list[dict[str, object]]:
    if not isinstance(value, list):
        errors.append(f"{path} must be a list")
        return []
    if len(value) > maximum:
        errors.append(f"{path} exceeds limit {maximum}")
    result: list[dict[str, object]] = []
    for index, item in enumerate(value[:maximum]):
        if not isinstance(item, Mapping):
            errors.append(f"{path}[{index}] must be an object")
        else:
            result.append(dict(item))
    return result


def _exact_fields(
    value: Mapping[str, object], expected: set[str], path: str, errors: list[str]
) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing:
        errors.append(f"{path} missing fields: {', '.join(missing)}")
    if unknown:
        errors.append(f"{path} unknown fields: {', '.join(unknown)}")


def _equal(actual: object, expected: object, path: str, errors: list[str]) -> None:
    if actual != expected:
        errors.append(f"{path} mismatch")


def _bounded_string(
    value: object, path: str, errors: list[str], *, maximum: int = _MAX_TEXT
) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        errors.append(f"{path} must be non-empty bounded text")
    elif any(ord(character) < 32 and character not in "\n\r\t" for character in value):
        errors.append(f"{path} contains control characters")


def _non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _finite_number(value: object) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, TypeError, ValueError):
        return False


def _duplicates(values: Sequence[str], label: str, errors: list[str]) -> None:
    if any(not value for value in values) or len(values) != len(set(values)):
        errors.append(f"{label} must be non-empty and duplicate-free")


def _unique_scalar_list(
    value: object, path: str, errors: list[str], maximum: int
) -> None:
    if not isinstance(value, list) or len(value) > maximum:
        errors.append(f"{path} must be a bounded list")
        return
    markers = [json.dumps(item, ensure_ascii=False, sort_keys=True) for item in value]
    if len(markers) != len(set(markers)):
        errors.append(f"{path} must be duplicate-free")


def _validate_urls(value: object, path: str, errors: list[str]) -> None:
    if not isinstance(value, list):
        return
    for index, item in enumerate(value):
        if not _safe_http_url(item):
            errors.append(f"{path}[{index}] must be an absolute HTTP(S) URL")


def _safe_http_url(value: object) -> bool:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > 2_048
        or re.search(r"[\x00-\x20\x7f<>\"'\\]", value)
    ):
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme.lower() in {"http", "https"}
        and bool(parsed.netloc)
        and parsed.hostname is not None
        and parsed.username is None
        and parsed.password is None
        and (port is None or 1 <= port <= 65_535)
        and not any(
            segment in {".", ".."}
            for segment in unquote(parsed.path).split("/")
        )
    )


def _same_utc_instant(left: object, right: object) -> bool:
    try:
        left_value = datetime.fromisoformat(str(left).replace("Z", "+00:00"))
        right_value = datetime.fromisoformat(str(right).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if left_value.tzinfo is None or right_value.tzinfo is None:
        return False
    return left_value.astimezone(timezone.utc) == right_value.astimezone(timezone.utc)


def _count_or_length(value: object, sequence: object, path: str) -> int:
    if value is None:
        return len(sequence) if isinstance(sequence, list) else 0
    if not _non_negative_int(value):
        raise KnowledgeAuditExplorerValidationError([f"{path} is invalid"])
    return int(value)


def _positive_int(value: object, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise KnowledgeAuditExplorerValidationError([f"{path} is invalid"])
    return value

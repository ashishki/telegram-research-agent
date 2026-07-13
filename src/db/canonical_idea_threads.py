"""IRX-4 additive canonical Idea Thread persistence and lifecycle history.

The existing ``idea_threads`` and ``idea_thread_atoms`` tables are mutable raw
compatibility projections.  This module never rewrites them.  Canonical state
is incremental, versioned, and resolved from stored temporal memberships.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping, Sequence


CANONICAL_THREAD_STATUSES = frozenset(
    {"active", "stale", "merged", "split", "resolved", "archived"}
)
ACTIVE_CANONICAL_THREAD_STATUSES = frozenset({"active", "stale"})
TERMINAL_CANONICAL_THREAD_STATUSES = frozenset({"merged", "split", "archived"})
EVIDENCE_MATURITY_LEVELS = (
    "single_source",
    "repeated_signal",
    "multi_channel",
    "primary_verified",
    "externally_corroborated",
    "decision_grade",
)
LIFECYCLE_OPERATIONS = frozenset(
    {"create", "update", "merge", "split", "stale", "operator_correction"}
)
AUDIT_ONLY_OPERATIONS = frozenset({"keep_separate", "keep_together", "defer"})
CURATOR_OPERATIONS = LIFECYCLE_OPERATIONS | AUDIT_ONLY_OPERATIONS
ATOM_RELATIONS = frozenset({"supports", "contradicts", "supersedes", "related"})
ALIAS_TYPES = frozenset(
    {
        "raw_thread_id",
        "raw_thread_slug",
        "compatibility_ref",
        "legacy_ref",
        "title",
        "model_version",
        "manual",
    }
)
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_CANONICAL_ID_RE = re.compile(r"^ct_[0-9a-f]{24}$")
_ENVELOPE_KEYS = frozenset(
    {
        "schema_version",
        "run_id",
        "operation",
        "model",
        "model_version",
        "curator_version",
        "reason",
        "evidence",
        "proposal_id",
        "decision_id",
        "proposed_at",
        "actor",
        "contract_version",
        "status",
        "applied",
        "requires_deterministic_validation",
        "mutation_policy",
        "suggested_identity",
    }
)


class CanonicalLifecycleError(ValueError):
    """Raised when deterministic canonical lifecycle validation fails."""

    def __init__(self, errors: str | Iterable[str]):
        if isinstance(errors, str):
            normalized = (errors,)
        else:
            normalized = tuple(str(error) for error in errors if str(error).strip())
        self.errors = normalized or ("canonical lifecycle validation failed",)
        super().__init__("; ".join(self.errors))


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_value(value: object, fallback: object) -> object:
    if value is None:
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _rows(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    columns = [str(description[0]) for description in cursor.description or ()]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _row(cursor: sqlite3.Cursor) -> dict[str, Any] | None:
    rows = _rows(cursor)
    return rows[0] if rows else None


def _clean_required(value: object, field_name: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not text:
        raise CanonicalLifecycleError(f"{field_name} is required")
    return text


def _normalized_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(text.split()).casefold()


def _normalize_string_list(values: object) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, Iterable) or isinstance(values, (bytes, Mapping)):
        raise CanonicalLifecycleError("entities must be a list of strings")
    deduplicated: dict[str, str] = {}
    for value in values:
        clean = unicodedata.normalize("NFKC", str(value or "")).strip()
        if clean:
            deduplicated.setdefault(_normalized_text(clean), clean)
    return [deduplicated[key] for key in sorted(deduplicated)]


def normalize_canonical_utc(value: object, field_name: str = "timestamp") -> str:
    """Return an aware timestamp as deterministic UTC with a ``Z`` suffix."""

    if isinstance(value, datetime):
        parsed = value
    else:
        text = _clean_required(value, field_name)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise CanonicalLifecycleError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CanonicalLifecycleError(f"{field_name} requires an explicit timezone")
    normalized = parsed.astimezone(timezone.utc)
    # Fixed precision is intentional: temporal predicates are indexed SQLite
    # text comparisons, so seconds and fractional-seconds forms must never be
    # mixed (``...00Z`` sorts after ``...00.000001Z`` lexically).
    return normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _now_utc() -> str:
    return normalize_canonical_utc(datetime.now(timezone.utc))


def _utc_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def normalize_stable_slug(value: object) -> str:
    slug = _clean_required(value, "stable_slug")
    if slug != slug.lower() or not _SLUG_RE.fullmatch(slug) or len(slug) > 96:
        raise CanonicalLifecycleError(
            "stable_slug must be 1-96 lowercase ASCII letters/digits separated by single hyphens"
        )
    return slug


def stable_canonical_thread_id(stable_slug: object) -> str:
    slug = normalize_stable_slug(stable_slug)
    return "ct_" + hashlib.sha256(slug.encode("utf-8")).hexdigest()[:24]


def _normalize_canonical_id(value: object, *, stable_slug: str | None = None) -> str:
    canonical_thread_id = _clean_required(value, "canonical_thread_id")
    if not _CANONICAL_ID_RE.fullmatch(canonical_thread_id):
        raise CanonicalLifecycleError(
            "canonical_thread_id must be ct_ followed by 24 lowercase hexadecimal characters"
        )
    if stable_slug is not None and canonical_thread_id != stable_canonical_thread_id(stable_slug):
        raise CanonicalLifecycleError(
            "canonical_thread_id must be the deterministic identity derived from stable_slug"
        )
    return canonical_thread_id


def _normalize_operation(value: object) -> str:
    operation = _clean_required(value, "operation")
    if operation not in CURATOR_OPERATIONS:
        raise CanonicalLifecycleError(
            "unsupported operation; expected one of " + ", ".join(sorted(CURATOR_OPERATIONS))
        )
    return operation


def _payload(proposal: Mapping[str, object]) -> dict[str, object]:
    nested = proposal.get("payload")
    if isinstance(nested, Mapping):
        result = dict(nested)
        for key, value in proposal.items():
            if key not in _ENVELOPE_KEYS and key != "payload":
                result.setdefault(key, value)
        return result
    return {key: value for key, value in proposal.items() if key not in _ENVELOPE_KEYS}


def _metadata_value(
    proposal: Mapping[str, object], explicit: object, key: str, *, default: object = None
) -> object:
    embedded = proposal.get(key)
    if explicit is not None and embedded is not None and str(explicit) != str(embedded):
        raise CanonicalLifecycleError(f"explicit {key} conflicts with proposal envelope")
    if explicit is not None:
        return explicit
    if embedded is not None:
        return embedded
    return default


def _history_condition(as_of: str | None, *, prefix: str = "") -> tuple[str, list[object]]:
    qualified = f"{prefix}." if prefix else ""
    if as_of is None:
        return f"{qualified}valid_to IS NULL", []
    return (
        f"{qualified}valid_from < ? AND "
        f"({qualified}valid_to IS NULL OR {qualified}valid_to >= ?)",
        [as_of, as_of],
    )


def _thread_from_row(row: Mapping[str, object]) -> dict[str, object]:
    version = row.get("current_version", row.get("version", 1))
    return {
        "canonical_thread_id": str(row["canonical_thread_id"]),
        "stable_slug": str(row["stable_slug"]),
        "title_ru": str(row["title_ru"]),
        "title_en": str(row["title_en"]),
        "thesis": str(row["thesis"]),
        "status": str(row["status"]),
        "first_seen_at": str(row["first_seen_at"]),
        "last_seen_at": str(row["last_seen_at"]),
        "evidence_maturity": str(row["evidence_maturity"]),
        "operator_interest": float(row["operator_interest"] or 0.0),
        "entities": _normalize_string_list(_json_value(row.get("entities_json"), [])),
        "curator_version": str(row["curator_version"]),
        "current_version": int(version or 1),
        "valid_from": str(row.get("valid_from") or row.get("created_at") or ""),
        "valid_to": str(row["valid_to"]) if row.get("valid_to") else None,
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or row.get("created_at") or ""),
    }


def _membership_rows(
    connection: sqlite3.Connection,
    canonical_thread_id: str,
    *,
    as_of: str | None,
) -> list[dict[str, Any]]:
    condition, params = _history_condition(as_of, prefix="membership")
    return _rows(
        connection.execute(
            f"""
            SELECT
                membership.atom_id,
                membership.raw_thread_id,
                membership.relation,
                membership.valid_from,
                membership.valid_to,
                atom.atom_type,
                atom.claim,
                atom.summary,
                atom.evidence_quote,
                atom.source_post_ids_json,
                atom.source_urls_json,
                atom.entities_json,
                atom.confidence,
                atom.staleness_status,
                atom.first_seen_at AS atom_first_seen_at,
                atom.last_seen_at AS atom_last_seen_at
            FROM canonical_idea_thread_atom_history AS membership
            JOIN knowledge_atoms AS atom ON atom.id = membership.atom_id
            WHERE membership.canonical_thread_id = ? AND {condition}
            ORDER BY membership.atom_id
            """,
            [canonical_thread_id, *params],
        )
    )


def _alias_rows(
    connection: sqlite3.Connection,
    canonical_thread_id: str,
    *,
    as_of: str | None,
) -> list[dict[str, Any]]:
    condition, params = _history_condition(as_of)
    return _rows(
        connection.execute(
            f"""
            SELECT alias_type, alias_value, normalized_alias, valid_from, valid_to
            FROM canonical_idea_thread_alias_history
            WHERE canonical_thread_id = ? AND {condition}
            ORDER BY alias_type, normalized_alias, alias_value
            """,
            [canonical_thread_id, *params],
        )
    )


def _lineage_rows(
    connection: sqlite3.Connection,
    canonical_thread_id: str,
    *,
    as_of: str | None,
) -> list[dict[str, Any]]:
    clauses = ["(from_thread_id = ? OR to_thread_id = ?)"]
    params: list[object] = [canonical_thread_id, canonical_thread_id]
    if as_of is not None:
        clauses.append("event_at < ?")
        params.append(as_of)
    return _rows(
        connection.execute(
            f"""
            SELECT relation_type, from_thread_id, to_thread_id, decision_id, event_at, reason
            FROM canonical_idea_thread_lineage
            WHERE {' AND '.join(clauses)}
            ORDER BY event_at, relation_type, from_thread_id, to_thread_id
            """,
            params,
        )
    )


def _enrich_thread(
    connection: sqlite3.Connection,
    thread: Mapping[str, object],
    *,
    as_of: str | None,
    include_atoms: bool,
    atom_limit: int,
) -> dict[str, object]:
    result = dict(thread)
    canonical_thread_id = str(result["canonical_thread_id"])
    memberships = _membership_rows(connection, canonical_thread_id, as_of=as_of)
    aliases = _alias_rows(connection, canonical_thread_id, as_of=as_of)
    lineage = _lineage_rows(connection, canonical_thread_id, as_of=as_of)
    atom_ids = [int(row["atom_id"]) for row in memberships]
    source_post_ids: set[int] = set()
    source_urls: set[str] = set()
    source_refs: list[dict[str, object]] = []
    provenance_entities = {_normalized_text(value): value for value in result["entities"]}
    atoms: list[dict[str, object]] = []
    for row in memberships:
        post_ids = sorted(
            {
                int(value)
                for value in _json_value(row.get("source_post_ids_json"), [])
                if str(value).strip().isdigit()
            }
        )
        urls = sorted(
            {
                str(value).strip()
                for value in _json_value(row.get("source_urls_json"), [])
                if str(value).strip()
            }
        )
        source_post_ids.update(post_ids)
        source_urls.update(urls)
        for entity in _normalize_string_list(_json_value(row.get("entities_json"), [])):
            provenance_entities.setdefault(_normalized_text(entity), entity)
        source_refs.append(
            {
                "atom_id": int(row["atom_id"]),
                "source_post_ids": post_ids,
                "source_urls": urls,
            }
        )
        if include_atoms and len(atoms) < atom_limit:
            atoms.append(
                {
                    "atom_id": int(row["atom_id"]),
                    "raw_thread_id": (
                        int(row["raw_thread_id"]) if row.get("raw_thread_id") is not None else None
                    ),
                    "relation": str(row["relation"]),
                    "atom_type": str(row["atom_type"]),
                    "claim": str(row["claim"]),
                    "summary": str(row["summary"] or ""),
                    "evidence_quote": str(row["evidence_quote"]),
                    "source_post_ids": post_ids,
                    "source_urls": urls,
                    "entities": _normalize_string_list(
                        _json_value(row.get("entities_json"), [])
                    ),
                    "confidence": float(row["confidence"] or 0.0),
                    "staleness_status": str(row["staleness_status"]),
                    "first_seen_at": str(row["atom_first_seen_at"]),
                    "last_seen_at": str(row["atom_last_seen_at"]),
                }
            )
    raw_thread_ids = sorted(
        {int(row["raw_thread_id"]) for row in memberships if row.get("raw_thread_id") is not None}
    )
    raw_thread_refs: list[dict[str, object]] = []
    if raw_thread_ids:
        placeholders = ",".join("?" for _ in raw_thread_ids)
        raw_thread_refs = _rows(
            connection.execute(
                f"""
                SELECT id AS raw_thread_id, slug, title, status
                FROM idea_threads
                WHERE id IN ({placeholders})
                ORDER BY id
                """,
                raw_thread_ids,
            )
        )
        for raw_ref in raw_thread_refs:
            raw_ref["raw_thread_id"] = int(raw_ref["raw_thread_id"])
    alias_values = [
        {"alias_type": str(row["alias_type"]), "alias_value": str(row["alias_value"])}
        for row in aliases
    ]
    raw_alias_types = {"raw_thread_id", "raw_thread_slug", "compatibility_ref"}
    result.update(
        {
            "as_of": as_of,
            "atom_ids": atom_ids,
            "atom_count": len(atom_ids),
            "source_post_ids": sorted(source_post_ids),
            "source_urls": sorted(source_urls),
            "source_refs": source_refs,
            "raw_thread_ids": raw_thread_ids,
            "raw_thread_refs": raw_thread_refs,
            "raw_thread_aliases": [
                value for value in alias_values if value["alias_type"] in raw_alias_types
            ],
            "aliases": alias_values,
            "entities": [provenance_entities[key] for key in sorted(provenance_entities)],
            "merged_from": sorted(
                {
                    str(row["from_thread_id"])
                    for row in lineage
                    if row["relation_type"] == "merge"
                    and row["to_thread_id"] == canonical_thread_id
                }
            ),
            "merged_into": sorted(
                {
                    str(row["to_thread_id"])
                    for row in lineage
                    if row["relation_type"] == "merge"
                    and row["from_thread_id"] == canonical_thread_id
                }
            ),
            "split_from": sorted(
                {
                    str(row["from_thread_id"])
                    for row in lineage
                    if row["relation_type"] == "split"
                    and row["to_thread_id"] == canonical_thread_id
                }
            ),
            "split_into": sorted(
                {
                    str(row["to_thread_id"])
                    for row in lineage
                    if row["relation_type"] == "split"
                    and row["from_thread_id"] == canonical_thread_id
                }
            ),
            "lineage": lineage,
        }
    )
    fingerprint_payload = {
        key: value
        for key, value in result.items()
        if key not in {"snapshot_fingerprint", "atoms", "created_at", "updated_at"}
    }
    result["snapshot_fingerprint"] = hashlib.sha256(
        _canonical_json(fingerprint_payload).encode("utf-8")
    ).hexdigest()
    if include_atoms:
        result["atoms"] = atoms
        result["atoms_truncated"] = len(atom_ids) > atom_limit
    return result


def fetch_canonical_threads(
    connection: sqlite3.Connection,
    *,
    as_of: object | None = None,
    status: str | None = None,
    limit: int = 100,
    include_atoms: bool = False,
    atom_limit: int = 100,
) -> list[dict[str, object]]:
    """Read current or exclusive-period-end canonical snapshots.

    When ``as_of`` is supplied, lifecycle events whose ``valid_from`` equals
    that boundary are excluded and the version closed at that boundary remains
    visible.  This is the report-period interpretation of half-open history.
    """

    boundary = normalize_canonical_utc(as_of, "as_of") if as_of is not None else None
    params: list[object] = []
    clauses: list[str] = []
    if boundary is None:
        clauses.append("version.valid_to IS NULL")
        status_column = "current.status"
        sort_prefix = "current"
        query = """
            SELECT current.*, version.valid_from, version.valid_to
            FROM canonical_idea_threads AS current
            JOIN canonical_idea_thread_versions AS version
              ON version.canonical_thread_id = current.canonical_thread_id
        """
    else:
        status_column = "version.status"
        sort_prefix = "version"
        clauses.extend(["version.valid_from < ?", "(version.valid_to IS NULL OR version.valid_to >= ?)"])
        params.extend([boundary, boundary])
        query = """
            SELECT
                version.*,
                version.version AS current_version,
                version.created_at AS updated_at
            FROM canonical_idea_thread_versions AS version
        """
    if status is not None:
        clean_status = _clean_required(status, "status")
        if clean_status not in CANONICAL_THREAD_STATUSES:
            raise CanonicalLifecycleError("unsupported canonical thread status")
        clauses.append(f"{status_column} = ?")
        params.append(clean_status)
    where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""
    rows = _rows(
        connection.execute(
            query
            + f"""
            {where_sql}
            ORDER BY
                CASE {sort_prefix}.status
                    WHEN 'active' THEN 0 WHEN 'stale' THEN 1 ELSE 2 END,
                {sort_prefix}.operator_interest DESC,
                {sort_prefix}.last_seen_at DESC,
                {sort_prefix}.stable_slug ASC
            LIMIT ?
            """,
            [*params, max(1, int(limit))],
        )
    )
    return [
        _enrich_thread(
            connection,
            _thread_from_row(row),
            as_of=boundary,
            include_atoms=bool(include_atoms),
            atom_limit=max(1, int(atom_limit)),
        )
        for row in rows
    ]


def fetch_canonical_thread(
    connection: sqlite3.Connection,
    canonical_thread_id: object,
    *,
    as_of: object | None = None,
    include_atoms: bool = False,
    atom_limit: int = 100,
) -> dict[str, object] | None:
    clean_id = _normalize_canonical_id(canonical_thread_id)
    for thread in fetch_canonical_threads(
        connection,
        as_of=as_of,
        limit=100000,
        include_atoms=include_atoms,
        atom_limit=atom_limit,
    ):
        if thread["canonical_thread_id"] == clean_id:
            return thread
    return None


def resolve_canonical_thread(
    connection: sqlite3.Connection,
    ref: object,
    *,
    alias_type: str | None = None,
    as_of: object | None = None,
    include_atoms: bool = False,
) -> dict[str, object] | None:
    """Resolve a stable ID/slug or a versioned alias without semantic guessing."""

    clean_ref = _clean_required(ref, "ref")
    boundary = normalize_canonical_utc(as_of, "as_of") if as_of is not None else None
    candidates = fetch_canonical_threads(
        connection, as_of=boundary, limit=100000, include_atoms=include_atoms
    )
    direct = [
        thread
        for thread in candidates
        if clean_ref in {thread["canonical_thread_id"], thread["stable_slug"]}
    ]
    if len(direct) == 1:
        return direct[0]
    normalized_alias = _normalized_text(clean_ref)
    condition, params = _history_condition(boundary)
    clauses = ["normalized_alias = ?", condition]
    query_params: list[object] = [normalized_alias, *params]
    if alias_type is not None:
        clean_alias_type = _clean_required(alias_type, "alias_type")
        if clean_alias_type not in ALIAS_TYPES:
            raise CanonicalLifecycleError("unsupported alias_type")
        clauses.append("alias_type = ?")
        query_params.append(clean_alias_type)
    rows = _rows(
        connection.execute(
            f"""
            SELECT DISTINCT canonical_thread_id
            FROM canonical_idea_thread_alias_history
            WHERE {' AND '.join(clauses)}
            ORDER BY canonical_thread_id
            """,
            query_params,
        )
    )
    owner_ids = {str(row["canonical_thread_id"]) for row in rows}
    if len(owner_ids) != 1:
        return None
    return fetch_canonical_thread(
        connection,
        owner_ids.pop(),
        as_of=boundary,
        include_atoms=include_atoms,
    )


def resolve_canonical_atoms(
    connection: sqlite3.Connection,
    atom_ids: Iterable[int],
    *,
    as_of: object | None = None,
    include_atoms: bool = False,
) -> dict[str, object] | None:
    """Return one stored owner only when every requested atom shares it."""

    requested = sorted({int(atom_id) for atom_id in atom_ids})
    if not requested:
        return None
    boundary = normalize_canonical_utc(as_of, "as_of") if as_of is not None else None
    placeholders = ",".join("?" for _ in requested)
    condition, params = _history_condition(boundary)
    rows = _rows(
        connection.execute(
            f"""
            SELECT atom_id, canonical_thread_id
            FROM canonical_idea_thread_atom_history
            WHERE atom_id IN ({placeholders}) AND {condition}
            ORDER BY atom_id, canonical_thread_id
            """,
            [*requested, *params],
        )
    )
    owners_by_atom: dict[int, set[str]] = {atom_id: set() for atom_id in requested}
    for row in rows:
        owners_by_atom[int(row["atom_id"])].add(str(row["canonical_thread_id"]))
    if any(len(owners) != 1 for owners in owners_by_atom.values()):
        return None
    common = set.intersection(*(owners for owners in owners_by_atom.values()))
    if len(common) != 1:
        return None
    return fetch_canonical_thread(
        connection, common.pop(), as_of=boundary, include_atoms=include_atoms
    )


def fetch_canonical_provenance(
    connection: sqlite3.Connection,
    canonical_thread_id: object,
    *,
    as_of: object | None = None,
    atom_limit: int = 1000,
) -> dict[str, object] | None:
    return fetch_canonical_thread(
        connection,
        canonical_thread_id,
        as_of=as_of,
        include_atoms=True,
        atom_limit=atom_limit,
    )


def _decision_from_row(row: Mapping[str, object]) -> dict[str, object]:
    return {
        "decision_id": str(row["decision_id"]),
        "proposal_id": str(row["decision_id"]),
        "run_id": str(row["run_id"]),
        "operation": str(row["operation"]),
        "proposal": _json_value(row.get("proposal_json"), {}),
        "evidence": _json_value(row.get("evidence_json"), []),
        "model": str(row["model"]),
        "model_version": str(row["model_version"]),
        "curator_version": str(row["curator_version"]),
        "reason": str(row["reason"]),
        "validation_status": str(row["validation_status"]),
        "validation_errors": _json_value(row.get("validation_errors_json"), []),
        "decision_status": str(row["decision_status"]),
        "actor": str(row["actor"]),
        "proposed_at": str(row["proposed_at"]),
        "validated_at": str(row["validated_at"]) if row.get("validated_at") else None,
        "applied_at": str(row["applied_at"]) if row.get("applied_at") else None,
        "result": _json_value(row.get("result_json"), None),
    }


def fetch_curator_decision(
    connection: sqlite3.Connection, decision_id: object
) -> dict[str, object] | None:
    row = _row(
        connection.execute(
            """
            SELECT *
            FROM canonical_idea_thread_curator_decisions
            WHERE decision_id = ?
            LIMIT 1
            """,
            (_clean_required(decision_id, "decision_id"),),
        )
    )
    return _decision_from_row(row) if row else None


def _record_curator_proposal(
    connection: sqlite3.Connection,
    *,
    proposal: Mapping[str, object],
    run_id: object | None = None,
    operation: object | None = None,
    model: object | None = None,
    model_version: object | None = None,
    curator_version: object | None = None,
    reason: object | None = None,
    proposed_at: object | None = None,
    actor: object | None = None,
    commit: bool,
) -> dict[str, object]:
    """Insert/read one proposal, optionally committing for the public wrapper."""

    if not isinstance(proposal, Mapping):
        raise CanonicalLifecycleError("proposal must be an object")
    clean_run_id = _clean_required(
        _metadata_value(proposal, run_id, "run_id"), "run_id"
    )
    clean_operation = _normalize_operation(
        _metadata_value(proposal, operation, "operation")
    )
    clean_model = _clean_required(_metadata_value(proposal, model, "model"), "model")
    clean_model_version = _clean_required(
        _metadata_value(proposal, model_version, "model_version"), "model_version"
    )
    clean_curator_version = _clean_required(
        _metadata_value(proposal, curator_version, "curator_version"), "curator_version"
    )
    clean_reason = _clean_required(
        _metadata_value(proposal, reason, "reason"), "reason"
    )
    clean_actor = _clean_required(
        _metadata_value(proposal, actor, "actor", default="curator"), "actor"
    )
    timestamp = normalize_canonical_utc(
        _metadata_value(proposal, proposed_at, "proposed_at", default=_now_utc()),
        "proposed_at",
    )
    stored_proposal = dict(proposal)
    identity_proposal = {
        key: value
        for key, value in stored_proposal.items()
        if key not in {"proposal_id", "decision_id", "proposed_at", "status", "applied"}
    }
    identity_payload = {
        "run_id": clean_run_id,
        "operation": clean_operation,
        "proposal": identity_proposal,
        "model": clean_model,
        "model_version": clean_model_version,
        "curator_version": clean_curator_version,
        "reason": clean_reason,
        "actor": clean_actor,
    }
    decision_id = "ccd_" + hashlib.sha256(
        _canonical_json(identity_payload).encode("utf-8")
    ).hexdigest()[:24]
    evidence = proposal.get("evidence", [])
    if not isinstance(evidence, (list, dict)):
        raise CanonicalLifecycleError("evidence must be a JSON list or object")
    connection.execute(
        """
        INSERT INTO canonical_idea_thread_curator_decisions (
            decision_id,
            run_id,
            operation,
            proposal_json,
            evidence_json,
            model,
            model_version,
            curator_version,
            reason,
            validation_status,
            validation_errors_json,
            decision_status,
            actor,
            proposed_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', '[]', 'proposed', ?, ?, ?, ?)
        ON CONFLICT(decision_id) DO NOTHING
        """,
        (
            decision_id,
            clean_run_id,
            clean_operation,
            _canonical_json(stored_proposal),
            _canonical_json(evidence),
            clean_model,
            clean_model_version,
            clean_curator_version,
            clean_reason,
            clean_actor,
            timestamp,
            timestamp,
            timestamp,
        ),
    )
    if commit:
        connection.commit()
    recorded = fetch_curator_decision(connection, decision_id)
    if recorded is None:
        raise RuntimeError("curator proposal could not be read back")
    return recorded


def record_curator_proposal(
    connection: sqlite3.Connection,
    *,
    proposal: Mapping[str, object],
    run_id: object | None = None,
    operation: object | None = None,
    model: object | None = None,
    model_version: object | None = None,
    curator_version: object | None = None,
    reason: object | None = None,
    proposed_at: object | None = None,
    actor: object | None = None,
) -> dict[str, object]:
    """Persist a proposal without mutating canonical lifecycle state."""

    return _record_curator_proposal(
        connection,
        proposal=proposal,
        run_id=run_id,
        operation=operation,
        model=model,
        model_version=model_version,
        curator_version=curator_version,
        reason=reason,
        proposed_at=proposed_at,
        actor=actor,
        commit=True,
    )


def _current_thread_row(
    connection: sqlite3.Connection, canonical_thread_id: str
) -> dict[str, Any] | None:
    return _row(
        connection.execute(
            """
            SELECT current.*, version.valid_from, version.valid_to
            FROM canonical_idea_threads AS current
            JOIN canonical_idea_thread_versions AS version
              ON version.canonical_thread_id = current.canonical_thread_id
             AND version.valid_to IS NULL
            WHERE current.canonical_thread_id = ?
            LIMIT 1
            """,
            (canonical_thread_id,),
        )
    )


def _current_snapshot(
    connection: sqlite3.Connection, canonical_thread_id: str
) -> dict[str, object] | None:
    row = _current_thread_row(connection, canonical_thread_id)
    return _thread_from_row(row) if row else None


def _normalize_thread_descriptor(
    descriptor: Mapping[str, object],
    *,
    base: Mapping[str, object] | None,
    curator_version: str,
) -> dict[str, object]:
    if not isinstance(descriptor, Mapping):
        raise CanonicalLifecycleError("thread descriptor must be an object")
    slug_value = descriptor.get("stable_slug")
    if slug_value is None and base is not None:
        slug_value = base["stable_slug"]
    stable_slug = normalize_stable_slug(slug_value)
    id_value = descriptor.get("canonical_thread_id")
    if id_value is None and base is not None:
        id_value = base["canonical_thread_id"]
    canonical_thread_id = (
        stable_canonical_thread_id(stable_slug)
        if id_value is None
        else _normalize_canonical_id(id_value, stable_slug=stable_slug)
    )
    if base is not None:
        if canonical_thread_id != base["canonical_thread_id"]:
            raise CanonicalLifecycleError("canonical_thread_id is immutable")
        if stable_slug != base["stable_slug"]:
            raise CanonicalLifecycleError("stable_slug churn is forbidden")

    def field(name: str, default: object = None) -> object:
        if name in descriptor and descriptor[name] is not None:
            return descriptor[name]
        if base is not None and name in base:
            return base[name]
        return default

    title_ru = _clean_required(field("title_ru"), "title_ru")
    title_en = _clean_required(field("title_en"), "title_en")
    thesis = _clean_required(field("thesis"), "thesis")
    status = _clean_required(field("status", "active"), "status")
    if status not in CANONICAL_THREAD_STATUSES:
        raise CanonicalLifecycleError("unsupported canonical thread status")
    first_seen_at = normalize_canonical_utc(field("first_seen_at"), "first_seen_at")
    last_seen_at = normalize_canonical_utc(field("last_seen_at"), "last_seen_at")
    if _utc_datetime(first_seen_at) > _utc_datetime(last_seen_at):
        raise CanonicalLifecycleError("first_seen_at must not be after last_seen_at")
    evidence_maturity = _clean_required(
        field("evidence_maturity", "single_source"), "evidence_maturity"
    )
    if evidence_maturity not in EVIDENCE_MATURITY_LEVELS:
        raise CanonicalLifecycleError(
            "unsupported evidence_maturity; expected one of "
            + ", ".join(EVIDENCE_MATURITY_LEVELS)
        )
    try:
        operator_interest = float(field("operator_interest", 0.0) or 0.0)
    except (TypeError, ValueError) as exc:
        raise CanonicalLifecycleError("operator_interest must be numeric") from exc
    if not 0.0 <= operator_interest <= 1.0:
        raise CanonicalLifecycleError("operator_interest must be between 0 and 1")
    entities = _normalize_string_list(field("entities", []))
    return {
        "canonical_thread_id": canonical_thread_id,
        "stable_slug": stable_slug,
        "title_ru": title_ru,
        "normalized_title_ru": _normalized_text(title_ru),
        "title_en": title_en,
        "normalized_title_en": _normalized_text(title_en),
        "thesis": thesis,
        "status": status,
        "first_seen_at": first_seen_at,
        "last_seen_at": last_seen_at,
        "evidence_maturity": evidence_maturity,
        "operator_interest": operator_interest,
        "entities": entities,
        "curator_version": curator_version,
        "current_version": int(base["current_version"]) if base is not None else 0,
        "valid_from": str(base.get("valid_from") or "") if base is not None else "",
        "created_at": str(base.get("created_at") or "") if base is not None else "",
    }


def _current_memberships(
    connection: sqlite3.Connection, canonical_thread_id: str
) -> dict[int, dict[str, object]]:
    rows = _rows(
        connection.execute(
            """
            SELECT atom_id, raw_thread_id, relation, valid_from
            FROM canonical_idea_thread_atom_history
            WHERE canonical_thread_id = ? AND valid_to IS NULL
            ORDER BY atom_id
            """,
            (canonical_thread_id,),
        )
    )
    return {
        int(row["atom_id"]): {
            "atom_id": int(row["atom_id"]),
            "raw_thread_id": (
                int(row["raw_thread_id"]) if row.get("raw_thread_id") is not None else None
            ),
            "relation": str(row["relation"]),
            "valid_from": str(row["valid_from"]),
        }
        for row in rows
    }


def _raw_thread_for_atom(
    connection: sqlite3.Connection, atom_id: int
) -> int | None:
    rows = connection.execute(
        """
        SELECT thread_id
        FROM idea_thread_atoms
        WHERE atom_id = ?
        ORDER BY thread_id
        """,
        (atom_id,),
    ).fetchall()
    if len(rows) > 1:
        raise CanonicalLifecycleError(
            f"atom {atom_id} has ambiguous raw idea_thread provenance"
        )
    return int(rows[0][0]) if rows else None


def _normalize_memberships(
    connection: sqlite3.Connection,
    values: object,
) -> dict[int, dict[str, object]]:
    if values is None:
        return {}
    if isinstance(values, (str, bytes, Mapping)) or not isinstance(values, Iterable):
        raise CanonicalLifecycleError("atom_memberships must be a list")
    result: dict[int, dict[str, object]] = {}
    for value in values:
        if isinstance(value, Mapping):
            atom_value = value.get("atom_id")
            raw_value = value.get("raw_thread_id")
            relation = str(value.get("relation") or "supports").strip()
        else:
            atom_value = value
            raw_value = None
            relation = "supports"
        try:
            atom_id = int(atom_value)
        except (TypeError, ValueError) as exc:
            raise CanonicalLifecycleError("atom_id must be a positive integer") from exc
        if atom_id <= 0:
            raise CanonicalLifecycleError("atom_id must be a positive integer")
        if atom_id in result:
            raise CanonicalLifecycleError(f"duplicate atom membership for atom {atom_id}")
        if relation not in ATOM_RELATIONS:
            raise CanonicalLifecycleError(f"unsupported relation for atom {atom_id}")
        if connection.execute(
            "SELECT 1 FROM knowledge_atoms WHERE id = ? LIMIT 1", (atom_id,)
        ).fetchone() is None:
            raise CanonicalLifecycleError(f"knowledge atom {atom_id} does not exist")
        raw_thread_id: int | None
        if raw_value is None:
            raw_thread_id = _raw_thread_for_atom(connection, atom_id)
        else:
            try:
                raw_thread_id = int(raw_value)
            except (TypeError, ValueError) as exc:
                raise CanonicalLifecycleError("raw_thread_id must be a positive integer") from exc
            if raw_thread_id <= 0:
                raise CanonicalLifecycleError("raw_thread_id must be a positive integer")
            if connection.execute(
                "SELECT 1 FROM idea_threads WHERE id = ? LIMIT 1", (raw_thread_id,)
            ).fetchone() is None:
                raise CanonicalLifecycleError(f"raw idea thread {raw_thread_id} does not exist")
            if connection.execute(
                """
                SELECT 1 FROM idea_thread_atoms
                WHERE thread_id = ? AND atom_id = ? LIMIT 1
                """,
                (raw_thread_id, atom_id),
            ).fetchone() is None:
                raise CanonicalLifecycleError(
                    f"raw idea thread {raw_thread_id} does not own atom {atom_id}"
                )
        result[atom_id] = {
            "atom_id": atom_id,
            "raw_thread_id": raw_thread_id,
            "relation": relation,
        }
    return result


def _membership_input(container: Mapping[str, object]) -> tuple[bool, object]:
    if "atom_memberships" in container:
        return True, container.get("atom_memberships")
    if "atom_ids" in container:
        return True, container.get("atom_ids")
    thread = container.get("thread")
    if isinstance(thread, Mapping):
        if "atom_memberships" in thread:
            return True, thread.get("atom_memberships")
        if "atom_ids" in thread:
            return True, thread.get("atom_ids")
    return False, None


def _normalize_aliases(values: object) -> list[dict[str, str]]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [{"alias_type": "manual", "alias_value": values}]
    if isinstance(values, (bytes, Mapping)) or not isinstance(values, Iterable):
        raise CanonicalLifecycleError("aliases must be a list")
    result: dict[tuple[str, str], dict[str, str]] = {}
    for value in values:
        if isinstance(value, str):
            alias_type = "manual"
            alias_value = value
        elif isinstance(value, Mapping):
            alias_type = _clean_required(value.get("alias_type", "manual"), "alias_type")
            alias_value = _clean_required(value.get("alias_value"), "alias_value")
        else:
            raise CanonicalLifecycleError("each alias must be a string or object")
        if alias_type not in ALIAS_TYPES:
            raise CanonicalLifecycleError(f"unsupported alias_type: {alias_type}")
        normalized = _normalized_text(alias_value)
        result.setdefault(
            (alias_type, normalized),
            {
                "alias_type": alias_type,
                "alias_value": alias_value,
                "normalized_alias": normalized,
            },
        )
    return [result[key] for key in sorted(result)]


def _aliases_for_memberships(
    connection: sqlite3.Connection,
    memberships: Mapping[int, Mapping[str, object]],
) -> list[dict[str, str]]:
    raw_ids = sorted(
        {
            int(value["raw_thread_id"])
            for value in memberships.values()
            if value.get("raw_thread_id") is not None
        }
    )
    aliases: list[dict[str, object]] = []
    for raw_thread_id in raw_ids:
        row = connection.execute(
            "SELECT slug FROM idea_threads WHERE id = ? LIMIT 1", (raw_thread_id,)
        ).fetchone()
        aliases.append({"alias_type": "raw_thread_id", "alias_value": str(raw_thread_id)})
        if row and str(row[0] or "").strip():
            slug = str(row[0]).strip()
            aliases.extend(
                [
                    {"alias_type": "raw_thread_slug", "alias_value": slug},
                    {"alias_type": "compatibility_ref", "alias_value": f"idea_thread:{slug}"},
                ]
            )
    return _normalize_aliases(aliases)


def _alias_input(container: Mapping[str, object]) -> object:
    if "aliases" in container:
        return container.get("aliases")
    thread = container.get("thread")
    if isinstance(thread, Mapping) and "aliases" in thread:
        return thread.get("aliases")
    return None


def _merge_alias_lists(*groups: Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    merged: dict[tuple[str, str], dict[str, str]] = {}
    for group in groups:
        for alias in group:
            key = (str(alias["alias_type"]), str(alias["normalized_alias"]))
            merged.setdefault(key, dict(alias))
    return [merged[key] for key in sorted(merged)]


def _assert_event_after_current(snapshot: Mapping[str, object], event_at: str) -> None:
    valid_from = str(snapshot.get("valid_from") or "")
    if valid_from and _utc_datetime(event_at) <= _utc_datetime(valid_from):
        raise CanonicalLifecycleError(
            "event_at must be strictly later than the current version valid_from"
        )


def _check_thread_conflicts(
    connection: sqlite3.Connection,
    snapshots: Sequence[Mapping[str, object]],
    *,
    exempt_thread_ids: Iterable[str] = (),
) -> None:
    exempt = set(exempt_thread_ids)
    seen_slugs: dict[str, str] = {}
    seen_ru: dict[str, str] = {}
    seen_en: dict[str, str] = {}
    for snapshot in snapshots:
        thread_id = str(snapshot["canonical_thread_id"])
        slug = str(snapshot["stable_slug"])
        previous_slug = seen_slugs.setdefault(slug, thread_id)
        if previous_slug != thread_id:
            raise CanonicalLifecycleError(f"duplicate stable_slug in proposal: {slug}")
        existing_slug = connection.execute(
            """
            SELECT canonical_thread_id
            FROM canonical_idea_threads
            WHERE stable_slug = ? AND canonical_thread_id != ?
            LIMIT 1
            """,
            (slug, thread_id),
        ).fetchone()
        if existing_slug and str(existing_slug[0]) not in exempt:
            raise CanonicalLifecycleError(f"stable_slug collision: {slug}")
        if snapshot["status"] != "active":
            continue
        for field, seen, column in (
            ("normalized_title_ru", seen_ru, "normalized_title_ru"),
            ("normalized_title_en", seen_en, "normalized_title_en"),
        ):
            normalized = str(snapshot[field])
            previous = seen.setdefault(normalized, thread_id)
            if previous != thread_id:
                raise CanonicalLifecycleError("duplicate active canonical thread title")
            rows = connection.execute(
                f"""
                SELECT canonical_thread_id
                FROM canonical_idea_threads
                WHERE status = 'active' AND {column} = ? AND canonical_thread_id != ?
                ORDER BY canonical_thread_id
                """,
                (normalized, thread_id),
            ).fetchall()
            owners = {str(row[0]) for row in rows} - exempt
            if owners:
                raise CanonicalLifecycleError("duplicate active canonical thread title")


def _check_membership_owners(
    connection: sqlite3.Connection,
    memberships: Mapping[int, Mapping[str, object]],
    *,
    allowed_owner_ids: Iterable[str],
) -> None:
    allowed = set(allowed_owner_ids)
    if not memberships:
        return
    placeholders = ",".join("?" for _ in memberships)
    rows = connection.execute(
        f"""
        SELECT atom_id, canonical_thread_id
        FROM canonical_idea_thread_atom_history
        WHERE atom_id IN ({placeholders}) AND valid_to IS NULL
        ORDER BY atom_id
        """,
        sorted(memberships),
    ).fetchall()
    for atom_id, owner_id in rows:
        if str(owner_id) not in allowed:
            raise CanonicalLifecycleError(
                f"atom {int(atom_id)} already has active canonical owner {owner_id}"
            )


def _current_aliases(
    connection: sqlite3.Connection, canonical_thread_id: str
) -> list[dict[str, str]]:
    rows = _rows(
        connection.execute(
            """
            SELECT alias_type, alias_value, normalized_alias
            FROM canonical_idea_thread_alias_history
            WHERE canonical_thread_id = ? AND valid_to IS NULL
            ORDER BY alias_type, normalized_alias
            """,
            (canonical_thread_id,),
        )
    )
    return [
        {
            "alias_type": str(row["alias_type"]),
            "alias_value": str(row["alias_value"]),
            "normalized_alias": str(row["normalized_alias"]),
        }
        for row in rows
    ]


def _check_alias_conflicts(
    connection: sqlite3.Connection,
    assignments: Mapping[str, Sequence[Mapping[str, str]]],
    *,
    transferable_owner_ids: Iterable[str] = (),
) -> None:
    transferable = set(transferable_owner_ids)
    proposed: dict[tuple[str, str], str] = {}
    for thread_id, aliases in assignments.items():
        for alias in aliases:
            key = (str(alias["alias_type"]), str(alias["normalized_alias"]))
            prior = proposed.setdefault(key, thread_id)
            if prior != thread_id:
                raise CanonicalLifecycleError(
                    f"alias collision for {alias['alias_type']}:{alias['alias_value']}"
                )
            rows = connection.execute(
                """
                SELECT canonical_thread_id
                FROM canonical_idea_thread_alias_history
                WHERE alias_type = ? AND normalized_alias = ? AND valid_to IS NULL
                ORDER BY canonical_thread_id
                """,
                key,
            ).fetchall()
            owners = {str(row[0]) for row in rows}
            invalid = owners - {thread_id} - transferable
            if invalid:
                raise CanonicalLifecycleError(
                    f"alias collision for {alias['alias_type']}:{alias['alias_value']}"
                )


def _check_lineage_cycles(
    connection: sqlite3.Connection,
    new_edges: Sequence[tuple[str, str, str]],
) -> None:
    graph: dict[str, set[str]] = {}
    for source, target in connection.execute(
        "SELECT from_thread_id, to_thread_id FROM canonical_idea_thread_lineage"
    ).fetchall():
        graph.setdefault(str(source), set()).add(str(target))
    for _relation, source, target in new_edges:
        if source == target:
            raise CanonicalLifecycleError("merge/split lineage cannot point to itself")
        graph.setdefault(source, set()).add(target)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise CanonicalLifecycleError("merge/split lineage cycle detected")
        if node in visited:
            return
        visiting.add(node)
        for child in graph.get(node, set()):
            visit(child)
        visiting.remove(node)
        visited.add(node)

    for node in sorted(graph):
        visit(node)


def _thread_descriptor_from_payload(payload: Mapping[str, object]) -> Mapping[str, object]:
    thread = payload.get("thread")
    if isinstance(thread, Mapping):
        return thread
    return payload


def _normalize_existing_id(value: object, field_name: str) -> str:
    try:
        return _normalize_canonical_id(value)
    except CanonicalLifecycleError as exc:
        raise CanonicalLifecycleError(f"invalid {field_name}: {exc}") from exc


def _prepare_lifecycle_plan(
    connection: sqlite3.Connection,
    *,
    operation: str,
    proposal: Mapping[str, object],
    curator_version: str,
    event_at: str,
) -> dict[str, object]:
    payload = _payload(proposal)
    if operation in AUDIT_ONLY_OPERATIONS:
        refs = payload.get("canonical_thread_ids", payload.get("thread_ids", []))
        if refs is None:
            refs = []
        if isinstance(refs, (str, bytes, Mapping)) or not isinstance(refs, Iterable):
            raise CanonicalLifecycleError("audit-only thread_ids must be a list")
        thread_ids = [_normalize_existing_id(value, "thread_id") for value in refs]
        for thread_id in thread_ids:
            if _current_snapshot(connection, thread_id) is None:
                raise CanonicalLifecycleError(f"canonical thread does not exist: {thread_id}")
        raw_thread_ids: set[int] = set()
        atom_ids: set[int] = set()

        def collect_candidate_refs(value: object) -> None:
            if isinstance(value, Mapping):
                raw_values = value.get("raw_thread_ids")
                if raw_values is None and value.get("raw_thread_id") is not None:
                    raw_values = [value.get("raw_thread_id")]
                atom_values = value.get("atom_ids")
                if atom_values is None and value.get("atom_id") is not None:
                    atom_values = [value.get("atom_id")]
                if raw_values is not None and isinstance(raw_values, (str, int)):
                    raw_values = [raw_values]
                if atom_values is not None and isinstance(atom_values, (str, int)):
                    atom_values = [atom_values]
                if raw_values is not None and (
                    isinstance(raw_values, (bytes, Mapping))
                    or not isinstance(raw_values, Iterable)
                ):
                    raise CanonicalLifecycleError("raw_thread_ids must be a list")
                if atom_values is not None and (
                    isinstance(atom_values, (bytes, Mapping))
                    or not isinstance(atom_values, Iterable)
                ):
                    raise CanonicalLifecycleError("atom_ids must be a list")
                for raw_value in raw_values or []:
                    try:
                        raw_thread_ids.add(int(raw_value))
                    except (TypeError, ValueError) as exc:
                        raise CanonicalLifecycleError("raw_thread_id must be an integer") from exc
                for atom_value in atom_values or []:
                    try:
                        atom_ids.add(int(atom_value))
                    except (TypeError, ValueError) as exc:
                        raise CanonicalLifecycleError("atom_id must be an integer") from exc
                for nested_key in ("source_records", "review_subject", "candidates", "records"):
                    if nested_key in value:
                        collect_candidate_refs(value[nested_key])
            elif isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
                for item in value:
                    collect_candidate_refs(item)

        collect_candidate_refs(payload)
        for raw_thread_id in sorted(raw_thread_ids):
            if raw_thread_id <= 0 or connection.execute(
                "SELECT 1 FROM idea_threads WHERE id = ? LIMIT 1", (raw_thread_id,)
            ).fetchone() is None:
                raise CanonicalLifecycleError(
                    f"raw idea thread does not exist: {raw_thread_id}"
                )
        for atom_id in sorted(atom_ids):
            if atom_id <= 0 or connection.execute(
                "SELECT 1 FROM knowledge_atoms WHERE id = ? LIMIT 1", (atom_id,)
            ).fetchone() is None:
                raise CanonicalLifecycleError(f"knowledge atom does not exist: {atom_id}")
        canonical_count = len(set(thread_ids))
        if operation == "keep_separate" and canonical_count < 2 and len(raw_thread_ids) < 2:
            raise CanonicalLifecycleError(
                "keep_separate requires at least two canonical or raw thread candidates"
            )
        if operation == "keep_together" and canonical_count < 2:
            if len(raw_thread_ids) < 1 or len(atom_ids) < 1:
                raise CanonicalLifecycleError(
                    "keep_together requires canonical threads or one raw thread with atom evidence"
                )
            linked_atoms = {
                int(row[0])
                for raw_thread_id in raw_thread_ids
                for row in connection.execute(
                    "SELECT atom_id FROM idea_thread_atoms WHERE thread_id = ?",
                    (raw_thread_id,),
                ).fetchall()
            }
            if not atom_ids.issubset(linked_atoms):
                raise CanonicalLifecycleError(
                    "keep_together atom evidence must belong to the referenced raw thread"
                )
        if operation == "defer" and not (
            thread_ids
            or raw_thread_ids
            or atom_ids
            or proposal.get("evidence")
            or payload.get("source_records")
        ):
            raise CanonicalLifecycleError("defer requires an auditable review subject or evidence")
        return {
            "operation": operation,
            "audit_only": True,
            "affected_thread_ids": sorted(set(thread_ids)),
            "audit_subject": {
                "raw_thread_ids": sorted(raw_thread_ids),
                "atom_ids": sorted(atom_ids),
            },
            "thread_changes": [],
            "membership_targets": {},
            "alias_assignments": {},
            "alias_transfer_sources": {},
            "lineage_edges": [],
        }

    if operation == "create":
        descriptor = _thread_descriptor_from_payload(payload)
        snapshot = _normalize_thread_descriptor(
            descriptor, base=None, curator_version=curator_version
        )
        if snapshot["status"] not in ACTIVE_CANONICAL_THREAD_STATUSES:
            raise CanonicalLifecycleError("create status must be active or stale")
        if _current_snapshot(connection, str(snapshot["canonical_thread_id"])) is not None:
            raise CanonicalLifecycleError("canonical thread already exists")
        provided, membership_values = _membership_input(payload)
        if not provided:
            raise CanonicalLifecycleError("create requires atom_memberships")
        memberships = _normalize_memberships(connection, membership_values)
        if not memberships:
            raise CanonicalLifecycleError("create requires at least one atom membership")
        thread_id = str(snapshot["canonical_thread_id"])
        _check_membership_owners(connection, memberships, allowed_owner_ids=())
        aliases = _merge_alias_lists(
            _normalize_aliases(_alias_input(payload)),
            _aliases_for_memberships(connection, memberships),
        )
        _check_thread_conflicts(connection, [snapshot])
        _check_alias_conflicts(connection, {thread_id: aliases})
        return {
            "operation": operation,
            "audit_only": False,
            "affected_thread_ids": [thread_id],
            "thread_changes": [(snapshot, operation, True)],
            "membership_targets": {thread_id: memberships},
            "alias_assignments": {thread_id: aliases},
            "alias_transfer_sources": {},
            "lineage_edges": [],
        }

    if operation in {"update", "operator_correction"}:
        descriptor = _thread_descriptor_from_payload(payload)
        id_value = descriptor.get("canonical_thread_id", payload.get("canonical_thread_id"))
        thread_id = _normalize_existing_id(id_value, "canonical_thread_id")
        base = _current_snapshot(connection, thread_id)
        if base is None:
            raise CanonicalLifecycleError(f"canonical thread does not exist: {thread_id}")
        if base["status"] in TERMINAL_CANONICAL_THREAD_STATUSES:
            raise CanonicalLifecycleError("terminal canonical threads cannot be updated")
        snapshot = _normalize_thread_descriptor(
            descriptor, base=base, curator_version=curator_version
        )
        if operation == "update" and snapshot["status"] != base["status"]:
            raise CanonicalLifecycleError("update cannot change lifecycle status")
        if operation == "operator_correction" and snapshot["status"] in {"merged", "split"}:
            raise CanonicalLifecycleError("operator correction cannot manufacture merge/split state")
        _assert_event_after_current(base, event_at)
        current_memberships = _current_memberships(connection, thread_id)
        provided, membership_values = _membership_input(payload)
        memberships = (
            _normalize_memberships(connection, membership_values)
            if provided
            else current_memberships
        )
        missing = set(current_memberships) - set(memberships)
        if missing:
            raise CanonicalLifecycleError(
                "atom loss is forbidden; missing atoms: "
                + ", ".join(str(atom_id) for atom_id in sorted(missing))
            )
        _check_membership_owners(connection, memberships, allowed_owner_ids={thread_id})
        aliases = _merge_alias_lists(
            _normalize_aliases(_alias_input(payload)),
            _aliases_for_memberships(connection, memberships),
        )
        _check_thread_conflicts(connection, [snapshot])
        _check_alias_conflicts(connection, {thread_id: aliases})
        return {
            "operation": operation,
            "audit_only": False,
            "affected_thread_ids": [thread_id],
            "thread_changes": [(snapshot, operation, False)],
            "membership_targets": {thread_id: memberships},
            "alias_assignments": {thread_id: aliases},
            "alias_transfer_sources": {},
            "lineage_edges": [],
        }

    if operation == "stale":
        id_value = payload.get("canonical_thread_id")
        thread = payload.get("thread")
        if id_value is None and isinstance(thread, Mapping):
            id_value = thread.get("canonical_thread_id")
        thread_id = _normalize_existing_id(id_value, "canonical_thread_id")
        base = _current_snapshot(connection, thread_id)
        if base is None:
            raise CanonicalLifecycleError(f"canonical thread does not exist: {thread_id}")
        if base["status"] == "stale":
            return {
                "operation": operation,
                "audit_only": True,
                "affected_thread_ids": [thread_id],
                "thread_changes": [],
                "membership_targets": {},
                "alias_assignments": {},
                "alias_transfer_sources": {},
                "lineage_edges": [],
            }
        if base["status"] != "active":
            raise CanonicalLifecycleError("only an active canonical thread can become stale")
        _assert_event_after_current(base, event_at)
        snapshot = _normalize_thread_descriptor(
            {"canonical_thread_id": thread_id, "status": "stale"},
            base=base,
            curator_version=curator_version,
        )
        return {
            "operation": operation,
            "audit_only": False,
            "affected_thread_ids": [thread_id],
            "thread_changes": [(snapshot, operation, False)],
            "membership_targets": {},
            "alias_assignments": {},
            "alias_transfer_sources": {},
            "lineage_edges": [],
        }

    if operation == "merge":
        source_values = payload.get("source_thread_ids", payload.get("sources"))
        if isinstance(source_values, (str, bytes, Mapping)) or not isinstance(
            source_values, Iterable
        ):
            raise CanonicalLifecycleError("merge source_thread_ids must be a list")
        source_ids = [_normalize_existing_id(value, "source_thread_id") for value in source_values]
        if not source_ids or len(set(source_ids)) != len(source_ids):
            raise CanonicalLifecycleError("merge requires distinct source threads")
        source_snapshots: list[dict[str, object]] = []
        source_memberships: dict[int, dict[str, object]] = {}
        for source_id in source_ids:
            source = _current_snapshot(connection, source_id)
            if source is None:
                raise CanonicalLifecycleError(f"merge source does not exist: {source_id}")
            if source["status"] not in ACTIVE_CANONICAL_THREAD_STATUSES:
                raise CanonicalLifecycleError("merge sources must be active or stale")
            _assert_event_after_current(source, event_at)
            source_snapshots.append(source)
            source_memberships.update(_current_memberships(connection, source_id))
        target_value = payload.get("target")
        if not isinstance(target_value, Mapping):
            raise CanonicalLifecycleError("merge target must be an object")
        target_descriptor = _thread_descriptor_from_payload(target_value)
        target_id_value = target_descriptor.get("canonical_thread_id")
        target_base: dict[str, object] | None = None
        if target_id_value is not None:
            prospective_slug = target_descriptor.get("stable_slug")
            if prospective_slug is not None:
                target_id = _normalize_canonical_id(
                    target_id_value, stable_slug=normalize_stable_slug(prospective_slug)
                )
            else:
                target_id = _normalize_existing_id(target_id_value, "target canonical_thread_id")
            target_base = _current_snapshot(connection, target_id)
        if target_base is not None:
            if target_base["canonical_thread_id"] in source_ids:
                raise CanonicalLifecycleError("merge target cannot also be a source")
            if target_base["status"] not in ACTIVE_CANONICAL_THREAD_STATUSES:
                raise CanonicalLifecycleError("merge target must be active or stale")
            _assert_event_after_current(target_base, event_at)
        elif len(source_ids) < 2:
            raise CanonicalLifecycleError(
                "merge into a new target requires at least two source threads"
            )
        target = _normalize_thread_descriptor(
            target_descriptor, base=target_base, curator_version=curator_version
        )
        target_id = str(target["canonical_thread_id"])
        if target_id in source_ids:
            raise CanonicalLifecycleError("merge target cannot also be a source")
        if target_descriptor.get("status") not in (None, "active"):
            raise CanonicalLifecycleError("merge target status must be active")
        target["status"] = "active"
        target_memberships = (
            _current_memberships(connection, target_id) if target_base is not None else {}
        )
        expected_memberships = {**target_memberships, **source_memberships}
        provided, membership_values = _membership_input(target_value)
        if provided:
            proposed_memberships = _normalize_memberships(connection, membership_values)
            if set(proposed_memberships) != set(expected_memberships):
                raise CanonicalLifecycleError("merge must preserve the exact union of source atoms")
            expected_memberships = proposed_memberships
        _check_membership_owners(
            connection,
            expected_memberships,
            allowed_owner_ids={*source_ids, target_id},
        )
        target_aliases = _merge_alias_lists(
            _normalize_aliases(_alias_input(target_value)),
            _aliases_for_memberships(connection, expected_memberships),
        )
        source_aliases = {
            source_id: _current_aliases(connection, source_id) for source_id in source_ids
        }
        all_target_aliases = _merge_alias_lists(target_aliases, *source_aliases.values())
        terminal_changes: list[tuple[dict[str, object], str, bool]] = []
        for source in source_snapshots:
            terminal = dict(source)
            terminal["status"] = "merged"
            terminal["curator_version"] = curator_version
            terminal_changes.append((terminal, operation, False))
        _check_thread_conflicts(
            connection,
            [target],
            exempt_thread_ids={*source_ids, target_id},
        )
        _check_alias_conflicts(
            connection,
            {target_id: all_target_aliases},
            transferable_owner_ids=source_ids,
        )
        edges = [("merge", source_id, target_id) for source_id in source_ids]
        _check_lineage_cycles(connection, edges)
        membership_targets = {source_id: {} for source_id in source_ids}
        membership_targets[target_id] = expected_memberships
        return {
            "operation": operation,
            "audit_only": False,
            "affected_thread_ids": sorted([*source_ids, target_id]),
            "thread_changes": [
                *terminal_changes,
                (target, operation, target_base is None),
            ],
            "membership_targets": membership_targets,
            "alias_assignments": {target_id: all_target_aliases},
            "alias_transfer_sources": {target_id: source_ids},
            "lineage_edges": edges,
        }

    if operation == "split":
        source_value = payload.get("source_thread_id", payload.get("source"))
        source_id = _normalize_existing_id(source_value, "source_thread_id")
        source = _current_snapshot(connection, source_id)
        if source is None:
            raise CanonicalLifecycleError(f"split source does not exist: {source_id}")
        if source["status"] not in ACTIVE_CANONICAL_THREAD_STATUSES:
            raise CanonicalLifecycleError("split source must be active or stale")
        _assert_event_after_current(source, event_at)
        output_values = payload.get("outputs")
        if isinstance(output_values, (str, bytes, Mapping)) or not isinstance(
            output_values, Iterable
        ):
            raise CanonicalLifecycleError("split outputs must be a list")
        outputs = list(output_values)
        if len(outputs) < 2 or not all(isinstance(output, Mapping) for output in outputs):
            raise CanonicalLifecycleError("split requires at least two output objects")
        source_memberships = _current_memberships(connection, source_id)
        if not source_memberships:
            raise CanonicalLifecycleError("split source has no atoms")
        assigned_source_atoms: set[int] = set()
        output_snapshots: list[dict[str, object]] = []
        membership_targets: dict[str, dict[int, dict[str, object]]] = {source_id: {}}
        alias_assignments: dict[str, list[dict[str, str]]] = {}
        output_ids: set[str] = set()
        for output_value in outputs:
            assert isinstance(output_value, Mapping)
            descriptor = _thread_descriptor_from_payload(output_value)
            id_value = descriptor.get("canonical_thread_id")
            base: dict[str, object] | None = None
            if id_value is not None:
                prospective_slug = descriptor.get("stable_slug")
                if prospective_slug is not None:
                    output_id = _normalize_canonical_id(
                        id_value, stable_slug=normalize_stable_slug(prospective_slug)
                    )
                else:
                    output_id = _normalize_existing_id(id_value, "output canonical_thread_id")
                base = _current_snapshot(connection, output_id)
            if base is not None:
                if base["status"] not in ACTIVE_CANONICAL_THREAD_STATUSES:
                    raise CanonicalLifecycleError("existing split output must be active or stale")
                _assert_event_after_current(base, event_at)
            snapshot = _normalize_thread_descriptor(
                descriptor, base=base, curator_version=curator_version
            )
            output_id = str(snapshot["canonical_thread_id"])
            if output_id == source_id or output_id in output_ids:
                raise CanonicalLifecycleError("split outputs must be distinct from source and each other")
            output_ids.add(output_id)
            if descriptor.get("status") not in (None, "active"):
                raise CanonicalLifecycleError("split output status must be active")
            snapshot["status"] = "active"
            provided, values = _membership_input(output_value)
            if not provided:
                raise CanonicalLifecycleError("each split output requires atom_memberships")
            assigned = _normalize_memberships(connection, values)
            if not assigned:
                raise CanonicalLifecycleError("each split output requires at least one source atom")
            foreign_atoms = set(assigned) - set(source_memberships)
            duplicates = set(assigned) & assigned_source_atoms
            if foreign_atoms:
                raise CanonicalLifecycleError("split outputs may only assign source atoms")
            if duplicates:
                raise CanonicalLifecycleError("split creates duplicate atom ownership")
            assigned_source_atoms.update(assigned)
            existing = _current_memberships(connection, output_id) if base is not None else {}
            desired = {**existing, **assigned}
            membership_targets[output_id] = desired
            # A split source may contain atoms from one broad raw thread.  Its
            # raw slug/ref must remain on the terminal source rather than being
            # duplicated across children; children resolve by atom history and
            # may receive only explicit, non-colliding aliases.
            aliases = _normalize_aliases(_alias_input(output_value))
            alias_assignments[output_id] = aliases
            output_snapshots.append(snapshot)
        missing = set(source_memberships) - assigned_source_atoms
        if missing:
            raise CanonicalLifecycleError(
                "split would lose atoms: " + ", ".join(str(value) for value in sorted(missing))
            )
        for output_id, desired in membership_targets.items():
            if output_id != source_id:
                _check_membership_owners(
                    connection,
                    desired,
                    allowed_owner_ids={source_id, output_id},
                )
        _check_thread_conflicts(
            connection,
            output_snapshots,
            exempt_thread_ids={source_id, *output_ids},
        )
        _check_alias_conflicts(connection, alias_assignments)
        edges = [("split", source_id, output_id) for output_id in sorted(output_ids)]
        _check_lineage_cycles(connection, edges)
        terminal = dict(source)
        terminal["status"] = "split"
        terminal["curator_version"] = curator_version
        return {
            "operation": operation,
            "audit_only": False,
            "affected_thread_ids": sorted({source_id, *output_ids}),
            "thread_changes": [
                (terminal, operation, False),
                *[
                    (
                        snapshot,
                        operation,
                        _current_snapshot(connection, str(snapshot["canonical_thread_id"])) is None,
                    )
                    for snapshot in output_snapshots
                ],
            ],
            "membership_targets": membership_targets,
            "alias_assignments": alias_assignments,
            "alias_transfer_sources": {},
            "lineage_edges": edges,
        }

    raise CanonicalLifecycleError(f"unsupported lifecycle operation: {operation}")


def validate_canonical_lifecycle(
    connection: sqlite3.Connection,
    proposal: Mapping[str, object],
    *,
    operation: object | None = None,
    event_at: object | None = None,
    curator_version: object | None = None,
) -> tuple[str, ...]:
    """Return deterministic validation errors without mutating any table."""

    try:
        if not isinstance(proposal, Mapping):
            raise CanonicalLifecycleError("proposal must be an object")
        clean_operation = _normalize_operation(
            _metadata_value(proposal, operation, "operation")
        )
        clean_curator_version = _clean_required(
            _metadata_value(proposal, curator_version, "curator_version"),
            "curator_version",
        )
        timestamp_value = event_at
        if timestamp_value is None:
            timestamp_value = proposal.get("event_at")
        if timestamp_value is None:
            timestamp_value = _payload(proposal).get("event_at")
        timestamp = normalize_canonical_utc(timestamp_value or _now_utc(), "event_at")
        _prepare_lifecycle_plan(
            connection,
            operation=clean_operation,
            proposal=proposal,
            curator_version=clean_curator_version,
            event_at=timestamp,
        )
    except CanonicalLifecycleError as exc:
        return exc.errors
    except sqlite3.Error as exc:
        return (f"database validation error: {exc}",)
    return ()


def _persist_thread_version(
    connection: sqlite3.Connection,
    *,
    snapshot: Mapping[str, object],
    operation: str,
    is_new: bool,
    decision_id: str,
    event_at: str,
) -> None:
    thread_id = str(snapshot["canonical_thread_id"])
    normalized_title_ru = _normalized_text(snapshot["title_ru"])
    normalized_title_en = _normalized_text(snapshot["title_en"])
    entities_json = _canonical_json(_normalize_string_list(snapshot.get("entities", [])))
    if is_new:
        if _current_thread_row(connection, thread_id) is not None:
            raise CanonicalLifecycleError(f"canonical thread already exists: {thread_id}")
        version = 1
        created_at = event_at
        connection.execute(
            """
            INSERT INTO canonical_idea_threads (
                canonical_thread_id,
                stable_slug,
                title_ru,
                normalized_title_ru,
                title_en,
                normalized_title_en,
                thesis,
                status,
                first_seen_at,
                last_seen_at,
                evidence_maturity,
                operator_interest,
                entities_json,
                curator_version,
                current_version,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                thread_id,
                snapshot["stable_slug"],
                snapshot["title_ru"],
                normalized_title_ru,
                snapshot["title_en"],
                normalized_title_en,
                snapshot["thesis"],
                snapshot["status"],
                snapshot["first_seen_at"],
                snapshot["last_seen_at"],
                snapshot["evidence_maturity"],
                snapshot["operator_interest"],
                entities_json,
                snapshot["curator_version"],
                version,
                created_at,
                event_at,
            ),
        )
    else:
        current = _current_thread_row(connection, thread_id)
        if current is None:
            raise CanonicalLifecycleError(f"canonical thread does not exist: {thread_id}")
        if str(current["stable_slug"]) != str(snapshot["stable_slug"]):
            raise CanonicalLifecycleError("stable_slug churn is forbidden")
        current_valid_from = normalize_canonical_utc(current["valid_from"], "valid_from")
        if _utc_datetime(event_at) <= _utc_datetime(current_valid_from):
            raise CanonicalLifecycleError(
                "event_at must be strictly later than current valid_from"
            )
        changed = connection.execute(
            """
            UPDATE canonical_idea_thread_versions
            SET valid_to = ?
            WHERE canonical_thread_id = ? AND valid_to IS NULL
            """,
            (event_at, thread_id),
        ).rowcount
        if changed != 1:
            raise CanonicalLifecycleError("canonical thread has ambiguous current version")
        version = int(current["current_version"]) + 1
        created_at = str(current["created_at"])
        connection.execute(
            """
            UPDATE canonical_idea_threads
            SET
                title_ru = ?,
                normalized_title_ru = ?,
                title_en = ?,
                normalized_title_en = ?,
                thesis = ?,
                status = ?,
                first_seen_at = ?,
                last_seen_at = ?,
                evidence_maturity = ?,
                operator_interest = ?,
                entities_json = ?,
                curator_version = ?,
                current_version = ?,
                updated_at = ?
            WHERE canonical_thread_id = ?
            """,
            (
                snapshot["title_ru"],
                normalized_title_ru,
                snapshot["title_en"],
                normalized_title_en,
                snapshot["thesis"],
                snapshot["status"],
                snapshot["first_seen_at"],
                snapshot["last_seen_at"],
                snapshot["evidence_maturity"],
                snapshot["operator_interest"],
                entities_json,
                snapshot["curator_version"],
                version,
                event_at,
                thread_id,
            ),
        )
    connection.execute(
        """
        INSERT INTO canonical_idea_thread_versions (
            canonical_thread_id,
            version,
            stable_slug,
            title_ru,
            normalized_title_ru,
            title_en,
            normalized_title_en,
            thesis,
            status,
            first_seen_at,
            last_seen_at,
            evidence_maturity,
            operator_interest,
            entities_json,
            curator_version,
            operation,
            decision_id,
            valid_from,
            valid_to,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
        """,
        (
            thread_id,
            version,
            snapshot["stable_slug"],
            snapshot["title_ru"],
            normalized_title_ru,
            snapshot["title_en"],
            normalized_title_en,
            snapshot["thesis"],
            snapshot["status"],
            snapshot["first_seen_at"],
            snapshot["last_seen_at"],
            snapshot["evidence_maturity"],
            snapshot["operator_interest"],
            entities_json,
            snapshot["curator_version"],
            operation,
            decision_id,
            event_at,
            event_at,
        ),
    )


def _persist_membership_targets(
    connection: sqlite3.Connection,
    *,
    targets: Mapping[str, Mapping[int, Mapping[str, object]]],
    decision_id: str,
    event_at: str,
) -> None:
    if not targets:
        return
    desired_owner: dict[int, str] = {}
    for thread_id, memberships in targets.items():
        for atom_id in memberships:
            prior = desired_owner.setdefault(int(atom_id), thread_id)
            if prior != thread_id:
                raise CanonicalLifecycleError(
                    f"ambiguous desired canonical ownership for atom {atom_id}"
                )
    target_ids = sorted(targets)
    placeholders = ",".join("?" for _ in target_ids)
    current_rows = _rows(
        connection.execute(
            f"""
            SELECT id, canonical_thread_id, atom_id, raw_thread_id, relation, valid_from
            FROM canonical_idea_thread_atom_history
            WHERE canonical_thread_id IN ({placeholders}) AND valid_to IS NULL
            ORDER BY atom_id, canonical_thread_id
            """,
            target_ids,
        )
    )
    retained: set[tuple[str, int]] = set()
    for row in current_rows:
        thread_id = str(row["canonical_thread_id"])
        atom_id = int(row["atom_id"])
        desired = targets.get(thread_id, {}).get(atom_id)
        same = bool(
            desired is not None
            and desired.get("raw_thread_id") == row.get("raw_thread_id")
            and str(desired.get("relation") or "supports") == str(row["relation"])
        )
        if same:
            retained.add((thread_id, atom_id))
            continue
        valid_from = normalize_canonical_utc(row["valid_from"], "membership valid_from")
        if _utc_datetime(event_at) <= _utc_datetime(valid_from):
            raise CanonicalLifecycleError(
                "event_at must be later than membership valid_from"
            )
        connection.execute(
            """
            UPDATE canonical_idea_thread_atom_history
            SET valid_to = ?, retired_decision_id = ?
            WHERE id = ? AND valid_to IS NULL
            """,
            (event_at, decision_id, int(row["id"])),
        )
    for thread_id in target_ids:
        for atom_id, desired in sorted(targets[thread_id].items()):
            if (thread_id, int(atom_id)) in retained:
                continue
            connection.execute(
                """
                INSERT INTO canonical_idea_thread_atom_history (
                    canonical_thread_id,
                    atom_id,
                    raw_thread_id,
                    relation,
                    valid_from,
                    valid_to,
                    assigned_decision_id,
                    retired_decision_id,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, NULL, ?, NULL, ?)
                """,
                (
                    thread_id,
                    int(atom_id),
                    desired.get("raw_thread_id"),
                    str(desired.get("relation") or "supports"),
                    event_at,
                    decision_id,
                    event_at,
                ),
            )


def _persist_alias_changes(
    connection: sqlite3.Connection,
    *,
    assignments: Mapping[str, Sequence[Mapping[str, str]]],
    transfer_sources: Mapping[str, Sequence[str]],
    decision_id: str,
    event_at: str,
) -> None:
    transferring = {
        source_id
        for source_ids in transfer_sources.values()
        for source_id in source_ids
    }
    if transferring:
        placeholders = ",".join("?" for _ in transferring)
        rows = _rows(
            connection.execute(
                f"""
                SELECT id, valid_from
                FROM canonical_idea_thread_alias_history
                WHERE canonical_thread_id IN ({placeholders}) AND valid_to IS NULL
                ORDER BY id
                """,
                sorted(transferring),
            )
        )
        for row in rows:
            valid_from = normalize_canonical_utc(row["valid_from"], "alias valid_from")
            if _utc_datetime(event_at) <= _utc_datetime(valid_from):
                raise CanonicalLifecycleError("event_at must be later than alias valid_from")
            connection.execute(
                """
                UPDATE canonical_idea_thread_alias_history
                SET valid_to = ?, retired_decision_id = ?
                WHERE id = ? AND valid_to IS NULL
                """,
                (event_at, decision_id, int(row["id"])),
            )
    for thread_id in sorted(assignments):
        existing = {
            (str(row[0]), str(row[1]))
            for row in connection.execute(
                """
                SELECT alias_type, normalized_alias
                FROM canonical_idea_thread_alias_history
                WHERE canonical_thread_id = ? AND valid_to IS NULL
                """,
                (thread_id,),
            ).fetchall()
        }
        for alias in assignments[thread_id]:
            key = (str(alias["alias_type"]), str(alias["normalized_alias"]))
            if key in existing:
                continue
            connection.execute(
                """
                INSERT INTO canonical_idea_thread_alias_history (
                    canonical_thread_id,
                    alias_type,
                    alias_value,
                    normalized_alias,
                    valid_from,
                    valid_to,
                    assigned_decision_id,
                    retired_decision_id,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, NULL, ?, NULL, ?)
                """,
                (
                    thread_id,
                    alias["alias_type"],
                    alias["alias_value"],
                    alias["normalized_alias"],
                    event_at,
                    decision_id,
                    event_at,
                ),
            )
            existing.add(key)


def _execute_plan(
    connection: sqlite3.Connection,
    *,
    plan: Mapping[str, object],
    decision_id: str,
    reason: str,
    event_at: str,
) -> None:
    for snapshot, operation, is_new in plan["thread_changes"]:  # type: ignore[index]
        _persist_thread_version(
            connection,
            snapshot=snapshot,
            operation=str(operation),
            is_new=bool(is_new),
            decision_id=decision_id,
            event_at=event_at,
        )
    _persist_membership_targets(
        connection,
        targets=plan["membership_targets"],  # type: ignore[arg-type]
        decision_id=decision_id,
        event_at=event_at,
    )
    _persist_alias_changes(
        connection,
        assignments=plan["alias_assignments"],  # type: ignore[arg-type]
        transfer_sources=plan["alias_transfer_sources"],  # type: ignore[arg-type]
        decision_id=decision_id,
        event_at=event_at,
    )
    for relation_type, source_id, target_id in plan["lineage_edges"]:  # type: ignore[index]
        connection.execute(
            """
            INSERT INTO canonical_idea_thread_lineage (
                relation_type,
                from_thread_id,
                to_thread_id,
                decision_id,
                event_at,
                reason,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                relation_type,
                source_id,
                target_id,
                decision_id,
                event_at,
                reason,
                event_at,
            ),
        )


def apply_canonical_lifecycle(
    connection: sqlite3.Connection,
    *,
    proposal: Mapping[str, object],
    run_id: object | None = None,
    operation: object | None = None,
    model: object | None = None,
    model_version: object | None = None,
    curator_version: object | None = None,
    reason: object | None = None,
    event_at: object | None = None,
    actor: object | None = None,
    proposal_id: object | None = None,
    strict_validator: Callable[
        [sqlite3.Connection, Mapping[str, object]], Iterable[str]
    ]
    | None = None,
) -> dict[str, object]:
    """Validate and atomically apply one incremental lifecycle proposal.

    The proposal audit row is durable even when deterministic validation rejects
    the operation.  All canonical projections/history/lineage changes and the
    final applied decision transition commit in one ``BEGIN IMMEDIATE``
    transaction.  An optional strict validator reads its source evidence under
    that same writer lock.  Reapplying the same run/proposal identity is a no-op.
    """

    decision_id: str | None = None
    recorded: dict[str, object] | None = None
    try:
        # Match the historical public API's treatment of caller-side pending
        # writes, then acquire the only writer slot before reading any state
        # that controls validation or canonical mutation.
        connection.commit()
        connection.execute("BEGIN IMMEDIATE")
        recorded = _record_curator_proposal(
            connection,
            proposal=proposal,
            run_id=run_id,
            operation=operation,
            model=model,
            model_version=model_version,
            curator_version=curator_version,
            reason=reason,
            actor=actor,
            commit=False,
        )
        decision_id = str(recorded["decision_id"])
        if (
            proposal_id is not None
            and _clean_required(proposal_id, "proposal_id") != decision_id
        ):
            raise CanonicalLifecycleError(
                "proposal_id does not match deterministic proposal identity"
            )
        if recorded["decision_status"] == "applied":
            result = dict(recorded.get("result") or {})
            connection.commit()
            affected = [
                thread
                for thread_id in result.get("affected_thread_ids", [])
                if (thread := fetch_canonical_thread(connection, thread_id)) is not None
            ]
            return {
                "decision": recorded,
                "affected_thread_ids": list(result.get("affected_thread_ids", [])),
                "canonical_threads": affected,
                "idempotent": True,
            }
        if recorded["decision_status"] == "rejected":
            raise CanonicalLifecycleError(
                recorded.get("validation_errors") or "proposal was rejected"
            )

        clean_operation = str(recorded["operation"])
        clean_curator_version = str(recorded["curator_version"])
        clean_reason = str(recorded["reason"])
        clean_actor = str(recorded["actor"])
        if clean_operation == "operator_correction" and not clean_actor.casefold().startswith(
            "operator"
        ):
            raise CanonicalLifecycleError(
                "operator_correction requires an operator actor"
            )
        timestamp_value = event_at
        if timestamp_value is None:
            timestamp_value = proposal.get("event_at")
        if timestamp_value is None:
            timestamp_value = _payload(proposal).get("event_at")
        timestamp = normalize_canonical_utc(
            timestamp_value or recorded["proposed_at"], "event_at"
        )
        if strict_validator is not None:
            strict_errors = tuple(
                str(error).strip()
                for error in strict_validator(connection, proposal)
                if str(error).strip()
            )
            if strict_errors:
                raise CanonicalLifecycleError(strict_errors)
        plan = _prepare_lifecycle_plan(
            connection,
            operation=clean_operation,
            proposal=proposal,
            curator_version=clean_curator_version,
            event_at=timestamp,
        )
        connection.execute(
            """
            UPDATE canonical_idea_thread_curator_decisions
            SET validation_status = 'passed', validation_errors_json = '[]',
                validated_at = ?, updated_at = ?
            WHERE decision_id = ? AND decision_status = 'proposed'
            """,
            (timestamp, timestamp, decision_id),
        )
        _execute_plan(
            connection,
            plan=plan,
            decision_id=decision_id,
            reason=clean_reason,
            event_at=timestamp,
        )
        result = {
            "affected_thread_ids": list(plan["affected_thread_ids"]),
            "event_at": timestamp,
            "operation": clean_operation,
            "audit_only": bool(plan["audit_only"]),
        }
        if plan.get("audit_subject"):
            result["audit_subject"] = plan["audit_subject"]
        connection.execute(
            """
            UPDATE canonical_idea_thread_curator_decisions
            SET decision_status = 'applied', applied_at = ?, result_json = ?, updated_at = ?
            WHERE decision_id = ? AND decision_status = 'proposed'
            """,
            (timestamp, _canonical_json(result), timestamp, decision_id),
        )
        connection.commit()
    except (CanonicalLifecycleError, sqlite3.Error) as exc:
        connection.rollback()
        errors = (
            exc.errors
            if isinstance(exc, CanonicalLifecycleError)
            else (f"database apply error: {exc}",)
        )
        if decision_id is None:
            raise CanonicalLifecycleError(errors) from exc
        rejected_at = _now_utc()
        # The decision insert was part of the rolled-back transaction for a new
        # proposal.  Recreate it without an intermediate commit, then durably
        # append the rejection while leaving canonical and raw state untouched.
        _record_curator_proposal(
            connection,
            proposal=proposal,
            run_id=run_id,
            operation=operation,
            model=model,
            model_version=model_version,
            curator_version=curator_version,
            reason=reason,
            proposed_at=recorded.get("proposed_at") if recorded else None,
            actor=actor,
            commit=False,
        )
        connection.execute(
            """
            UPDATE canonical_idea_thread_curator_decisions
            SET validation_status = 'rejected', validation_errors_json = ?,
                decision_status = 'rejected', validated_at = ?, updated_at = ?
            WHERE decision_id = ? AND decision_status = 'proposed'
            """,
            (_canonical_json(errors), rejected_at, rejected_at, decision_id),
        )
        connection.commit()
        raise CanonicalLifecycleError(errors) from exc
    except Exception:
        connection.rollback()
        raise

    decision = fetch_curator_decision(connection, decision_id)
    if decision is None:
        raise RuntimeError("applied curator decision could not be read back")
    affected_threads = [
        thread
        for thread_id in result["affected_thread_ids"]
        if (thread := fetch_canonical_thread(connection, thread_id)) is not None
    ]
    return {
        "decision": decision,
        "affected_thread_ids": list(result["affected_thread_ids"]),
        "canonical_threads": affected_threads,
        "idempotent": False,
    }

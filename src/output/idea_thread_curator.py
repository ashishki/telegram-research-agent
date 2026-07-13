"""Deterministic, bounded proposal boundary for canonical Idea Thread curation.

Raw ``idea_threads`` remain audit evidence.  This module reads their stored atom
memberships, finds review candidates from non-entity evidence, and packages a
curator decision as an inert proposal.  Canonical writes are deliberately kept
behind the deterministic persistence validator in
:mod:`db.canonical_idea_threads`.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping, Sequence

from output.reaction_personalization import ThreadResolution


GROUPING_CANDIDATE_SCHEMA_VERSION = "idea_thread_grouping_candidate.v1"
CURATOR_PROPOSAL_SCHEMA_VERSION = "canonical_idea_thread_proposal.v1"
CURATOR_CONTRACT_VERSION = "irx4_curator.v1"

MAX_CANDIDATES = 12
MAX_RAW_THREADS_SCANNED = 200
MAX_RAW_THREADS_PER_CANDIDATE = 6
MAX_ATOMS_PER_RAW_THREAD = 8
MAX_ATOM_EVIDENCE_PER_CANDIDATE = 24
MAX_SOURCE_REFS_PER_CANDIDATE = 24
MAX_REASON_CHARS = 2_000

_OPERATIONS = frozenset(
    {
        "create",
        "update",
        "merge",
        "split",
        "stale",
        "operator_correction",
        "keep_separate",
        "keep_together",
        "defer",
    }
)
_MUTATING_OPERATIONS = frozenset(
    {"create", "update", "merge", "split", "stale", "operator_correction"}
)
_AUDIT_ONLY_OPERATIONS = frozenset({"keep_separate", "keep_together", "defer"})
_TOKEN_RE = re.compile(r"[^\W_][^\W_+.-]{1,}", re.UNICODE)
_VERSION_RE = re.compile(r"^(?:v(?:er(?:sion)?)?)?\d+(?:[._-]\d+)*[a-z]?$", re.I)
_NON_SEMANTIC_TERMS = frozenset(
    {
        "about",
        "after",
        "agent",
        "agents",
        "also",
        "before",
        "being",
        "build",
        "from",
        "have",
        "into",
        "model",
        "models",
        "more",
        "new",
        "that",
        "their",
        "this",
        "tool",
        "tools",
        "using",
        "with",
        "для",
        "как",
        "модель",
        "модели",
        "новая",
        "новый",
        "при",
        "это",
    }
)


class CuratorContractError(ValueError):
    """Raised when a bounded curator object violates the IRX-4 contract."""


def _clean_required(value: object, field_name: str, *, limit: int = 500) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        raise CuratorContractError(f"{field_name} is required")
    if len(text) > limit:
        raise CuratorContractError(f"{field_name} exceeds {limit} characters")
    return text


def _bounded(value: object, *, default: int, hard_limit: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise CuratorContractError("bounds must be integers") from exc
    if parsed < 1:
        raise CuratorContractError("bounds must be positive")
    return min(parsed, hard_limit)


def _json_list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _strings(value: object) -> list[str]:
    result: list[str] = []
    for item in _json_list(value) if isinstance(value, str) else (value or []):
        text = " ".join(str(item or "").split())
        if text and text not in result:
            result.append(text)
    return result


def _ints(value: object) -> list[int]:
    result: list[int] = []
    for item in _json_list(value) if isinstance(value, str) else (value or []):
        try:
            parsed = int(item)
        except (TypeError, ValueError):
            continue
        if parsed > 0 and parsed not in result:
            result.append(parsed)
    return result


def _rows(cursor: sqlite3.Cursor) -> list[dict[str, object]]:
    columns = [str(item[0]) for item in cursor.description or ()]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _tokens(value: object) -> list[str]:
    return [match.casefold() for match in _TOKEN_RE.findall(str(value or ""))]


def _excluded_tokens(atom: Mapping[str, object]) -> set[str]:
    excluded: set[str] = set()
    for field in ("entities", "tools", "models"):
        for value in atom.get(field) or []:
            excluded.update(_tokens(value))
    return excluded


def _semantic_tokens(value: object, *, excluded: set[str]) -> tuple[str, ...]:
    result: list[str] = []
    for token in _tokens(value):
        if (
            token in excluded
            or token in _NON_SEMANTIC_TERMS
            or _VERSION_RE.fullmatch(token)
            or len(token) < 3
        ):
            continue
        normalized = token.strip(".+-")
        if normalized and normalized not in result:
            result.append(normalized)
    return tuple(result)


def _practice_signals(atom: Mapping[str, object]) -> set[str]:
    excluded = _excluded_tokens(atom)
    signals: set[str] = set()
    for practice in atom.get("practices") or []:
        tokens = _semantic_tokens(practice, excluded=excluded)
        if tokens:
            signals.add("-".join(tokens[:8]))
    return signals


def _idea_terms(atom: Mapping[str, object]) -> set[str]:
    excluded = _excluded_tokens(atom)
    text = " ".join(
        str(atom.get(field) or "") for field in ("claim", "summary", "evidence_quote")
    )
    return set(_semantic_tokens(text, excluded=excluded))


def _slug(value: object) -> str:
    raw = " ".join(str(value or "").split()).casefold()
    ascii_tokens = [
        re.sub(r"[^a-z0-9]+", "", token)
        for token in _semantic_tokens(raw, excluded=set())
        if token.isascii()
    ]
    text = "-".join(token for token in ascii_tokens if token)
    text = re.sub(r"-+", "-", text).strip("-")[:80].strip("-")
    if text:
        return text
    return "idea-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _digest(value: object, *, length: int = 24) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:length]


def _stable_canonical_id(stable_slug: str) -> str:
    return "ct_" + hashlib.sha256(stable_slug.encode("utf-8")).hexdigest()[:24]


def _candidate_snapshot_fingerprint(
    raw_records: Sequence[Mapping[str, object]],
    atom_evidence: Sequence[Mapping[str, object]],
    source_provenance: Sequence[Mapping[str, object]],
) -> str:
    """Hash the bounded stored evidence, not merely its mutable identities."""

    payload = {
        "raw_memberships": sorted(
            (
                {
                    "raw_thread_id": int(item["raw_thread_id"]),
                    "atom_ids": sorted(_ints(item.get("atom_ids"))),
                    "membership_count": int(item.get("membership_count") or 0),
                }
                for item in raw_records
            ),
            key=lambda item: int(item["raw_thread_id"]),
        ),
        "atom_evidence": sorted(
            (dict(item) for item in atom_evidence),
            key=lambda item: (int(item["atom_id"]), int(item["raw_thread_id"])),
        ),
        "source_provenance": list(source_provenance),
    }
    return _digest(payload, length=64)


def _load_raw_thread_evidence(
    connection: sqlite3.Connection,
    *,
    raw_thread_limit: int,
    atom_limit: int,
) -> list[dict[str, object]]:
    thread_rows = _rows(
        connection.execute(
            """
            SELECT id, slug, title, summary, status, first_seen_at, last_seen_at,
                   source_channels_json, key_entities_json
            FROM idea_threads
            ORDER BY id ASC
            LIMIT ?
            """,
            (raw_thread_limit,),
        )
    )
    if not thread_rows:
        return []
    thread_ids = [int(row["id"]) for row in thread_rows]
    placeholders = ",".join("?" for _ in thread_ids)
    evidence_rows = _rows(
        connection.execute(
            f"""
            WITH ranked_memberships AS (
                SELECT ita.thread_id, ita.atom_id, ita.relation,
                       ROW_NUMBER() OVER (
                           PARTITION BY ita.thread_id ORDER BY ita.atom_id ASC
                       ) AS member_rank,
                       COUNT(*) OVER (PARTITION BY ita.thread_id) AS member_count
                FROM idea_thread_atoms AS ita
                WHERE ita.thread_id IN ({placeholders})
            )
            SELECT ranked.thread_id, ranked.relation, ranked.member_count,
                   atom.id AS atom_id, atom.atom_type, atom.claim, atom.summary,
                   atom.evidence_quote, atom.source_post_ids_json,
                   atom.source_urls_json, atom.entities_json, atom.tools_json,
                   atom.models_json, atom.practices_json, atom.first_seen_at,
                   atom.last_seen_at
            FROM ranked_memberships AS ranked
            JOIN knowledge_atoms AS atom ON atom.id = ranked.atom_id
            WHERE ranked.member_rank <= ?
            ORDER BY ranked.thread_id ASC, atom.id ASC
            """,
            (*thread_ids, atom_limit),
        )
    )
    atoms_by_thread: dict[int, list[dict[str, object]]] = {
        thread_id: [] for thread_id in thread_ids
    }
    membership_counts = {thread_id: 0 for thread_id in thread_ids}
    for row in evidence_rows:
        thread_id = int(row["thread_id"])
        membership_counts[thread_id] = int(row.get("member_count") or 0)
        atoms_by_thread[thread_id].append(
            {
                "atom_id": int(row["atom_id"]),
                "relation": str(row.get("relation") or "supports"),
                "atom_type": str(row.get("atom_type") or ""),
                "claim": str(row.get("claim") or ""),
                "summary": str(row.get("summary") or ""),
                "evidence_quote": str(row.get("evidence_quote") or ""),
                "source_post_ids": _ints(row.get("source_post_ids_json")),
                "source_urls": _strings(row.get("source_urls_json")),
                "entities": _strings(row.get("entities_json")),
                "tools": _strings(row.get("tools_json")),
                "models": _strings(row.get("models_json")),
                "practices": _strings(row.get("practices_json")),
                "first_seen_at": str(row.get("first_seen_at") or ""),
                "last_seen_at": str(row.get("last_seen_at") or ""),
            }
        )
    snapshots: list[dict[str, object]] = []
    for row in thread_rows:
        thread_id = int(row["id"])
        atoms = atoms_by_thread[thread_id]
        practices: set[str] = set()
        idea_terms: set[str] = set()
        entities: set[str] = set(_strings(row.get("key_entities_json")))
        models: set[str] = set()
        for atom in atoms:
            practices.update(_practice_signals(atom))
            idea_terms.update(_idea_terms(atom))
            entities.update(str(value) for value in atom["entities"])
            models.update(str(value) for value in atom["models"])
        snapshots.append(
            {
                "raw_thread_id": thread_id,
                "slug": str(row.get("slug") or ""),
                "title": str(row.get("title") or ""),
                "summary": str(row.get("summary") or ""),
                "status": str(row.get("status") or "active"),
                "first_seen_at": str(row.get("first_seen_at") or ""),
                "last_seen_at": str(row.get("last_seen_at") or ""),
                "source_channels": _strings(row.get("source_channels_json")),
                "entities": sorted(entities, key=str.casefold),
                "models": sorted(models, key=str.casefold),
                "practice_signals": sorted(practices),
                "idea_terms": sorted(idea_terms),
                "atoms": atoms,
                "membership_count": membership_counts[thread_id],
                "evidence_complete": membership_counts[thread_id] == len(atoms),
            }
        )
    return snapshots


def _pair_signals(
    left: Mapping[str, object], right: Mapping[str, object]
) -> dict[str, list[str]] | None:
    practices = sorted(
        set(left.get("practice_signals") or []).intersection(
            right.get("practice_signals") or []
        )
    )
    idea_terms = sorted(
        set(left.get("idea_terms") or []).intersection(right.get("idea_terms") or [])
    )
    # Entity/tool/model overlap is audit context only.  A grouping edge requires
    # an independently stored practice or at least two shared idea terms.
    if not practices and len(idea_terms) < 2:
        return None
    entities = sorted(
        set(str(value).casefold() for value in left.get("entities") or []).intersection(
            str(value).casefold() for value in right.get("entities") or []
        )
    )
    models = sorted(
        set(str(value) for value in left.get("models") or []).union(
            str(value) for value in right.get("models") or []
        ),
        key=str.casefold,
    )
    return {
        "shared_practices": practices,
        "shared_idea_terms": idea_terms[:12],
        "shared_entities": entities[:12],
        "model_aliases": models[:12],
    }


def _model_family_terms(atom: Mapping[str, object]) -> set[str]:
    """Normalize only structured model fields; exact aliases stay in evidence."""

    terms: set[str] = set()
    for model in atom.get("models") or []:
        for token in _tokens(model):
            if not _VERSION_RE.fullmatch(token):
                terms.add(token)
    return terms


def _atom_components(atoms: Sequence[Mapping[str, object]]) -> list[list[int]]:
    """Find disjoint non-entity evidence islands inside one raw thread.

    A structured model-family overlap can reinforce one shared idea term, but it
    never creates a connection by itself.  Consequently a numeric/model release
    difference alone cannot become a split reason, while a broad vendor bucket
    containing unrelated practices remains reviewable.
    """

    by_id = {int(atom["atom_id"]): atom for atom in atoms}
    ids = sorted(by_id)
    adjacency = {atom_id: set() for atom_id in ids}
    for index, left_id in enumerate(ids):
        left = by_id[left_id]
        left_practices = _practice_signals(left)
        left_terms = _idea_terms(left)
        left_family = _model_family_terms(left)
        for right_id in ids[index + 1 :]:
            right = by_id[right_id]
            shared_practices = left_practices.intersection(_practice_signals(right))
            right_terms = _idea_terms(right)
            shared_terms = left_terms.intersection(right_terms)
            shared_family = left_family.intersection(_model_family_terms(right))
            if shared_practices or len(shared_terms) >= 2 or (
                shared_family
                and (shared_terms or (not left_terms and not right_terms))
            ):
                adjacency[left_id].add(right_id)
                adjacency[right_id].add(left_id)
    components: list[list[int]] = []
    seen: set[int] = set()
    for start in ids:
        if start in seen:
            continue
        pending = [start]
        component: list[int] = []
        while pending:
            current = pending.pop(0)
            if current in seen:
                continue
            seen.add(current)
            component.append(current)
            pending.extend(sorted(adjacency[current] - seen))
        components.append(sorted(component))
    return components


def _split_review_candidate(
    snapshot: Mapping[str, object],
    *,
    run_id: str,
    source_limit: int,
) -> dict[str, object] | None:
    atoms = [item for item in snapshot.get("atoms") or [] if isinstance(item, Mapping)]
    if len(atoms) < 2:
        return None
    clusters = _atom_components(atoms)
    if len(clusters) < 2:
        return None
    atoms_by_id = {int(atom["atom_id"]): atom for atom in atoms}
    source_posts = sorted(
        {int(value) for atom in atoms for value in atom.get("source_post_ids") or []}
    )
    source_urls = sorted(
        {str(value) for atom in atoms for value in atom.get("source_urls") or []}
    )
    source_refs = ([{"source_post_id": value} for value in source_posts] + [
        {"source_url": value} for value in source_urls
    ])
    source_overflow = len(source_refs) > source_limit
    source_refs = source_refs[:source_limit]
    raw_id = int(snapshot["raw_thread_id"])
    raw_record = {
        "raw_thread_id": raw_id,
        "compatibility_ref": f"idea_thread:{snapshot['slug']}",
        "slug": snapshot["slug"],
        "title": snapshot["title"],
        "summary": snapshot["summary"],
        "status": snapshot["status"],
        "first_seen_at": snapshot["first_seen_at"],
        "last_seen_at": snapshot["last_seen_at"],
        "atom_ids": sorted(atoms_by_id),
        "membership_count": int(snapshot["membership_count"]),
        "source_channels": list(snapshot["source_channels"]),
        "entities": list(snapshot["entities"]),
        "models": list(snapshot["models"]),
    }
    output_clusters: list[dict[str, object]] = []
    for atom_ids in clusters:
        cluster_practices = sorted(
            {
                signal
                for atom_id in atom_ids
                for signal in _practice_signals(atoms_by_id[atom_id])
            }
        )
        cluster_terms = sorted(
            {
                term
                for atom_id in atom_ids
                for term in _idea_terms(atoms_by_id[atom_id])
            }
        )
        seed = cluster_practices[0] if cluster_practices else "-".join(cluster_terms[:4])
        stable_slug = _slug(seed)
        output_clusters.append(
            {
                "atom_ids": atom_ids,
                "shared_practices": cluster_practices[:12],
                "idea_terms": cluster_terms[:12],
                "suggested_identity": {
                    "canonical_thread_id": _stable_canonical_id(stable_slug),
                    "stable_slug": stable_slug,
                },
            }
        )
    identity_basis = {
        "kind": "split_review",
        "raw_thread_ref": raw_record["compatibility_ref"],
    }
    provenance_complete = bool(snapshot["evidence_complete"]) and not source_overflow
    evidence = [{**dict(atom), "raw_thread_id": raw_id} for atom in atoms]
    evidence.sort(key=lambda item: int(item["atom_id"]))
    return {
        "schema_version": GROUPING_CANDIDATE_SCHEMA_VERSION,
        "contract_version": CURATOR_CONTRACT_VERSION,
        "candidate_id": f"itgc_{_digest(identity_basis)}",
        "snapshot_fingerprint": _candidate_snapshot_fingerprint(
            [raw_record], evidence, source_refs
        ),
        "run_id": run_id,
        "kind": "split_review",
        "suggested_identity": {
            "canonical_thread_id": _stable_canonical_id(_slug(snapshot["slug"])),
            "stable_slug": _slug(snapshot["slug"]),
        },
        "suggested_output_identities": output_clusters,
        "raw_threads": [raw_record],
        "atom_evidence": evidence,
        "source_provenance": source_refs,
        "signals": {
            "disjoint_non_entity_clusters": output_clusters,
            "entity_overlap_is_split_evidence": False,
            "model_version_difference_is_split_evidence": False,
        },
        "allowed_operations": ["split", "keep_together", "defer"],
        "provenance_complete": provenance_complete,
        "bounds": {
            "max_raw_threads": 1,
            "max_atom_evidence": MAX_ATOMS_PER_RAW_THREAD,
            "max_source_refs": source_limit,
            "raw_thread_count": 1,
            "atom_evidence_count": len(evidence),
            "source_ref_count": len(source_refs),
            "evidence_truncated": not provenance_complete,
        },
    }


def _connected_components(
    snapshots: Sequence[Mapping[str, object]],
) -> list[tuple[list[int], dict[tuple[int, int], dict[str, list[str]]]]]:
    by_id = {int(item["raw_thread_id"]): item for item in snapshots}
    edges: dict[tuple[int, int], dict[str, list[str]]] = {}
    ids = sorted(by_id)
    for index, left_id in enumerate(ids):
        for right_id in ids[index + 1 :]:
            signals = _pair_signals(by_id[left_id], by_id[right_id])
            if signals is not None:
                edges[(left_id, right_id)] = signals
    adjacency = {thread_id: set() for thread_id in ids}
    for left_id, right_id in edges:
        adjacency[left_id].add(right_id)
        adjacency[right_id].add(left_id)
    components: list[tuple[list[int], dict[tuple[int, int], dict[str, list[str]]]]] = []
    seen: set[int] = set()
    for start in ids:
        if start in seen or not adjacency[start]:
            continue
        pending = [start]
        component: list[int] = []
        while pending:
            current = pending.pop(0)
            if current in seen:
                continue
            seen.add(current)
            component.append(current)
            pending.extend(sorted(adjacency[current] - seen))
        component.sort()
        component_edges = {
            pair: signals
            for pair, signals in edges.items()
            if pair[0] in component and pair[1] in component
        }
        components.append((component, component_edges))
    return components


def generate_grouping_candidates(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    max_candidates: int = MAX_CANDIDATES,
    max_raw_threads: int = MAX_RAW_THREADS_SCANNED,
    max_threads_per_candidate: int = MAX_RAW_THREADS_PER_CANDIDATE,
    max_atoms_per_thread: int = MAX_ATOMS_PER_RAW_THREAD,
    max_sources_per_candidate: int = MAX_SOURCE_REFS_PER_CANDIDATE,
) -> list[dict[str, object]]:
    """Return stable grouping-review candidates from stored raw evidence.

    The result is deterministic for the same database snapshot and is bounded
    even if callers request larger limits.  Model/tool/entity values are never
    used to create an edge, so vendor overlap alone cannot become a merge.
    """

    clean_run_id = _clean_required(run_id, "run_id", limit=300)
    candidate_limit = _bounded(max_candidates, default=MAX_CANDIDATES, hard_limit=MAX_CANDIDATES)
    scan_limit = _bounded(
        max_raw_threads, default=MAX_RAW_THREADS_SCANNED, hard_limit=MAX_RAW_THREADS_SCANNED
    )
    thread_limit = _bounded(
        max_threads_per_candidate,
        default=MAX_RAW_THREADS_PER_CANDIDATE,
        hard_limit=MAX_RAW_THREADS_PER_CANDIDATE,
    )
    atom_limit = _bounded(
        max_atoms_per_thread,
        default=MAX_ATOMS_PER_RAW_THREAD,
        hard_limit=MAX_ATOMS_PER_RAW_THREAD,
    )
    source_limit = _bounded(
        max_sources_per_candidate,
        default=MAX_SOURCE_REFS_PER_CANDIDATE,
        hard_limit=MAX_SOURCE_REFS_PER_CANDIDATE,
    )
    snapshots = _load_raw_thread_evidence(
        connection, raw_thread_limit=scan_limit, atom_limit=atom_limit
    )
    by_id = {int(item["raw_thread_id"]): item for item in snapshots}
    candidates: list[dict[str, object]] = []
    for snapshot in snapshots:
        split_candidate = _split_review_candidate(
            snapshot, run_id=clean_run_id, source_limit=source_limit
        )
        if split_candidate is not None:
            candidates.append(split_candidate)
    for component, edge_signals in _connected_components(snapshots):
        for offset in range(0, len(component), thread_limit):
            selected_ids = component[offset : offset + thread_limit]
            if len(selected_ids) < 2:
                continue
            selected = [by_id[thread_id] for thread_id in selected_ids]
            selected_edges = {
                pair: signals
                for pair, signals in edge_signals.items()
                if pair[0] in selected_ids and pair[1] in selected_ids
            }
            if not selected_edges:
                continue
            shared_practices = sorted(
                {value for item in selected_edges.values() for value in item["shared_practices"]}
            )
            shared_idea_terms = sorted(
                {value for item in selected_edges.values() for value in item["shared_idea_terms"]}
            )
            seed = shared_practices[0] if shared_practices else "-".join(shared_idea_terms[:4])
            stable_slug = _slug(seed)
            canonical_thread_id = _stable_canonical_id(stable_slug)
            evidence = [
                {**atom, "raw_thread_id": int(thread["raw_thread_id"])}
                for thread in selected
                for atom in thread["atoms"]
            ]
            evidence.sort(key=lambda item: (int(item["atom_id"]), int(item["raw_thread_id"])))
            all_source_posts = sorted(
                {int(value) for atom in evidence for value in atom["source_post_ids"]}
            )
            all_source_urls = sorted(
                {str(value) for atom in evidence for value in atom["source_urls"]}
            )
            source_overflow = len(all_source_posts) + len(all_source_urls) > source_limit
            source_refs: list[dict[str, object]] = []
            for post_id in all_source_posts:
                source_refs.append({"source_post_id": post_id})
            for url in all_source_urls:
                source_refs.append({"source_url": url})
            source_refs = source_refs[:source_limit]
            provenance_complete = (
                all(bool(item["evidence_complete"]) for item in selected)
                and len(evidence) <= MAX_ATOM_EVIDENCE_PER_CANDIDATE
                and not source_overflow
            )
            if len(evidence) > MAX_ATOM_EVIDENCE_PER_CANDIDATE:
                evidence = evidence[:MAX_ATOM_EVIDENCE_PER_CANDIDATE]
            raw_records = [
                {
                    "raw_thread_id": int(item["raw_thread_id"]),
                    "compatibility_ref": f"idea_thread:{item['slug']}",
                    "slug": item["slug"],
                    "title": item["title"],
                    "summary": item["summary"],
                    "status": item["status"],
                    "first_seen_at": item["first_seen_at"],
                    "last_seen_at": item["last_seen_at"],
                    "atom_ids": [int(atom["atom_id"]) for atom in item["atoms"]],
                    "membership_count": int(item["membership_count"]),
                    "source_channels": list(item["source_channels"]),
                    "entities": list(item["entities"]),
                    "models": list(item["models"]),
                }
                for item in selected
            ]
            identity_basis = {
                "kind": "grouping_review",
                "raw_thread_refs": [record["compatibility_ref"] for record in raw_records],
            }
            candidate = {
                "schema_version": GROUPING_CANDIDATE_SCHEMA_VERSION,
                "contract_version": CURATOR_CONTRACT_VERSION,
                "candidate_id": f"itgc_{_digest(identity_basis)}",
                "snapshot_fingerprint": _candidate_snapshot_fingerprint(
                    raw_records, evidence, source_refs
                ),
                "run_id": clean_run_id,
                "kind": "grouping_review",
                "suggested_identity": {
                    "canonical_thread_id": canonical_thread_id,
                    "stable_slug": stable_slug,
                },
                "raw_threads": raw_records,
                "atom_evidence": evidence,
                "source_provenance": source_refs,
                "signals": {
                    "shared_non_entity_practices": shared_practices[:12],
                    "shared_non_entity_idea_terms": shared_idea_terms[:12],
                    "shared_entities_audit_only": sorted(
                        {
                            value
                            for item in selected_edges.values()
                            for value in item["shared_entities"]
                        }
                    )[:12],
                    "model_aliases_audit_only": sorted(
                        {
                            value
                            for item in selected_edges.values()
                            for value in item["model_aliases"]
                        },
                        key=str.casefold,
                    )[:12],
                    "entity_overlap_only": False,
                    "model_version_difference_is_split_evidence": False,
                },
                "allowed_operations": ["create", "update", "merge", "keep_separate", "defer"],
                "provenance_complete": provenance_complete,
                "bounds": {
                    "max_raw_threads": thread_limit,
                    "max_atom_evidence": MAX_ATOM_EVIDENCE_PER_CANDIDATE,
                    "max_source_refs": source_limit,
                    "raw_thread_count": len(raw_records),
                    "atom_evidence_count": len(evidence),
                    "source_ref_count": len(source_refs),
                    "evidence_truncated": not provenance_complete,
                },
            }
            candidates.append(candidate)
    candidates.sort(key=lambda item: (str(item["candidate_id"]), str(item["snapshot_fingerprint"])))
    return candidates[:candidate_limit]


build_grouping_candidates = generate_grouping_candidates


def _candidate_atom_memberships(candidate: Mapping[str, object]) -> list[dict[str, object]]:
    memberships: list[dict[str, object]] = []
    for raw_atom in candidate.get("atom_evidence") or []:
        if not isinstance(raw_atom, Mapping):
            raise CuratorContractError("candidate atom evidence must contain objects")
        memberships.append(
            {
                "atom_id": int(raw_atom["atom_id"]),
                "raw_thread_id": int(raw_atom["raw_thread_id"]),
                "relation": str(raw_atom.get("relation") or "supports"),
            }
        )
    return sorted(memberships, key=lambda item: (int(item["atom_id"]), int(item["raw_thread_id"])))


def _candidate_aliases(candidate: Mapping[str, object]) -> list[dict[str, str]]:
    aliases: list[dict[str, str]] = []
    for raw_thread in candidate.get("raw_threads") or []:
        if not isinstance(raw_thread, Mapping):
            continue
        raw_id = int(raw_thread["raw_thread_id"])
        raw_slug = str(raw_thread.get("slug") or "").strip()
        compatibility_ref = str(raw_thread.get("compatibility_ref") or "").strip()
        aliases.append(
            {"alias_type": "raw_thread_id", "alias_value": str(raw_id)}
        )
        if raw_slug:
            aliases.append(
                {"alias_type": "raw_thread_slug", "alias_value": raw_slug}
            )
        if compatibility_ref:
            aliases.append(
                {"alias_type": "compatibility_ref", "alias_value": compatibility_ref}
            )
    return aliases


def _proposal_evidence(candidate: Mapping[str, object]) -> dict[str, object]:
    sources = [
        item
        for item in candidate.get("raw_threads") or []
        if isinstance(item, Mapping)
    ]
    atoms = [
        item
        for item in candidate.get("atom_evidence") or []
        if isinstance(item, Mapping)
    ]
    signals = candidate.get("signals")
    return {
        "grouping_candidate_id": candidate["candidate_id"],
        "candidate_snapshot_fingerprint": candidate["snapshot_fingerprint"],
        "raw_thread_ids": sorted(int(item["raw_thread_id"]) for item in sources),
        "atom_ids": sorted({int(item["atom_id"]) for item in atoms}),
        "source_provenance": list(candidate.get("source_provenance") or []),
        "deterministic_signals": dict(signals) if isinstance(signals, Mapping) else {},
    }


def _build_audit_only_proposal(
    candidate: Mapping[str, object],
    strong_model_output: Mapping[str, object],
    *,
    run_id: str,
    operation: str,
    curator: str,
    curator_version: str,
    model: str,
    model_version: str,
    reason: str,
) -> dict[str, object]:
    forbidden = {
        "thread",
        "target",
        "atom_memberships",
        "aliases",
        "outputs",
        "source_thread_id",
        "source_thread_ids",
        "canonical_thread_id",
    }
    supplied_mutations = sorted(forbidden.intersection(strong_model_output))
    if supplied_mutations:
        raise CuratorContractError(
            "audit-only proposal cannot contain mutation payload: "
            + ", ".join(supplied_mutations)
        )
    if operation != "defer" and not bool(candidate.get("provenance_complete")):
        raise CuratorContractError(
            "truncated evidence may only produce a defer audit proposal"
        )
    sources = [
        dict(item)
        for item in candidate.get("raw_threads") or []
        if isinstance(item, Mapping)
    ]
    proposal: dict[str, object] = {
        "schema_version": CURATOR_PROPOSAL_SCHEMA_VERSION,
        "contract_version": CURATOR_CONTRACT_VERSION,
        "run_id": run_id,
        "status": "proposed",
        "applied": False,
        "requires_deterministic_validation": True,
        "mutation_policy": "audit_only_no_canonical_mutation",
        "operation": operation,
        "curator": _clean_required(curator, "curator", limit=100),
        "curator_version": _clean_required(curator_version, "curator_version", limit=100),
        "model": _clean_required(model, "model", limit=200),
        "model_version": _clean_required(model_version, "model_version", limit=200),
        "reason": _clean_required(reason, "reason", limit=MAX_REASON_CHARS),
        "evidence": _proposal_evidence(candidate),
        "suggested_identity": dict(candidate.get("suggested_identity") or {}),
        "review_subject": {
            "kind": str(candidate.get("kind") or "grouping_review"),
            "candidate_id": str(candidate["candidate_id"]),
            "raw_thread_ids": [int(item["raw_thread_id"]) for item in sources],
            "compatibility_refs": [
                str(item.get("compatibility_ref") or "") for item in sources
            ],
            "atom_ids": sorted(
                {
                    int(atom["atom_id"])
                    for atom in candidate.get("atom_evidence") or []
                    if isinstance(atom, Mapping)
                }
            ),
        },
        "source_records": sources,
    }
    proposal["proposal_id"] = f"ctp_{_digest(proposal, length=32)}"
    return proposal


def _build_split_proposal(
    candidate: Mapping[str, object],
    strong_model_output: Mapping[str, object],
    *,
    run_id: str,
    curator: str,
    curator_version: str,
    model: str,
    model_version: str,
    reason: str,
) -> dict[str, object]:
    source_thread_id = _clean_required(
        strong_model_output.get("source_thread_id"), "source_thread_id", limit=100
    )
    raw_outputs = strong_model_output.get("outputs")
    suggestions = candidate.get("suggested_output_identities")
    if not isinstance(raw_outputs, list) or not all(
        isinstance(item, Mapping) for item in raw_outputs
    ):
        raise CuratorContractError("split proposal outputs must be a list of objects")
    if not isinstance(suggestions, list) or len(raw_outputs) != len(suggestions):
        raise CuratorContractError("split proposal must preserve every suggested output")
    suggestion_by_atoms: dict[tuple[int, ...], Mapping[str, object]] = {}
    for suggestion in suggestions:
        if not isinstance(suggestion, Mapping):
            raise CuratorContractError("split suggested outputs must be objects")
        suggestion_by_atoms[tuple(sorted(_ints(suggestion.get("atom_ids"))))] = suggestion
    expected_memberships = _candidate_atom_memberships(candidate)
    expected_pairs = sorted(
        (
            int(item["atom_id"]),
            int(item["raw_thread_id"]),
            str(item.get("relation") or "supports"),
        )
        for item in expected_memberships
    )
    observed_pairs: list[tuple[int, int, str]] = []
    outputs: list[dict[str, object]] = []
    used_clusters: set[tuple[int, ...]] = set()
    for raw_output in raw_outputs:
        raw_memberships = raw_output.get("atom_memberships")
        if not isinstance(raw_memberships, list) or not all(
            isinstance(item, Mapping) for item in raw_memberships
        ):
            raise CuratorContractError("each split output requires atom_memberships")
        memberships = [
            {
                "atom_id": int(item["atom_id"]),
                "raw_thread_id": int(item["raw_thread_id"]),
                "relation": str(item.get("relation") or "supports"),
            }
            for item in raw_memberships
        ]
        atom_key = tuple(sorted(int(item["atom_id"]) for item in memberships))
        suggestion = suggestion_by_atoms.get(atom_key)
        if suggestion is None or atom_key in used_clusters:
            raise CuratorContractError(
                "split output atom assignment must match one deterministic evidence cluster"
            )
        used_clusters.add(atom_key)
        suggested_identity = suggestion.get("suggested_identity")
        if not isinstance(suggested_identity, Mapping):
            raise CuratorContractError("split output suggested_identity is required")
        raw_thread = raw_output.get("thread") or {}
        if not isinstance(raw_thread, Mapping):
            raise CuratorContractError("split output thread must be an object")
        thread = dict(raw_thread)
        stable_slug = _clean_required(
            suggested_identity.get("stable_slug"), "stable_slug", limit=100
        )
        canonical_id = _clean_required(
            suggested_identity.get("canonical_thread_id"),
            "canonical_thread_id",
            limit=100,
        )
        if str(thread.get("stable_slug") or stable_slug).strip() != stable_slug or str(
            thread.get("canonical_thread_id") or canonical_id
        ).strip() != canonical_id:
            raise CuratorContractError(
                "strong model cannot replace a split output's stable suggested identity"
            )
        thread["stable_slug"] = stable_slug
        thread["canonical_thread_id"] = canonical_id
        raw_aliases = raw_output.get("aliases", [])
        if not isinstance(raw_aliases, list) or not all(
            isinstance(item, Mapping) for item in raw_aliases
        ):
            raise CuratorContractError("split output aliases must be a list of objects")
        aliases = [
            {
                "alias_type": _clean_required(item.get("alias_type"), "alias_type", limit=80),
                "alias_value": _clean_required(item.get("alias_value"), "alias_value", limit=300),
            }
            for item in raw_aliases
        ]
        if any(item["alias_type"] == "model_version" for item in aliases):
            raise CuratorContractError(
                "model/entity names are audit evidence, not global curator aliases"
            )
        observed_pairs.extend(
            (
                int(item["atom_id"]),
                int(item["raw_thread_id"]),
                str(item.get("relation") or "supports"),
            )
            for item in memberships
        )
        outputs.append(
            {
                "thread": thread,
                "atom_memberships": memberships,
                "aliases": aliases,
            }
        )
    if sorted(observed_pairs) != expected_pairs:
        raise CuratorContractError(
            "split proposal must assign every atom exactly once with raw provenance"
        )
    sources = [
        dict(item)
        for item in candidate.get("raw_threads") or []
        if isinstance(item, Mapping)
    ]
    proposal: dict[str, object] = {
        "schema_version": CURATOR_PROPOSAL_SCHEMA_VERSION,
        "contract_version": CURATOR_CONTRACT_VERSION,
        "run_id": run_id,
        "status": "proposed",
        "applied": False,
        "requires_deterministic_validation": True,
        "mutation_policy": "proposal_only",
        "operation": "split",
        "curator": _clean_required(curator, "curator", limit=100),
        "curator_version": _clean_required(curator_version, "curator_version", limit=100),
        "model": _clean_required(model, "model", limit=200),
        "model_version": _clean_required(model_version, "model_version", limit=200),
        "reason": _clean_required(reason, "reason", limit=MAX_REASON_CHARS),
        "evidence": {
            "grouping_candidate_id": candidate["candidate_id"],
            "candidate_snapshot_fingerprint": candidate["snapshot_fingerprint"],
            "raw_thread_ids": [int(item["raw_thread_id"]) for item in sources],
            "atom_ids": sorted(
                {atom_id for atom_id, _raw_id, _relation in expected_pairs}
            ),
            "source_provenance": list(candidate.get("source_provenance") or []),
            "disjoint_non_entity_clusters": list(suggestions),
        },
        "suggested_identity": dict(candidate.get("suggested_identity") or {}),
        "target": {"source_thread_id": source_thread_id},
        "source_records": sources,
        "source_thread_id": source_thread_id,
        "outputs": outputs,
    }
    proposal["proposal_id"] = f"ctp_{_digest(proposal, length=32)}"
    return proposal


def build_curator_proposal(
    candidate: Mapping[str, object],
    strong_model_output: Mapping[str, object],
    *,
    run_id: str,
    operation: str,
    curator: str,
    curator_version: str,
    model: str,
    model_version: str,
    reason: str,
) -> dict[str, object]:
    """Normalize one strong-model result into an inert proposal object.

    This function has no connection argument and performs no write.  Even a
    well-formed return value must pass :func:`validate_curator_proposal` and an
    explicit :func:`apply_curator_proposal` call before canonical state changes.
    """

    if (
        not isinstance(candidate, Mapping)
        or candidate.get("schema_version") != GROUPING_CANDIDATE_SCHEMA_VERSION
    ):
        raise CuratorContractError("a versioned grouping candidate is required")
    clean_run_id = _clean_required(run_id, "run_id", limit=300)
    if str(candidate.get("run_id") or "") != clean_run_id:
        raise CuratorContractError("proposal run_id must match its grouping candidate")
    clean_operation = _clean_required(operation, "operation", limit=50)
    if clean_operation not in _OPERATIONS:
        raise CuratorContractError(f"unsupported operation: {clean_operation}")
    allowed_operations = {
        str(value) for value in candidate.get("allowed_operations") or []
    }
    if clean_operation not in allowed_operations:
        raise CuratorContractError(
            f"operation {clean_operation!r} is not allowed for this candidate"
        )
    if not isinstance(strong_model_output, Mapping):
        raise CuratorContractError("strong_model_output must be a proposal object")
    if clean_operation in _AUDIT_ONLY_OPERATIONS:
        return _build_audit_only_proposal(
            candidate,
            strong_model_output,
            run_id=clean_run_id,
            operation=clean_operation,
            curator=curator,
            curator_version=curator_version,
            model=model,
            model_version=model_version,
            reason=reason,
        )
    if not bool(candidate.get("provenance_complete")) and clean_operation in _MUTATING_OPERATIONS:
        raise CuratorContractError("truncated candidate evidence cannot propose mutation")

    if clean_operation == "split":
        return _build_split_proposal(
            candidate,
            strong_model_output,
            run_id=clean_run_id,
            curator=curator,
            curator_version=curator_version,
            model=model,
            model_version=model_version,
            reason=reason,
        )

    suggested = candidate.get("suggested_identity")
    if not isinstance(suggested, Mapping):
        raise CuratorContractError("candidate suggested_identity is required")
    stable_slug = _clean_required(suggested.get("stable_slug"), "stable_slug", limit=100)
    canonical_id = _clean_required(
        suggested.get("canonical_thread_id"), "canonical_thread_id", limit=100
    )
    raw_target = strong_model_output.get("thread") or strong_model_output.get("target") or {}
    if not isinstance(raw_target, Mapping):
        raise CuratorContractError("proposal target must be an object")
    if clean_operation == "merge":
        reserved_nested = sorted({"thread", "atom_ids"}.intersection(raw_target))
        if reserved_nested:
            raise CuratorContractError(
                "merge target contains reserved nested fields: "
                + ", ".join(reserved_nested)
            )
    supplied_slug = str(raw_target.get("stable_slug") or stable_slug).strip()
    supplied_id = str(raw_target.get("canonical_thread_id") or canonical_id).strip()
    if supplied_slug != stable_slug or supplied_id != canonical_id:
        raise CuratorContractError("strong model cannot replace the stable suggested identity")
    target = dict(raw_target)
    target["stable_slug"] = stable_slug
    target["canonical_thread_id"] = canonical_id

    default_memberships = _candidate_atom_memberships(candidate)
    top_level_memberships = strong_model_output.get("atom_memberships")
    nested_memberships = raw_target.get("atom_memberships")
    if (
        top_level_memberships is not None
        and nested_memberships is not None
        and top_level_memberships != nested_memberships
    ):
        raise CuratorContractError(
            "target atom_memberships conflict with top-level atom_memberships"
        )
    raw_memberships = (
        top_level_memberships
        if top_level_memberships is not None
        else nested_memberships
        if nested_memberships is not None
        else default_memberships
    )
    if not isinstance(raw_memberships, list) or not all(
        isinstance(item, Mapping) for item in raw_memberships
    ):
        raise CuratorContractError("atom_memberships must be a list of objects")
    memberships = [
        {
            "atom_id": int(item["atom_id"]),
            "raw_thread_id": int(item["raw_thread_id"]),
            "relation": str(item.get("relation") or "supports"),
        }
        for item in raw_memberships
    ]
    if sorted(
        (item["atom_id"], item["raw_thread_id"], item["relation"])
        for item in memberships
    ) != sorted(
        (item["atom_id"], item["raw_thread_id"], item["relation"])
        for item in default_memberships
    ):
        raise CuratorContractError("strong model proposal must preserve exact candidate atom provenance")

    top_level_aliases = strong_model_output.get("aliases")
    nested_aliases = raw_target.get("aliases")
    if (
        top_level_aliases is not None
        and nested_aliases is not None
        and top_level_aliases != nested_aliases
    ):
        raise CuratorContractError("target aliases conflict with top-level aliases")
    aliases = (
        top_level_aliases
        if top_level_aliases is not None
        else nested_aliases
        if nested_aliases is not None
        else _candidate_aliases(candidate)
    )
    if not isinstance(aliases, list) or not all(isinstance(item, Mapping) for item in aliases):
        raise CuratorContractError("aliases must be a list of objects")
    normalized_aliases = [
        {
            "alias_type": _clean_required(item.get("alias_type"), "alias_type", limit=80),
            "alias_value": _clean_required(item.get("alias_value"), "alias_value", limit=300),
        }
        for item in aliases
    ]
    if any(item["alias_type"] == "model_version" for item in normalized_aliases):
        raise CuratorContractError(
            "model/entity names are audit evidence, not global curator aliases"
        )
    if clean_operation == "merge":
        # The persistence API consumes these fields from the nested merge
        # target.  Keep that payload identical to the normalized, candidate-
        # bound top-level projection so an untrusted model cannot bypass it.
        target["atom_memberships"] = memberships
        target["aliases"] = normalized_aliases
    sources = [dict(item) for item in candidate.get("raw_threads") or [] if isinstance(item, Mapping)]
    evidence = {
        "grouping_candidate_id": candidate["candidate_id"],
        "candidate_snapshot_fingerprint": candidate["snapshot_fingerprint"],
        "raw_thread_ids": [int(item["raw_thread_id"]) for item in sources],
        "atom_ids": sorted({int(item["atom_id"]) for item in memberships}),
        "source_provenance": list(candidate.get("source_provenance") or []),
        "shared_non_entity_practices": list(
            (candidate.get("signals") or {}).get("shared_non_entity_practices") or []
        ),
        "shared_non_entity_idea_terms": list(
            (candidate.get("signals") or {}).get("shared_non_entity_idea_terms") or []
        ),
    }
    proposal: dict[str, object] = {
        "schema_version": CURATOR_PROPOSAL_SCHEMA_VERSION,
        "contract_version": CURATOR_CONTRACT_VERSION,
        "run_id": clean_run_id,
        "status": "proposed",
        "applied": False,
        "requires_deterministic_validation": True,
        "mutation_policy": "proposal_only",
        "operation": clean_operation,
        "curator": _clean_required(curator, "curator", limit=100),
        "curator_version": _clean_required(curator_version, "curator_version", limit=100),
        "model": _clean_required(model, "model", limit=200),
        "model_version": _clean_required(model_version, "model_version", limit=200),
        "reason": _clean_required(reason, "reason", limit=MAX_REASON_CHARS),
        "evidence": evidence,
        "suggested_identity": dict(suggested),
        "target": target,
        "source_records": sources,
        "thread": target,
        "atom_memberships": memberships,
        "aliases": normalized_aliases,
    }
    # Existing-target merge/split/stale fields remain operation payload, but
    # cannot bypass the deterministic DB validator.
    for key in ("source_thread_ids", "source_thread_id", "outputs", "canonical_thread_id"):
        if key in strong_model_output:
            proposal[key] = strong_model_output[key]
    proposal["proposal_id"] = f"ctp_{_digest(proposal, length=32)}"
    return proposal


accept_strong_model_proposal = build_curator_proposal


def _proposal_metadata(proposal: Mapping[str, object]) -> dict[str, str]:
    if proposal.get("schema_version") != CURATOR_PROPOSAL_SCHEMA_VERSION:
        raise CuratorContractError("unsupported curator proposal schema_version")
    return {
        key: _clean_required(proposal.get(key), key, limit=MAX_REASON_CHARS if key == "reason" else 300)
        for key in ("run_id", "operation", "model", "model_version", "curator_version", "reason")
    }


def _canonical_owner_binding_errors(
    connection: sqlite3.Connection,
    proposal: Mapping[str, object],
    *,
    expected_atom_ids: set[int],
) -> tuple[str, ...]:
    """Bind update/merge targets to the candidate's complete raw atom set."""

    operation = str(proposal.get("operation") or "")
    if operation not in {"update", "merge"} or not expected_atom_ids:
        return ()

    target = proposal.get("target") or proposal.get("thread")
    target_id = (
        str(target.get("canonical_thread_id") or "").strip()
        if isinstance(target, Mapping)
        else ""
    )
    errors: list[str] = []

    def membership_signature(value: object) -> list[tuple[int, int, str]] | None:
        if not isinstance(value, list) or not all(
            isinstance(item, Mapping) for item in value
        ):
            return None
        try:
            return sorted(
                (
                    int(item["atom_id"]),
                    int(item["raw_thread_id"]),
                    str(item.get("relation") or "supports"),
                )
                for item in value
            )
        except (KeyError, TypeError, ValueError):
            return None

    def alias_signature(value: object) -> list[tuple[str, str]] | None:
        if not isinstance(value, list) or not all(
            isinstance(item, Mapping) for item in value
        ):
            return None
        result = sorted(
            (
                str(item.get("alias_type") or "").strip(),
                str(item.get("alias_value") or "").strip(),
            )
            for item in value
        )
        return (
            result
            if all(alias_type and alias_value for alias_type, alias_value in result)
            else None
        )

    if operation == "merge":
        if isinstance(target, Mapping):
            reserved_nested = sorted({"thread", "atom_ids"}.intersection(target))
            if reserved_nested:
                errors.append(
                    "merge target contains reserved nested fields: "
                    + ", ".join(reserved_nested)
                )
        nested_memberships = (
            target.get("atom_memberships") if isinstance(target, Mapping) else None
        )
        if (
            membership_signature(nested_memberships) is None
            or membership_signature(nested_memberships)
            != membership_signature(proposal.get("atom_memberships"))
        ):
            errors.append(
                "merge target atom_memberships must equal normalized candidate memberships"
            )
        nested_aliases = target.get("aliases") if isinstance(target, Mapping) else None
        if (
            alias_signature(nested_aliases) is None
            or alias_signature(nested_aliases)
            != alias_signature(proposal.get("aliases"))
        ):
            errors.append("merge target aliases must equal normalized proposal aliases")

    placeholders = ",".join("?" for _ in expected_atom_ids)
    owner_rows = _rows(
        connection.execute(
            f"""
            SELECT atom_id, canonical_thread_id
            FROM canonical_idea_thread_atom_history
            WHERE atom_id IN ({placeholders}) AND valid_to IS NULL
            ORDER BY atom_id, canonical_thread_id
            """,
            sorted(expected_atom_ids),
        )
    )
    owners_by_atom: dict[int, set[str]] = {
        atom_id: set() for atom_id in expected_atom_ids
    }
    for row in owner_rows:
        owners_by_atom[int(row["atom_id"])].add(str(row["canonical_thread_id"]))

    if operation == "update":
        if proposal.get("source_thread_ids") is not None:
            errors.append("update proposal cannot contain merge source_thread_ids")
        current_owners = {
            owner for owners in owners_by_atom.values() for owner in owners
        }
        if not target_id or current_owners - {target_id}:
            errors.append(
                "update target is not the sole current canonical owner of candidate atoms"
            )
        if target_id:
            target_atom_ids = {
                int(row[0])
                for row in connection.execute(
                    """
                    SELECT atom_id
                    FROM canonical_idea_thread_atom_history
                    WHERE canonical_thread_id = ? AND valid_to IS NULL
                    ORDER BY atom_id
                    """,
                    (target_id,),
                ).fetchall()
            }
            if not target_atom_ids or not target_atom_ids.issubset(expected_atom_ids):
                errors.append(
                    "update target memberships are not contained in candidate atom evidence"
                )
        return tuple(errors)

    raw_source_ids = proposal.get("source_thread_ids")
    if not isinstance(raw_source_ids, list) or not raw_source_ids:
        return tuple([*errors, "merge source_thread_ids must be a non-empty list"])
    source_ids = [str(value or "").strip() for value in raw_source_ids]
    if any(not value for value in source_ids) or len(set(source_ids)) != len(source_ids):
        return tuple(
            [
                *errors,
                "merge source_thread_ids must contain distinct canonical identities",
            ]
        )

    involved_ids = set(source_ids)
    if target_id:
        involved_ids.add(target_id)
    involved_placeholders = ",".join("?" for _ in involved_ids)
    involved_rows = _rows(
        connection.execute(
            f"""
            SELECT canonical_thread_id, atom_id
            FROM canonical_idea_thread_atom_history
            WHERE canonical_thread_id IN ({involved_placeholders})
              AND valid_to IS NULL
            ORDER BY canonical_thread_id, atom_id
            """,
            sorted(involved_ids),
        )
    )
    membership_ids = {int(row["atom_id"]) for row in involved_rows}
    existing_involved_ids = {
        str(row["canonical_thread_id"]) for row in involved_rows
    }
    current_owner_ids = {
        owner for owners in owners_by_atom.values() for owner in owners
    }
    unowned_or_ambiguous = {
        atom_id
        for atom_id, owners in owners_by_atom.items()
        if len(owners) != 1
    }
    expected_existing_ids = set(source_ids)
    if target_id in existing_involved_ids:
        expected_existing_ids.add(target_id)
    if unowned_or_ambiguous or current_owner_ids != expected_existing_ids:
        errors.append(
            "merge sources are not the exact current canonical owners of candidate atoms"
        )
    if membership_ids != expected_atom_ids:
        errors.append(
            "merge source memberships do not exactly match candidate atom evidence"
        )
    return tuple(errors)


def _proposal_snapshot_errors(
    connection: sqlite3.Connection, proposal: Mapping[str, object]
) -> tuple[str, ...]:
    errors: list[str] = []
    proposal_id = str(proposal.get("proposal_id") or "").strip()
    identity_payload = {
        key: value for key, value in proposal.items() if key != "proposal_id"
    }
    expected_proposal_id = f"ctp_{_digest(identity_payload, length=32)}"
    if proposal_id != expected_proposal_id:
        errors.append("proposal_id does not match the immutable proposal payload")

    raw_sources = proposal.get("source_records")
    if not isinstance(raw_sources, list) or not raw_sources or not all(
        isinstance(item, Mapping) for item in raw_sources
    ):
        return tuple(errors + ["proposal requires bounded source_records"])
    if len(raw_sources) > MAX_RAW_THREADS_PER_CANDIDATE:
        errors.append("proposal exceeds the raw-thread bound")
    expected_raw_ids: list[int] = []
    expected_atom_ids: set[int] = set()
    for source in raw_sources:
        assert isinstance(source, Mapping)
        try:
            raw_thread_id = int(source["raw_thread_id"])
            recorded_atom_ids = sorted(_ints(source.get("atom_ids")))
            recorded_count = int(source.get("membership_count"))
        except (KeyError, TypeError, ValueError):
            errors.append("source record identity/count is malformed")
            continue
        expected_raw_ids.append(raw_thread_id)
        expected_atom_ids.update(recorded_atom_ids)
        if len(recorded_atom_ids) > MAX_ATOMS_PER_RAW_THREAD:
            errors.append(f"source record {raw_thread_id} exceeds the atom bound")
        exists = connection.execute(
            "SELECT 1 FROM idea_threads WHERE id = ? LIMIT 1", (raw_thread_id,)
        ).fetchone()
        if exists is None:
            errors.append(f"raw thread {raw_thread_id} no longer exists")
            continue
        current_atom_ids = [
            int(row[0])
            for row in connection.execute(
                """
                SELECT atom_id
                FROM idea_thread_atoms
                WHERE thread_id = ?
                ORDER BY atom_id
                """,
                (raw_thread_id,),
            ).fetchall()
        ]
        if recorded_count != len(recorded_atom_ids):
            errors.append(f"source record {raw_thread_id} contains truncated memberships")
        if recorded_count != len(current_atom_ids) or recorded_atom_ids != current_atom_ids:
            errors.append(
                f"source record {raw_thread_id} is stale: raw atom membership changed"
            )

    evidence = proposal.get("evidence")
    if not isinstance(evidence, Mapping):
        return tuple(errors + ["proposal evidence must be an object"])
    evidence_raw_ids = sorted(_ints(evidence.get("raw_thread_ids")))
    evidence_atom_ids = set(_ints(evidence.get("atom_ids")))
    if len(expected_atom_ids) > MAX_ATOM_EVIDENCE_PER_CANDIDATE:
        errors.append("proposal exceeds the total atom-evidence bound")
    source_provenance = evidence.get("source_provenance")
    if (
        not isinstance(source_provenance, list)
        or len(source_provenance) > MAX_SOURCE_REFS_PER_CANDIDATE
    ):
        errors.append("proposal source provenance exceeds its bound")
    if evidence_raw_ids != sorted(expected_raw_ids):
        errors.append("proposal evidence raw_thread_ids contradict source_records")
    if evidence_atom_ids != expected_atom_ids:
        errors.append("proposal evidence atom_ids contradict source_records")

    errors.extend(
        _canonical_owner_binding_errors(
            connection,
            proposal,
            expected_atom_ids=expected_atom_ids,
        )
    )

    if expected_atom_ids:
        placeholders = ",".join("?" for _ in expected_atom_ids)
        atom_rows = _rows(
            connection.execute(
                f"""
                SELECT id, atom_type, claim, summary, evidence_quote,
                       source_post_ids_json, source_urls_json, entities_json,
                       tools_json, models_json, practices_json,
                       first_seen_at, last_seen_at
                FROM knowledge_atoms
                WHERE id IN ({placeholders})
                ORDER BY id
                """,
                sorted(expected_atom_ids),
            )
        )
        if {int(row["id"]) for row in atom_rows} != expected_atom_ids:
            errors.append("proposal atom evidence no longer resolves to stored atoms")
        current_posts = sorted(
            {
                value
                for row in atom_rows
                for value in _ints(row.get("source_post_ids_json"))
            }
        )
        current_urls = sorted(
            {
                value
                for row in atom_rows
                for value in _strings(row.get("source_urls_json"))
            }
        )
        current_provenance = ([{"source_post_id": value} for value in current_posts] + [
            {"source_url": value} for value in current_urls
        ])
        if evidence.get("source_provenance") != current_provenance:
            errors.append("proposal source provenance is stale or incomplete")

        atoms_by_id = {
            int(row["id"]): {
                "atom_id": int(row["id"]),
                "atom_type": str(row.get("atom_type") or ""),
                "claim": str(row.get("claim") or ""),
                "summary": str(row.get("summary") or ""),
                "evidence_quote": str(row.get("evidence_quote") or ""),
                "source_post_ids": _ints(row.get("source_post_ids_json")),
                "source_urls": _strings(row.get("source_urls_json")),
                "entities": _strings(row.get("entities_json")),
                "tools": _strings(row.get("tools_json")),
                "models": _strings(row.get("models_json")),
                "practices": _strings(row.get("practices_json")),
                "first_seen_at": str(row.get("first_seen_at") or ""),
                "last_seen_at": str(row.get("last_seen_at") or ""),
            }
            for row in atom_rows
        }
        current_evidence: list[dict[str, object]] = []
        for source in raw_sources:
            assert isinstance(source, Mapping)
            raw_id = int(source["raw_thread_id"])
            membership_rows = connection.execute(
                """
                SELECT atom_id, relation
                FROM idea_thread_atoms
                WHERE thread_id = ?
                ORDER BY atom_id
                """,
                (raw_id,),
            ).fetchall()
            for atom_id_value, relation_value in membership_rows:
                atom_id = int(atom_id_value)
                if atom_id not in atoms_by_id:
                    continue
                current_evidence.append(
                    {
                        **atoms_by_id[atom_id],
                        "raw_thread_id": raw_id,
                        "relation": str(relation_value or "supports"),
                    }
                )
        current_fingerprint = _candidate_snapshot_fingerprint(
            raw_sources, current_evidence, current_provenance
        )
        if str(evidence.get("candidate_snapshot_fingerprint") or "") != current_fingerprint:
            errors.append("candidate snapshot fingerprint is stale")
        semantic_snapshots: list[dict[str, object]] = []
        for source in raw_sources:
            assert isinstance(source, Mapping)
            raw_id = int(source["raw_thread_id"])
            atoms = [
                atoms_by_id[atom_id]
                for atom_id in _ints(source.get("atom_ids"))
                if atom_id in atoms_by_id
            ]
            semantic_snapshots.append(
                {
                    "raw_thread_id": raw_id,
                    "practice_signals": sorted(
                        {signal for atom in atoms for signal in _practice_signals(atom)}
                    ),
                    "idea_terms": sorted(
                        {term for atom in atoms for term in _idea_terms(atom)}
                    ),
                    "entities": sorted(
                        {
                            str(value)
                            for atom in atoms
                            for value in atom.get("entities") or []
                        },
                        key=str.casefold,
                    ),
                    "models": sorted(
                        {
                            str(value)
                            for atom in atoms
                            for value in atom.get("models") or []
                        },
                        key=str.casefold,
                    ),
                }
            )
        operation = str(proposal.get("operation") or "")
        if operation in {"create", "update", "merge"} and len(semantic_snapshots) >= 2:
            components = _connected_components(semantic_snapshots)
            expected_sources = {int(item["raw_thread_id"]) for item in semantic_snapshots}
            if not any(set(component) == expected_sources for component, _edges in components):
                errors.append(
                    "stored non-entity idea/practice evidence does not support grouping; "
                    "entity or model overlap alone cannot merge"
                )
        if operation == "split" and len(semantic_snapshots) == 1:
            source = raw_sources[0]
            assert isinstance(source, Mapping)
            source_atoms = [
                atoms_by_id[atom_id]
                for atom_id in _ints(source.get("atom_ids"))
                if atom_id in atoms_by_id
            ]
            if len(_atom_components(source_atoms)) < 2:
                errors.append(
                    "stored non-entity evidence does not support split; model-version "
                    "difference alone cannot split"
                )
    return tuple(dict.fromkeys(errors))


def validate_curator_proposal(
    connection: sqlite3.Connection,
    proposal: Mapping[str, object],
    *,
    event_at: datetime | str | None = None,
) -> tuple[str, ...]:
    """Run the persistence layer's deterministic lifecycle validator."""

    metadata = _proposal_metadata(proposal)
    snapshot_errors = _proposal_snapshot_errors(connection, proposal)
    if snapshot_errors:
        return snapshot_errors
    from db.canonical_idea_threads import validate_canonical_lifecycle

    return tuple(
        validate_canonical_lifecycle(
            connection,
            dict(proposal),
            operation=metadata["operation"],
            event_at=event_at,
        )
    )


def record_curator_proposal(
    connection: sqlite3.Connection,
    proposal: Mapping[str, object],
    *,
    proposed_at: datetime | str | None = None,
    actor: str | None = None,
) -> dict[str, object]:
    """Explicitly append proposal audit data without applying canonical state."""

    metadata = _proposal_metadata(proposal)
    from db.canonical_idea_threads import record_curator_proposal as persist_proposal

    return persist_proposal(
        connection,
        run_id=metadata["run_id"],
        operation=metadata["operation"],
        proposal=dict(proposal),
        model=metadata["model"],
        model_version=metadata["model_version"],
        curator_version=metadata["curator_version"],
        reason=metadata["reason"],
        proposed_at=proposed_at,
        actor=actor or str(proposal.get("curator") or "curator"),
    )


def apply_curator_proposal(
    connection: sqlite3.Connection,
    proposal: Mapping[str, object],
    *,
    event_at: datetime | str | None = None,
    actor: str | None = None,
    proposal_id: int | str | None = None,
) -> dict[str, object]:
    """Strictly validate and apply under one persistence writer transaction."""

    metadata = _proposal_metadata(proposal)
    from db.canonical_idea_threads import (
        CanonicalLifecycleError,
        apply_canonical_lifecycle,
    )

    try:
        return apply_canonical_lifecycle(
            connection,
            run_id=metadata["run_id"],
            operation=metadata["operation"],
            proposal=dict(proposal),
            model=metadata["model"],
            model_version=metadata["model_version"],
            curator_version=metadata["curator_version"],
            reason=metadata["reason"],
            event_at=event_at,
            actor=actor or str(proposal.get("curator") or "curator"),
            proposal_id=proposal_id,
            strict_validator=_proposal_snapshot_errors,
        )
    except CanonicalLifecycleError as exc:
        raise CuratorContractError(
            "canonical lifecycle proposal rejected: " + "; ".join(exc.errors)
        ) from exc


def _canonical_alias_owners_as_of(
    connection: sqlite3.Connection,
    *,
    aliases: Sequence[tuple[str, str]],
    as_of: str,
) -> set[str] | None:
    """Return one consistent typed-alias owner set, or ``None`` on ambiguity.

    Typed history is queried directly so a mutable raw slug that happens to
    equal a canonical stable slug cannot bypass the alias namespace.  The
    exclusive-period-end predicate matches the canonical persistence reader.
    """

    owners: set[str] = set()
    for alias_type, alias_value in aliases:
        normalized = " ".join(
            unicodedata.normalize("NFKC", str(alias_value or "")).split()
        ).casefold()
        if not normalized:
            continue
        rows = connection.execute(
            """
            SELECT DISTINCT canonical_thread_id
            FROM canonical_idea_thread_alias_history
            WHERE alias_type = ?
              AND normalized_alias = ?
              AND valid_from < ?
              AND (valid_to IS NULL OR valid_to >= ?)
            ORDER BY canonical_thread_id
            """,
            (alias_type, normalized, as_of, as_of),
        ).fetchall()
        alias_owners = {str(row[0]) for row in rows}
        if len(alias_owners) > 1:
            return None
        owners.update(alias_owners)
        if len(owners) > 1:
            return None
    return owners


def _period_bounded_atom_ids(
    connection: sqlite3.Connection,
    atom_ids: Iterable[int],
    *,
    as_of: str,
) -> list[int] | None:
    """Drop atoms first visible after the report boundary before fallback."""

    requested = sorted({int(value) for value in atom_ids if int(value) > 0})
    if not requested:
        return []
    placeholders = ",".join("?" for _ in requested)
    rows = connection.execute(
        f"""
        SELECT id, last_seen_at
        FROM knowledge_atoms
        WHERE id IN ({placeholders})
        ORDER BY id
        """,
        requested,
    ).fetchall()
    if {int(row[0]) for row in rows} != set(requested):
        return None

    from db.canonical_idea_threads import normalize_canonical_utc

    bounded: list[int] = []
    for atom_id, last_seen_at in rows:
        observed_at = normalize_canonical_utc(
            last_seen_at, "knowledge atom last_seen_at"
        )
        if observed_at < as_of:
            bounded.append(int(atom_id))
    return bounded


@dataclass(frozen=True, slots=True)
class StoredCanonicalThreadResolver:
    """Resolve IRX-3 attribution from stored aliases/memberships at one as-of."""

    connection: sqlite3.Connection
    as_of: datetime | str

    def resolve(self, thread: Mapping[str, object]) -> ThreadResolution:
        slug = str(thread.get("slug") or "").strip()
        compatibility_ref = f"idea_thread:{slug}" if slug else None
        compatibility_only = ThreadResolution(
            compatibility_thread_ref=compatibility_ref,
            current_thread_ref=compatibility_ref,
            canonical_thread_ref=None,
            resolution_status="compatibility_current_thread_only",
        )
        aliases: list[tuple[str, str]] = []
        raw_thread_id = thread.get("id")
        try:
            clean_raw_thread_id = int(raw_thread_id)
        except (TypeError, ValueError):
            clean_raw_thread_id = 0
        if clean_raw_thread_id > 0:
            aliases.append(("raw_thread_id", str(clean_raw_thread_id)))
        if slug:
            aliases.extend(
                (
                    ("compatibility_ref", compatibility_ref or ""),
                    ("raw_thread_slug", slug),
                )
            )

        from db.canonical_idea_threads import (
            TERMINAL_CANONICAL_THREAD_STATUSES,
            fetch_canonical_thread,
            normalize_canonical_utc,
            resolve_canonical_atoms,
        )

        try:
            boundary = normalize_canonical_utc(self.as_of, "as_of")
            alias_owners = _canonical_alias_owners_as_of(
                self.connection,
                aliases=aliases,
                as_of=boundary,
            )
            if alias_owners is None:
                return compatibility_only
            if alias_owners:
                canonical = fetch_canonical_thread(
                    self.connection,
                    next(iter(alias_owners)),
                    as_of=boundary,
                )
                if canonical is None:
                    return compatibility_only
                if str(canonical.get("status") or "") not in TERMINAL_CANONICAL_THREAD_STATUSES:
                    stable_slug = str(canonical.get("stable_slug") or "").strip()
                    if stable_slug:
                        return ThreadResolution(
                            compatibility_thread_ref=compatibility_ref,
                            current_thread_ref=compatibility_ref,
                            canonical_thread_ref=f"canonical_thread:{stable_slug}",
                            resolution_status="canonical_membership_resolved",
                        )

            # A split source intentionally retains its broad raw alias.  Never
            # attribute that terminal identity; exact period-bounded atom
            # ownership may still resolve one child, otherwise remain nullable.
            atom_ids = _period_bounded_atom_ids(
                self.connection,
                thread.get("atom_ids") or [],
                as_of=boundary,
            )
            if not atom_ids:
                return compatibility_only
            canonical = resolve_canonical_atoms(
                self.connection, atom_ids, as_of=boundary
            )
        except (sqlite3.Error, TypeError, ValueError):
            return compatibility_only

        stable_slug = str((canonical or {}).get("stable_slug") or "").strip()
        status = str((canonical or {}).get("status") or "")
        if not stable_slug or status in TERMINAL_CANONICAL_THREAD_STATUSES:
            return compatibility_only
        return ThreadResolution(
            compatibility_thread_ref=compatibility_ref,
            current_thread_ref=compatibility_ref,
            canonical_thread_ref=f"canonical_thread:{stable_slug}",
            resolution_status="canonical_membership_resolved",
        )


def canonical_snapshot_fingerprint(
    connection: sqlite3.Connection,
    *,
    as_of: datetime | str,
    limit: int = 500,
) -> str:
    """Fingerprint a complete bounded canonical snapshot for stale-proposal checks."""

    hard_limit = _bounded(limit, default=500, hard_limit=500)
    from db.canonical_idea_threads import (
        fetch_canonical_provenance,
        fetch_canonical_threads,
    )

    threads = fetch_canonical_threads(
        connection, as_of=as_of, limit=hard_limit + 1
    )
    if len(threads) > hard_limit:
        raise CuratorContractError("canonical snapshot exceeds fingerprint bound")
    snapshot = []
    for thread in threads:
        canonical_id = str(thread.get("canonical_thread_id") or "")
        snapshot.append(
            {
                "thread": thread,
                "provenance": fetch_canonical_provenance(
                    connection, canonical_id, as_of=as_of
                ),
            }
        )
    return "sha256:" + _digest(snapshot, length=64)


__all__ = [
    "CURATOR_CONTRACT_VERSION",
    "CURATOR_PROPOSAL_SCHEMA_VERSION",
    "GROUPING_CANDIDATE_SCHEMA_VERSION",
    "CuratorContractError",
    "StoredCanonicalThreadResolver",
    "accept_strong_model_proposal",
    "apply_curator_proposal",
    "build_curator_proposal",
    "build_grouping_candidates",
    "canonical_snapshot_fingerprint",
    "generate_grouping_candidates",
    "record_curator_proposal",
    "validate_curator_proposal",
]

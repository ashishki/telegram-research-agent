#!/usr/bin/env python3
"""Generate PRM-QA Eval V2 private silver cases without source self-answers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from db.archive_search import search_telegram_archive  # noqa: E402
from llm.client import LLMClient, suppress_usage_recording  # noqa: E402


DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "agent.db"
DEFAULT_OUT = PROJECT_ROOT / "data" / "evals" / "private" / "prm_qa" / "cases.v2.jsonl"
DEFAULT_MANIFEST = PROJECT_ROOT / "evals" / "prm_qa" / "prm_qa_dataset_manifest.v2.json"
SCHEMA_VERSION = "prm_qa.case.v2"
GENERATOR_VERSION = "prm_qa_private_dataset_generator.v2"
DATASET_VERSION = "prm_qa_private_2026-08-15_v2"
TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9_+-]{2,}")
TARGET_COUNTS = {
    "semantic_research": 24,
    "named_project_decision": 18,
    "writer_editor": 10,
    "learning": 8,
    "reaction_or_saved_recall": 6,
    "current_fact_verification": 6,
}
PROJECT_NAMES = (
    "telegram-research-agent",
    "AI_workflow_playbook",
    "Eval-Ground-Truth-Lab",
    "Demand-to-MVP-Radar",
)
COMMON_THEMES = {
    "evaluation_quality": ("eval", "evaluation", "benchmark", "quality", "ground", "claim", "citation", "метрик", "оцен"),
    "retrieval_memory": ("rag", "retrieval", "search", "memory", "archive", "vector", "fts", "контекст", "памят"),
    "agent_runtime": ("agent", "tool", "router", "workflow", "runtime", "assistant", "агент", "роут"),
    "product_decision": ("product", "mvp", "decision", "project", "backlog", "проект", "решени", "гипотез"),
    "editorial_research": ("post", "brief", "writer", "content", "editor", "пост", "бриф", "редактор"),
    "learning_loop": ("learn", "study", "explain", "experiment", "объясн", "изучи", "эксперимент"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--public-manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--seed", type=int, default=24081502)
    parser.add_argument("--min-cases", type=int, default=60)
    parser.add_argument("--live-models", action="store_true")
    parser.add_argument("--confirm-provider-egress", action="store_true")
    args = parser.parse_args()

    live_models = bool(args.live_models)
    if live_models and not args.confirm_provider_egress:
        parser.error("--live-models requires --confirm-provider-egress")
    if live_models and os.environ.get("PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS", "").casefold() not in {"1", "true", "yes", "approved"}:
        parser.error("--live-models requires PRM_TELEGRAM_ALLOW_PROVIDER_EGRESS=1")

    db_path = Path(args.db)
    rng = random.Random(args.seed)
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        posts = _load_posts(connection)
        if len(posts) < 20:
            raise SystemExit("archive does not contain enough posts for PRM-QA V2 generation")
        corpus_df = _document_frequency(posts)
        clusters = _source_clusters(posts)
        cases = build_cases(connection, clusters, corpus_df=corpus_df, rng=rng, seed=args.seed, live_models=live_models)
        corpus_fingerprint = _corpus_fingerprint(connection, posts)

    if len(cases) < args.min_cases:
        raise SystemExit(f"generated only {len(cases)} cases, below --min-cases={args.min_cases}")
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        "\n".join(json.dumps(case, ensure_ascii=False, sort_keys=True) for case in cases) + "\n",
        encoding="utf-8",
    )
    manifest = _public_manifest(cases, corpus_fingerprint=corpus_fingerprint, seed=args.seed, out_path=out_path)
    manifest_path = Path(args.public_manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "case_count": len(cases), "private_cases": str(out_path), "public_manifest": str(manifest_path)}, ensure_ascii=False, sort_keys=True))
    return 0


def build_cases(
    connection: sqlite3.Connection,
    clusters: Sequence[Mapping[str, Any]],
    *,
    corpus_df: Mapping[str, int],
    rng: random.Random,
    seed: int,
    live_models: bool = False,
) -> list[dict[str, Any]]:
    pools = list(clusters)
    rng.shuffle(pools)
    result: list[dict[str, Any]] = []
    cursor = 0
    for job_type, count in TARGET_COUNTS.items():
        for index in range(count):
            cluster = pools[cursor % len(pools)]
            cursor += 1
            project_name = PROJECT_NAMES[index % len(PROJECT_NAMES)] if job_type == "named_project_decision" else ""
            summary = _semantic_summary_without_rare_terms(cluster, corpus_df=corpus_df)
            query = _generate_user_task(summary, job_type=job_type, project_name=project_name, live_models=live_models)
            allowed_query_terms = set(_tokens(project_name))
            leak = _query_leak_check(query, cluster, corpus_df=corpus_df, allowed_terms=allowed_query_terms)
            if not leak["passed"]:
                query = _fallback_query(summary, job_type=job_type, project_name=project_name)
                leak = _query_leak_check(query, cluster, corpus_df=corpus_df, allowed_terms=allowed_query_terms)
            if job_type == "current_fact_verification":
                candidates: list[dict[str, Any]] = []
                labels: list[dict[str, Any]] = []
            else:
                candidates = _pooled_retrieval(connection, query, cluster, limit=12)
                labels = _pairwise_relevance_labels(query, candidates, summary=summary, live_models=live_models)
            positives = [
                label
                for label in labels
                if label.get("label") in {"relevant", "highly_relevant", "partial"}
            ][:5]
            result.append(
                _case(
                    job_type=job_type,
                    query=query,
                    project_name=project_name,
                    semantic_summary=summary,
                    leak=leak,
                    candidates=candidates,
                    labels=labels,
                    positives=positives,
                    seed=seed,
                )
            )
    for idx, case in enumerate(result, start=1):
        case["case_id"] = f"prmqav2-{idx:04d}"
        case["holdout_partition"] = _partition(case)
    return result


def _load_posts(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    archive_documents = _table_exists(connection, "archive_documents")
    document_fields = (
        "COALESCE(d.content_hash, '') AS content_hash,"
        "COALESCE(d.duplicate_cluster_id, '') AS duplicate_cluster_id,"
        "COALESCE(d.repost_cluster_id, '') AS repost_cluster_id"
        if archive_documents
        else "'' AS content_hash, '' AS duplicate_cluster_id, '' AS repost_cluster_id"
    )
    document_join = "LEFT JOIN archive_documents d ON d.post_id = p.id" if archive_documents else ""
    rows = connection.execute(
        f"""
        SELECT p.id AS post_id, p.raw_post_id, p.channel_username, p.posted_at, p.content,
               COALESCE(r.message_url, '') AS source_url, {document_fields}
        FROM posts p
        INNER JOIN raw_posts r ON r.id = p.raw_post_id
        {document_join}
        WHERE length(trim(p.content)) >= 80
        ORDER BY p.posted_at DESC, p.id DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _source_clusters(posts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for post in posts:
        grouped[_source_group_id(post)].append(post)
    clusters = [
        {
            "cluster_id": cluster_id,
            "posts": list(items)[:5],
            "post_count": len(items),
            "latest_posted_at": max(str(item.get("posted_at") or "") for item in items),
        }
        for cluster_id, items in grouped.items()
    ]
    return sorted(clusters, key=lambda item: (item["post_count"], item["latest_posted_at"]), reverse=True)


def _semantic_summary_without_rare_terms(cluster: Mapping[str, Any], *, corpus_df: Mapping[str, int]) -> dict[str, Any]:
    text = " ".join(str(post.get("content") or "") for post in cluster.get("posts") or [])
    tokens = _tokens(text)
    theme_scores = {
        theme: sum(1 for token in tokens if any(marker in token for marker in markers))
        for theme, markers in COMMON_THEMES.items()
    }
    themes = [theme for theme, _score in sorted(theme_scores.items(), key=lambda item: item[1], reverse=True) if _score][:3]
    if not themes:
        themes = ["retrieval_memory"]
    language = "ru" if re.search(r"[А-Яа-яЁё]", text) else "en"
    evidence_shape = "implementation_or_eval_discussion" if any(theme in themes for theme in ("evaluation_quality", "agent_runtime", "retrieval_memory")) else "research_signal"
    return {
        "schema_version": "prm_qa.semantic_summary.v2",
        "themes": themes,
        "language": language,
        "evidence_shape": evidence_shape,
        "source_count": len(cluster.get("posts") or []),
        "rare_terms_removed": True,
        "names_removed": True,
        "summary_hash": _hash_json({"themes": themes, "language": language, "evidence_shape": evidence_shape}),
        "forbidden_term_count": len(_rare_terms(text, corpus_df=corpus_df)),
    }


def _generate_user_task(
    summary: Mapping[str, Any],
    *,
    job_type: str,
    project_name: str,
    live_models: bool,
) -> str:
    if not live_models:
        return _fallback_query(summary, job_type=job_type, project_name=project_name)
    prompt = (
        "You generate one realistic user task for a private Telegram research-memory assistant.\n"
        "You only see an abstract semantic summary. It has no source titles, names, brands, rare terms, or post text.\n"
        "Do not invent specific facts. Do not copy any term that looks like a source title. Make a natural user question.\n"
        "Return JSON: {\"query\":\"...\"}.\n\n"
        f"job_type: {job_type}\nproject_name: {project_name or 'none'}\nsemantic_summary:\n{json.dumps(dict(summary), ensure_ascii=False)}"
    )
    with suppress_usage_recording():
        data = LLMClient.complete_json(
            prompt=prompt,
            system="You are the query-generation model. You do not label relevance.",
            category="test",
            max_tokens=180,
            max_attempts=1,
        )
    if not isinstance(data, Mapping):
        raise ValueError("query model returned non-object JSON")
    return " ".join(str(data.get("query") or "").split())[:280]


def _fallback_query(summary: Mapping[str, Any], *, job_type: str, project_name: str) -> str:
    language = str(summary.get("language") or "en")
    themes = set(str(item) for item in summary.get("themes") or [])
    if job_type == "current_fact_verification":
        return "Что сейчас актуально по этой теме и нужна ли первоисточниковая проверка?"
    if job_type == "named_project_decision":
        return f"Как применить этот исследовательский сигнал к проекту {project_name} и какой следующий proof нужен?"
    if job_type == "writer_editor":
        return "Собери редакторский бриф по этой теме: тезисы, ограничения и источники." if language == "ru" else "Build an editor brief on this theme with theses, limits, and sources."
    if job_type == "learning":
        return "Объясни эту тему простыми словами и предложи маленький эксперимент." if language == "ru" else "Explain this theme simply and suggest one small experiment."
    if job_type == "reaction_or_saved_recall":
        return "Какие отмеченные или сохранённые материалы помогают вернуться к этой теме?" if language == "ru" else "Which reacted or saved materials help me revisit this theme?"
    if "evaluation_quality" in themes:
        return "Как мне проверить качество ответов ассистента и доказательств по архиву?" if language == "ru" else "How should I check assistant answer quality and evidence grounding from my archive?"
    if "retrieval_memory" in themes:
        return "Что в архиве помогает понять, достаточно ли локального retrieval для ответов?" if language == "ru" else "What in my archive helps decide whether local retrieval is enough for answers?"
    return "Что полезного в архиве по этой теме и что с этим делать дальше?" if language == "ru" else "What is useful in my archive on this theme, and what should I do next?"


def _pooled_retrieval(connection: sqlite3.Connection, query: str, cluster: Mapping[str, Any], *, limit: int) -> list[dict[str, Any]]:
    pool: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(item: Mapping[str, Any], *, origin: str) -> None:
        key = str(item.get("post_id") or item.get("source_url") or "")
        if not key or key in seen:
            return
        seen.add(key)
        pool.append({**dict(item), "pool_origin": origin})

    try:
        retrieved = search_telegram_archive(connection, query, limit=max(5, limit))
    except Exception:
        retrieved = []
    for item in retrieved:
        add(item.as_dict(), origin="query_retrieval")
    for post in cluster.get("posts") or []:
        if len(pool) >= limit:
            break
        add(_candidate_from_post(post), origin="source_cluster_seed")
    return pool[:limit]


def _pairwise_relevance_labels(
    query: str,
    candidates: Sequence[Mapping[str, Any]],
    *,
    summary: Mapping[str, Any],
    live_models: bool,
) -> list[dict[str, Any]]:
    if not candidates:
        return []
    if live_models:
        return _model_pairwise_relevance_labels(query, candidates, summary=summary)
    query_tokens = set(_tokens(query))
    theme_markers = {
        marker
        for theme in summary.get("themes") or []
        for marker in COMMON_THEMES.get(str(theme), ())
    }
    labels = []
    for candidate in candidates:
        text = str(candidate.get("snippet") or candidate.get("content") or "")
        tokens = set(_tokens(text))
        overlap = len(query_tokens & tokens)
        theme_overlap = sum(1 for token in tokens if any(marker in token for marker in theme_markers))
        label = "highly_relevant" if overlap >= 3 or theme_overlap >= 3 else "relevant" if overlap >= 2 or theme_overlap >= 2 else "partial" if overlap or theme_overlap else "not_relevant"
        labels.append(_label_row(candidate, label=label, rationale="deterministic_pairwise_theme_overlap"))
    return labels


def _model_pairwise_relevance_labels(
    query: str,
    candidates: Sequence[Mapping[str, Any]],
    *,
    summary: Mapping[str, Any],
) -> list[dict[str, Any]]:
    bounded = [
        {
            "candidate_id": _candidate_id(candidate),
            "snippet": " ".join(str(candidate.get("snippet") or candidate.get("content") or "").split())[:420],
        }
        for candidate in candidates[:12]
    ]
    prompt = (
        "You are the pairwise relevance reviewer, not the query generator. "
        "Label each candidate against the user query only. Do not reward lexical copies. "
        "Return JSON array with candidate_id, label highly_relevant|relevant|partial|not_relevant, rationale.\n\n"
        f"query: {query}\nsemantic_summary: {json.dumps(dict(summary), ensure_ascii=False)}\ncandidates:\n"
        f"{json.dumps(bounded, ensure_ascii=False, indent=2)}"
    )
    with suppress_usage_recording():
        data = LLMClient.complete_json(
            prompt=prompt,
            system="You are the independent pairwise relevance reviewer. You did not generate the query.",
            category="test",
            max_tokens=900,
            max_attempts=1,
        )
    by_id = {str(candidate.get("candidate_id") or ""): candidate for candidate in data} if isinstance(data, list) else {}
    labels = []
    for candidate in candidates:
        raw = by_id.get(_candidate_id(candidate), {})
        label = str(raw.get("label") or "not_relevant")
        if label not in {"highly_relevant", "relevant", "partial", "not_relevant"}:
            label = "not_relevant"
        labels.append(_label_row(candidate, label=label, rationale=str(raw.get("rationale") or "model_pairwise_review")[:180]))
    return labels


def _label_row(candidate: Mapping[str, Any], *, label: str, rationale: str) -> dict[str, Any]:
    return {
        "candidate_id": _candidate_id(candidate),
        "post_id": str(candidate.get("post_id") or ""),
        "source_group_id": _source_group_id(candidate),
        "label": label,
        "reviewer_role": "pairwise_relevance_reviewer",
        "reviewer_independent_of_query_generator": True,
        "rationale": rationale,
        "snippet_hash": _hash_text(str(candidate.get("snippet") or candidate.get("content") or "")),
    }


def _case(
    *,
    job_type: str,
    query: str,
    project_name: str,
    semantic_summary: Mapping[str, Any],
    leak: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    labels: Sequence[Mapping[str, Any]],
    positives: Sequence[Mapping[str, Any]],
    seed: int,
) -> dict[str, Any]:
    expected_route = "brief" if job_type == "writer_editor" else "research"
    if job_type == "current_fact_verification":
        expected_route = "research"
    expected_workflow = "writer_editor_brief" if expected_route == "brief" else "archive_research"
    if job_type == "current_fact_verification":
        expected_workflow = "current_fact_verification"
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_version": DATASET_VERSION,
        "generation_seed": seed,
        "generation_method": GENERATOR_VERSION,
        "job_type": job_type,
        "query": query,
        "language": "ru" if re.search(r"[А-Яа-яЁё]", query) else "en",
        "project_name": project_name,
        "expected_route": expected_route,
        "expected_workflow": expected_workflow,
        "expected_external_verification": job_type == "current_fact_verification",
        "semantic_summary_hash": semantic_summary.get("summary_hash"),
        "query_generation": {
            "input": "semantic_summary_without_names_or_rare_terms",
            "model_role": "query_generation_model",
            "separate_from_reviewer": True,
            "leak_check": dict(leak),
        },
        "pooled_retrieval": {
            "candidate_count": len(candidates),
            "origins": dict(sorted(Counter(str(item.get("pool_origin") or "unknown") for item in candidates).items())),
        },
        "relevance_labels": list(labels),
        "positive_source_ids": [str(item.get("post_id") or "") for item in positives if str(item.get("post_id") or "")],
        "positive_source_group_ids": _unique_strings([str(item.get("source_group_id") or "") for item in positives]),
        "label_quality": "silver_pairwise_v2",
        "privacy": {
            "contains_private_query": True,
            "contains_raw_telegram_body": False,
            "public_safe": False,
            "commit_allowed": False,
        },
    }


def _query_leak_check(
    query: str,
    cluster: Mapping[str, Any],
    *,
    corpus_df: Mapping[str, int],
    allowed_terms: set[str] | None = None,
) -> dict[str, Any]:
    source_text = " ".join(str(post.get("content") or "") for post in cluster.get("posts") or [])
    query_tokens = _tokens(query)
    source_tokens = _tokens(source_text)
    rare = _rare_terms(source_text, corpus_df=corpus_df)
    allowed = set(allowed_terms or set())
    rare_overlap = sorted((set(query_tokens) & rare) - allowed)
    source_ngrams = set(_ngrams(source_tokens, 3))
    query_ngram_hits = sorted(set(_ngrams(query_tokens, 3)) & source_ngrams)
    passed = not rare_overlap and not query_ngram_hits
    return {
        "schema_version": "prm_qa.query_leak_check.v2",
        "passed": passed,
        "rare_term_overlap_count": len(rare_overlap),
        "copied_source_phrase_count": len(query_ngram_hits),
        "rare_term_overlap_hashes": [_hash_text(item) for item in rare_overlap[:8]],
        "copied_phrase_hashes": [_hash_text(item) for item in query_ngram_hits[:8]],
    }


def _document_frequency(posts: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for post in posts:
        counts.update(set(_tokens(post.get("content"))))
    return dict(counts)


def _rare_terms(text: str, *, corpus_df: Mapping[str, int]) -> set[str]:
    result = set()
    for token in _tokens(text):
        if len(token) >= 9 and int(corpus_df.get(token) or 0) <= 2:
            result.add(token)
        if re.search(r"[A-Z][a-z]+[A-Z]|[_/]", token):
            result.add(token.casefold())
    return result


def _candidate_from_post(post: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "post_id": post.get("post_id"),
        "posted_at": post.get("posted_at"),
        "channel_username": post.get("channel_username"),
        "source_url": post.get("source_url"),
        "snippet": " ".join(str(post.get("content") or "").split())[:260],
        "content_hash": post.get("content_hash") or "",
        "duplicate_cluster_id": post.get("duplicate_cluster_id") or "",
        "repost_cluster_id": post.get("repost_cluster_id") or "",
    }


def _candidate_id(candidate: Mapping[str, Any]) -> str:
    return "cand:" + _hash_text(str(candidate.get("post_id") or candidate.get("source_url") or candidate.get("snippet") or ""))


def _source_group_id(item: Mapping[str, Any]) -> str:
    for key in ("repost_cluster_id", "duplicate_cluster_id", "content_hash"):
        value = str(item.get(key) or "").strip()
        if value:
            return f"{key}:{value[:24]}"
    source = str(item.get("source_url") or item.get("post_id") or "")
    return "sha256:" + hashlib.sha256(source.encode()).hexdigest()[:16]


def _tokens(value: object) -> list[str]:
    return [token.casefold() for token in TOKEN_RE.findall(str(value or ""))]


def _ngrams(tokens: Sequence[str], size: int) -> list[str]:
    return [" ".join(tokens[index : index + size]) for index in range(0, max(0, len(tokens) - size + 1))]


def _unique_strings(values: Sequence[str]) -> list[str]:
    result = []
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in result:
            result.append(clean)
    return result


def _partition(case: Mapping[str, Any]) -> str:
    key = "|".join(str(item) for item in case.get("positive_source_group_ids") or []) or str(case.get("job_type")) + ":" + str(case.get("query"))
    bucket = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % 10
    if bucket >= 8:
        return "holdout"
    if bucket >= 6:
        return "tuning"
    return "development"


def _corpus_fingerprint(connection: sqlite3.Connection, posts: Sequence[Mapping[str, Any]]) -> str:
    row = connection.execute("SELECT COUNT(*), MIN(posted_at), MAX(posted_at), SUM(length(content)) FROM posts").fetchone()
    payload = {
        "post_count": int(row[0] or 0),
        "min_posted_at": str(row[1] or ""),
        "max_posted_at": str(row[2] or ""),
        "content_length_sum": int(row[3] or 0),
        "eligible_post_count": len(posts),
    }
    return "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _public_manifest(cases: Sequence[Mapping[str, Any]], *, corpus_fingerprint: str, seed: int, out_path: Path) -> dict[str, Any]:
    return {
        "schema_version": "prm_qa_dataset_manifest.v2",
        "dataset_version": DATASET_VERSION,
        "generator_version": GENERATOR_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "generation_seed": seed,
        "corpus_fingerprint": corpus_fingerprint,
        "case_count": len(cases),
        "job_type_counts": dict(sorted(Counter(str(case["job_type"]) for case in cases).items())),
        "partition_counts": dict(sorted(Counter(str(case["holdout_partition"]) for case in cases).items())),
        "label_quality_counts": dict(sorted(Counter(str(case["label_quality"]) for case in cases).items())),
        "private_dataset_path": _display_path(out_path),
        "methodology": {
            "source_selection": "source_cluster",
            "query_input": "semantic_summary_without_source_names_titles_or_rare_terms",
            "query_leak_check": "rare term and copied phrase rejection",
            "positive_construction": "pooled_retrieval_plus_pairwise_reviewer",
            "query_generator_independent_from_relevance_reviewer": True,
        },
        "privacy": {
            "manifest_contains_queries": False,
            "manifest_contains_raw_telegram_body": False,
            "manifest_contains_source_urls": False,
            "private_cases_gitignored": True,
            "public_commit_allowed": True,
        },
        "honesty_boundary": "Eval V2 is automated silver evidence, not independent human gold or proof of operator usefulness.",
    }


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _hash_text(value: str) -> str:
    return hashlib.sha256(str(value or "").encode()).hexdigest()[:16]


def _hash_json(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(dict(value), sort_keys=True).encode()).hexdigest()


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    row = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1", (name,)).fetchone()
    return row is not None


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Generate a private PRM-QA evaluation dataset from the local archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "agent.db"
DEFAULT_OUT = PROJECT_ROOT / "data" / "evals" / "private" / "prm_qa" / "cases.v1.jsonl"
DEFAULT_MANIFEST = PROJECT_ROOT / "evals" / "prm_qa" / "prm_qa_dataset_manifest.v1.json"
SCHEMA_VERSION = "prm_qa.case.v1"
GENERATOR_VERSION = "prm_qa_private_dataset_generator.v1"
DATASET_VERSION = "prm_qa_private_2026-08-15_v1"

TARGET_COUNTS = {
    "exact_known_item": 20,
    "semantic_topic": 25,
    "case_study": 15,
    "comparison": 12,
    "timeline_freshness": 12,
    "named_project_decision": 25,
    "ambiguous_project": 10,
    "writer_editor": 8,
    "learning_experiment": 8,
    "reacted_post_recall": 5,
    "saved_knowledge_recall": 5,
    "no_answer": 5,
    "current_fact": 5,
    "distractor_hard_negative": 5,
}

TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9_+-]{2,}")
STOPWORDS = {
    "что",
    "как",
    "где",
    "когда",
    "это",
    "для",
    "про",
    "или",
    "the",
    "and",
    "for",
    "with",
    "about",
    "from",
    "that",
    "this",
    "are",
    "was",
    "were",
    "можно",
    "нужно",
}
PROJECT_NAMES = [
    "telegram-research-agent",
    "AI_workflow_playbook",
    "Agent-Runtime-Grid",
    "Eval-Ground-Truth-Lab",
    "Demand-to-MVP-Radar",
    "Dream_Motif_Interpreter",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--public-manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--seed", type=int, default=240815)
    parser.add_argument("--min-cases", type=int, default=150)
    args = parser.parse_args()

    db_path = Path(args.db)
    out_path = Path(args.out)
    public_manifest_path = Path(args.public_manifest)
    rng = random.Random(args.seed)
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        posts = _load_posts(connection)
        reactions = _load_reacted_posts(connection)
        saved = _load_saved_memory(connection)
        corpus = _corpus_fingerprint(connection, posts)
    if len(posts) < 20:
        raise SystemExit("archive does not contain enough posts for PRM-QA generation")

    cases = _build_cases(posts, reactions, saved, rng=rng, seed=args.seed, corpus_fingerprint=corpus)
    if len(cases) < args.min_cases:
        raise SystemExit(f"generated only {len(cases)} cases, below --min-cases={args.min_cases}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(json.dumps(case, ensure_ascii=False, sort_keys=True) for case in cases) + "\n", encoding="utf-8")
    manifest = _public_manifest(cases, corpus_fingerprint=corpus, seed=args.seed, out_path=out_path)
    public_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    public_manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "case_count": len(cases), "private_cases": str(out_path), "public_manifest": str(public_manifest_path)}, ensure_ascii=False, sort_keys=True))
    return 0


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
        SELECT
            p.id AS post_id,
            p.raw_post_id,
            p.channel_username,
            p.posted_at,
            p.content,
            p.language_detected,
            COALESCE(r.message_url, '') AS source_url,
            {document_fields}
        FROM posts p
        INNER JOIN raw_posts r ON r.id = p.raw_post_id
        {document_join}
        WHERE length(trim(p.content)) >= 80
        ORDER BY p.posted_at DESC, p.id DESC
        """
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["terms"] = _terms(item["content"])
        if len(item["terms"]) >= 3:
            result.append(item)
    return result


def _load_reacted_posts(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    try:
        rows = connection.execute(
            """
            SELECT p.id AS post_id, p.raw_post_id, p.channel_username, p.posted_at, p.content,
                   COALESCE(r.message_url, '') AS source_url,
                   COUNT(sf.id) AS reaction_count
            FROM signal_feedback sf
            INNER JOIN posts p ON p.id = sf.post_id
            INNER JOIN raw_posts r ON r.id = p.raw_post_id
            WHERE length(trim(p.content)) >= 80
            GROUP BY p.id
            ORDER BY reaction_count DESC, p.posted_at DESC
            LIMIT 50
            """
        ).fetchall()
    except sqlite3.Error:
        return []
    result = []
    for row in rows:
        item = dict(row)
        item["terms"] = _terms(item["content"])
        if item["terms"]:
            result.append(item)
    return result


def _load_saved_memory(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    try:
        rows = connection.execute(
            """
            SELECT memory_id, object_type, title, body, source_refs_json, created_at
            FROM personal_memory_events
            WHERE event_type = 'created'
            ORDER BY created_at DESC
            LIMIT 30
            """
        ).fetchall()
    except sqlite3.Error:
        return []
    return [dict(row) for row in rows]


def _build_cases(
    posts: list[dict[str, Any]],
    reactions: list[dict[str, Any]],
    saved: list[dict[str, Any]],
    *,
    rng: random.Random,
    seed: int,
    corpus_fingerprint: str,
) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    pools = list(posts)
    rng.shuffle(pools)
    cursor = 0

    def take() -> dict[str, Any]:
        nonlocal cursor
        item = pools[cursor % len(pools)]
        cursor += 1
        return item

    builders = {
        "exact_known_item": lambda i: _source_case(i, "exact_known_item", f"Найди пост примерно от {i['posted_at'][:10]}, где обсуждали {_topic(i)}.", "research", "archive_research", "deterministic"),
        "semantic_topic": lambda i: _source_case(i, "semantic_topic", f"Что в архиве есть про {_topic(i)}?", "research", "archive_research", "silver"),
        "case_study": lambda i: _source_case(i, "case_study", f"Какие практические кейсы есть по теме {_topic(i)}?", "research", "archive_research", "silver"),
        "comparison": lambda i: _source_case(i, "comparison", f"Сравни подходы вокруг {_pair_topic(i)} по локальным материалам.", "research", "archive_research", "silver"),
        "timeline_freshness": lambda i: _source_case(i, "timeline_freshness", f"Что изменилось по теме {_topic(i)} в период вокруг {i['posted_at'][:7]}?", "research", "archive_research", "silver", date_from=i["posted_at"][:10]),
        "writer_editor": lambda i: _source_case(i, "writer_editor", f"Собери редакторский бриф про {_topic(i)} на основе архива.", "brief", "writer_editor_brief", "silver"),
        "learning_experiment": lambda i: _source_case(i, "learning_experiment", f"Объясни {_topic(i)} простыми словами и предложи маленький эксперимент.", "research", "archive_research", "silver"),
    }
    for job_type, count in TARGET_COUNTS.items():
        if job_type in builders:
            for _ in range(count):
                cases.append(builders[job_type](take()))
        elif job_type == "named_project_decision":
            for index in range(count):
                item = take()
                project = PROJECT_NAMES[index % len(PROJECT_NAMES)]
                cases.append(_source_case(item, job_type, f"Что из материалов про {_topic(item)} применимо к {project}?", "research", "archive_research", "deterministic", project_name=project))
        elif job_type == "ambiguous_project":
            for _ in range(count):
                item = take()
                cases.append(_source_case(item, job_type, f"Что из материалов про {_topic(item)} применимо к моему проекту?", "project_clarify", "clarify_project", "deterministic", expected_clarification=True))
        elif job_type == "reacted_post_recall":
            source = reactions or posts
            for index in range(count):
                item = source[index % len(source)]
                cases.append(_source_case(item, job_type, f"Найди материал, который я отмечал реакцией, про {_topic(item)}.", "research", "archive_research", "deterministic"))
        elif job_type == "saved_knowledge_recall":
            for index in range(count):
                if saved:
                    item = saved[index % len(saved)]
                    source_refs = _json_list(item.get("source_refs_json"))
                    cases.append(_base_case(job_type, f"Что у меня сохранено в памяти про {_memory_topic(item)}?", "research", "archive_research", "deterministic", expected_source_ids=[str(item.get("memory_id") or "")], expected_source_urls=source_refs))
                else:
                    cases.append(_negative_case(job_type, f"Что у меня сохранено в памяти про контрольную тему {index + 1}?", "research", "archive_research", "deterministic", expected_no_answer=True))
        elif job_type == "no_answer":
            for index in range(count):
                cases.append(_negative_case(job_type, f"Найди в архиве утверждение про synthetic-nonexistent-topic-{seed}-{index}.", "research", "archive_research", "deterministic", expected_no_answer=True))
        elif job_type == "current_fact":
            for index in range(count):
                term = _topic(take())
                cases.append(_negative_case(job_type, f"Какая актуальная цена или последняя версия сейчас у {term}?", "current_fact_verification", "current_fact_verification", "deterministic", expected_external_verification=True))
        elif job_type == "distractor_hard_negative":
            for index in range(count):
                item = take()
                cases.append(_negative_case(job_type, f"Найди точный пост про {_topic(item)} и nonexistent-control-{index}.", "research", "archive_research", "synthetic_negative", expected_no_answer=True))

    result = []
    for index, case in enumerate(cases, start=1):
        result.append(
            {
                **case,
                "schema_version": SCHEMA_VERSION,
                "case_id": f"prmqa-{index:04d}",
                "dataset_version": DATASET_VERSION,
                "generation_seed": seed,
                "corpus_fingerprint": corpus_fingerprint,
                "holdout_partition": _partition(case),
                "privacy": {
                    "contains_private_query": True,
                    "contains_raw_telegram_body": False,
                    "public_safe": False,
                    "commit_allowed": False,
                },
            }
        )
    return result


def _source_case(
    item: Mapping[str, Any],
    job_type: str,
    query: str,
    expected_route: str,
    expected_workflow: str,
    label_quality: str,
    *,
    project_name: str = "",
    date_from: str | None = None,
    date_to: str | None = None,
    expected_clarification: bool = False,
) -> dict[str, Any]:
    group_id = _source_group_id(item)
    return _base_case(
        job_type,
        query,
        expected_route,
        expected_workflow,
        label_quality,
        project_name=project_name,
        date_from=date_from,
        date_to=date_to,
        expected_source_ids=[str(item.get("post_id") or "")],
        expected_source_urls=[str(item.get("source_url") or "")],
        expected_source_group_ids=[group_id],
        expected_clarification=expected_clarification,
    )


def _negative_case(
    job_type: str,
    query: str,
    expected_route: str,
    expected_workflow: str,
    label_quality: str,
    *,
    expected_no_answer: bool = False,
    expected_external_verification: bool = False,
) -> dict[str, Any]:
    return _base_case(
        job_type,
        query,
        expected_route,
        expected_workflow,
        label_quality,
        expected_no_answer=expected_no_answer,
        expected_external_verification=expected_external_verification,
    )


def _base_case(
    job_type: str,
    query: str,
    expected_route: str,
    expected_workflow: str,
    label_quality: str,
    *,
    project_name: str = "",
    date_from: str | None = None,
    date_to: str | None = None,
    expected_source_ids: list[str] | None = None,
    expected_source_urls: list[str] | None = None,
    expected_source_group_ids: list[str] | None = None,
    expected_no_answer: bool = False,
    expected_external_verification: bool = False,
    expected_clarification: bool = False,
) -> dict[str, Any]:
    return {
        "job_type": job_type,
        "query": query,
        "language": "ru",
        "expected_route": expected_route,
        "expected_workflow": expected_workflow,
        "project_name": project_name,
        "date_from": date_from,
        "date_to": date_to,
        "expected_source_ids": expected_source_ids or [],
        "expected_source_urls": [url for url in expected_source_urls or [] if url],
        "expected_source_group_ids": [group for group in expected_source_group_ids or [] if group],
        "expected_no_answer": bool(expected_no_answer),
        "expected_external_verification": bool(expected_external_verification),
        "expected_clarification": bool(expected_clarification),
        "label_quality": label_quality,
        "generation_method": GENERATOR_VERSION,
    }


def _public_manifest(cases: list[Mapping[str, Any]], *, corpus_fingerprint: str, seed: int, out_path: Path) -> dict[str, Any]:
    by_job = Counter(str(case["job_type"]) for case in cases)
    by_partition = Counter(str(case["holdout_partition"]) for case in cases)
    by_quality = Counter(str(case["label_quality"]) for case in cases)
    return {
        "schema_version": "prm_qa_dataset_manifest.v1",
        "dataset_version": DATASET_VERSION,
        "generator_version": GENERATOR_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "generation_seed": seed,
        "corpus_fingerprint": corpus_fingerprint,
        "case_count": len(cases),
        "job_type_counts": dict(sorted(by_job.items())),
        "partition_counts": dict(sorted(by_partition.items())),
        "label_quality_counts": dict(sorted(by_quality.items())),
        "private_dataset_path": _display_path(out_path),
        "holdout_strategy": "Source-group hash isolation where source-backed; case hash for synthetic negatives/current-fact cases.",
        "privacy": {
            "manifest_contains_queries": False,
            "manifest_contains_raw_telegram_body": False,
            "manifest_contains_source_urls": False,
            "private_cases_gitignored": True,
            "public_commit_allowed": True,
        },
        "honesty_boundary": "Generated questions and deterministic/silver labels are regression evidence only, not proof of real operator value.",
    }


def _corpus_fingerprint(connection: sqlite3.Connection, posts: list[Mapping[str, Any]]) -> str:
    row = connection.execute("SELECT COUNT(*), MIN(posted_at), MAX(posted_at), SUM(length(content)) FROM posts").fetchone()
    channels = Counter(str(post.get("channel_username") or "") for post in posts)
    payload = {
        "post_count": int(row[0] or 0),
        "min_posted_at": str(row[1] or ""),
        "max_posted_at": str(row[2] or ""),
        "content_length_sum": int(row[3] or 0),
        "eligible_post_count": len(posts),
        "channel_count": len(channels),
        "channel_count_hash": hashlib.sha256(json.dumps(sorted(channels.values())).encode()).hexdigest(),
    }
    return "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _partition(case: Mapping[str, Any]) -> str:
    groups = list(case.get("expected_source_group_ids") or [])
    key = groups[0] if groups else str(case.get("job_type")) + ":" + str(case.get("query"))
    bucket = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % 10
    if bucket >= 8:
        return "holdout"
    if bucket >= 6:
        return "tuning"
    return "development"


def _terms(text: object) -> list[str]:
    tokens = []
    for token in TOKEN_RE.findall(str(text or "")):
        lowered = token.casefold()
        if lowered not in STOPWORDS and len(lowered) > 2 and lowered not in tokens:
            tokens.append(lowered)
    scored = sorted(tokens, key=lambda token: (-len(token), token))
    return scored[:12]


def _topic(item: Mapping[str, Any]) -> str:
    terms = list(item.get("terms") or [])
    return " ".join(terms[:3]) if terms else "локальный сигнал"


def _pair_topic(item: Mapping[str, Any]) -> str:
    terms = list(item.get("terms") or [])
    if len(terms) >= 4:
        return f"{terms[0]} и {terms[3]}"
    return _topic(item)


def _source_group_id(item: Mapping[str, Any]) -> str:
    for key in ("repost_cluster_id", "duplicate_cluster_id", "content_hash"):
        value = str(item.get(key) or "").strip()
        if value:
            return f"{key}:{value[:24]}"
    source = str(item.get("source_url") or item.get("post_id") or "")
    return "sha256:" + hashlib.sha256(source.encode()).hexdigest()[:16]


def _memory_topic(item: Mapping[str, Any]) -> str:
    return " ".join(_terms(f"{item.get('title') or ''} {item.get('body') or ''}")[:3]) or str(item.get("object_type") or "saved memory")


def _json_list(value: object) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).startswith("https://")]


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    row = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1", (name,)).fetchone()
    return row is not None


if __name__ == "__main__":
    raise SystemExit(main())

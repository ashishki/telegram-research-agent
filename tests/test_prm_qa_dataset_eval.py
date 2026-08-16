import json
import sqlite3
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _seed_archive(db_path: Path, count: int = 60) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE raw_posts (
                id INTEGER PRIMARY KEY,
                channel_username TEXT NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                posted_at TEXT NOT NULL,
                raw_json TEXT NOT NULL DEFAULT '',
                ingested_at TEXT NOT NULL DEFAULT '2026-08-01T10:00:00Z',
                message_url TEXT,
                forward_from TEXT
            );
            CREATE TABLE posts (
                id INTEGER PRIMARY KEY,
                raw_post_id INTEGER NOT NULL UNIQUE,
                channel_username TEXT NOT NULL,
                posted_at TEXT NOT NULL,
                content TEXT NOT NULL,
                url_count INTEGER NOT NULL DEFAULT 0,
                has_code INTEGER NOT NULL DEFAULT 0,
                language_detected TEXT,
                word_count INTEGER NOT NULL DEFAULT 0,
                normalized_at TEXT NOT NULL DEFAULT '2026-08-01T10:00:00Z'
            );
            CREATE VIRTUAL TABLE posts_fts USING fts5(
                content,
                content='posts',
                content_rowid='id'
            );
            CREATE TABLE signal_feedback (
                id INTEGER PRIMARY KEY,
                post_id INTEGER NOT NULL,
                feedback TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            );
            CREATE TABLE personal_memory_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id TEXT NOT NULL,
                object_type TEXT NOT NULL,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT,
                rationale TEXT,
                source_refs_json TEXT NOT NULL DEFAULT '[]',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                proposal_id TEXT NOT NULL DEFAULT 'p',
                rollback_of_event_id INTEGER,
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL DEFAULT 'test',
                confirmation_token_hash TEXT NOT NULL DEFAULT 'h',
                confirmation_receipt_json TEXT NOT NULL DEFAULT '{}'
            );
            """
        )
        for index in range(1, count + 1):
            content = (
                f"Agent reliability evaluation case {index} discusses retrieval quality, "
                f"claim citations, project actions, benchmark holdout strategy, and source evidence."
            )
            connection.execute(
                "INSERT INTO raw_posts(id, channel_username, channel_id, message_id, posted_at, message_url) VALUES (?, ?, ?, ?, ?, ?)",
                (index + 1000, "@eval", -100, index, f"2026-08-{(index % 9) + 1:02d}T10:00:00Z", f"https://t.me/eval/{index}"),
            )
            connection.execute(
                "INSERT INTO posts(id, raw_post_id, channel_username, posted_at, content, language_detected, word_count) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (index, index + 1000, "@eval", f"2026-08-{(index % 9) + 1:02d}T10:00:00Z", content, "en", len(content.split())),
            )
            connection.execute("INSERT INTO posts_fts(rowid, content) VALUES (?, ?)", (index, content))
        connection.execute("INSERT INTO signal_feedback(post_id, feedback, recorded_at) VALUES (1, 'operator_liked', '2026-08-01T11:00:00Z')")


def test_private_generator_writes_gitignored_cases_and_public_manifest(tmp_path):
    db_path = tmp_path / "agent.db"
    cases_path = tmp_path / "private" / "cases.jsonl"
    manifest_path = tmp_path / "manifest.json"
    _seed_archive(db_path)

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "prm_qa_generate_private_eval.py"),
            "--db",
            str(db_path),
            "--out",
            str(cases_path),
            "--public-manifest",
            str(manifest_path),
            "--min-cases",
            "150",
        ],
        cwd=ROOT,
        check=True,
    )

    manifest = json.loads(manifest_path.read_text())
    first_case = json.loads(cases_path.read_text().splitlines()[0])

    assert manifest["case_count"] >= 150
    assert manifest["privacy"]["manifest_contains_queries"] is False
    assert first_case["privacy"]["commit_allowed"] is False
    assert "query" in first_case


def test_prm_qa_eval_public_report_has_no_private_queries(tmp_path):
    db_path = tmp_path / "agent.db"
    cases_path = tmp_path / "private" / "cases.jsonl"
    manifest_path = tmp_path / "manifest.json"
    report_path = tmp_path / "report.json"
    _seed_archive(db_path)
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "prm_qa_generate_private_eval.py"),
            "--db",
            str(db_path),
            "--out",
            str(cases_path),
            "--public-manifest",
            str(manifest_path),
        ],
        cwd=ROOT,
        check=True,
    )

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "prm_qa_eval.py"),
            "--db",
            str(db_path),
            "--cases",
            str(cases_path),
            "--vector-index",
            str(tmp_path / "missing-vector.sqlite"),
            "--public-report",
            str(report_path),
            "--check",
            "presentation",
        ],
        cwd=ROOT,
        check=True,
    )

    report = json.loads(report_path.read_text())

    assert report["privacy"]["public_report_contains_queries"] is False
    assert report["retrieval"]["R0_sqlite_fts_strict_or_baseline"]["available"] is True
    assert report["retrieval_by_job_type"]["R0_sqlite_fts_strict_or_baseline"]
    assert "semantic_topic" in report["retrieval_by_job_type"]["R0_sqlite_fts_strict_or_baseline"]
    assert report["dense_candidate"]["adopted"] is False


def test_private_generator_v2_uses_leak_checked_pairwise_silver_labels(tmp_path):
    db_path = tmp_path / "agent.db"
    cases_path = tmp_path / "private" / "cases.v2.jsonl"
    manifest_path = tmp_path / "manifest.v2.json"
    _seed_archive(db_path)

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "prm_qa_generate_private_eval_v2.py"),
            "--db",
            str(db_path),
            "--out",
            str(cases_path),
            "--public-manifest",
            str(manifest_path),
            "--min-cases",
            "60",
        ],
        cwd=ROOT,
        check=True,
    )

    manifest = json.loads(manifest_path.read_text())
    rows = [json.loads(line) for line in cases_path.read_text().splitlines() if line.strip()]
    labelled = next(row for row in rows if row["relevance_labels"])

    assert manifest["schema_version"] == "prm_qa_dataset_manifest.v2"
    assert manifest["methodology"]["query_generator_independent_from_relevance_reviewer"] is True
    assert labelled["schema_version"] == "prm_qa.case.v2"
    assert labelled["query_generation"]["leak_check"]["passed"] is True
    assert labelled["query_generation"]["input"] == "semantic_summary_without_names_or_rare_terms"
    assert labelled["relevance_labels"][0]["reviewer_role"] == "pairwise_relevance_reviewer"
    assert labelled["relevance_labels"][0]["reviewer_independent_of_query_generator"] is True
    assert "Agent reliability evaluation case" not in labelled["query"]
    assert labelled["privacy"]["contains_raw_telegram_body"] is False


def test_prm_qa_eval_v2_runs_real_runtime_route_without_public_queries(tmp_path):
    db_path = tmp_path / "agent.db"
    cases_path = tmp_path / "private" / "cases.v2.jsonl"
    manifest_path = tmp_path / "manifest.v2.json"
    report_path = tmp_path / "report.v2.json"
    _seed_archive(db_path)
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "prm_qa_generate_private_eval_v2.py"),
            "--db",
            str(db_path),
            "--out",
            str(cases_path),
            "--public-manifest",
            str(manifest_path),
            "--min-cases",
            "60",
        ],
        cwd=ROOT,
        check=True,
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "prm_qa_eval_v2.py"),
            "--db",
            str(db_path),
            "--cases",
            str(cases_path),
            "--public-report",
            str(report_path),
            "--case-limit",
            "6",
        ],
        cwd=ROOT,
        check=False,
    )

    assert completed.returncode in {0, 1}
    report = json.loads(report_path.read_text())

    assert report["schema_version"] == "prm_qa_eval_report.v2"
    assert report["privacy"]["public_report_contains_queries"] is False
    assert report["privacy"]["telegram_messages_sent"] is False
    assert report["routing"]["operator_context_rate"] == 1.0
    assert report["final_answer_verification"]["evaluated_cases"] == 6
    assert all("case_id_hash" in item and "query" not in item for item in report["cases"])

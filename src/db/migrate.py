import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = "data/agent.db"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def get_db_path() -> Path:
    raw_path = os.environ.get("AGENT_DB_PATH", DEFAULT_DB_PATH)
    path = Path(raw_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def run_migrations() -> Path:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    LOGGER.info("Running database migrations against %s", db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.execute("PRAGMA journal_mode = WAL;")
        connection.executescript(schema_sql)
        for stmt in [
            "ALTER TABLE projects ADD COLUMN github_repo TEXT",
            "ALTER TABLE projects ADD COLUMN last_commit_at TEXT",
            "ALTER TABLE projects ADD COLUMN github_synced_at TEXT",
        ]:
            try:
                connection.execute(stmt)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        try:
            connection.execute("ALTER TABLE raw_posts ADD COLUMN message_url TEXT")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
        try:
            connection.execute("ALTER TABLE raw_posts ADD COLUMN image_description TEXT")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
        try:
            connection.execute("ALTER TABLE digests ADD COLUMN content_json TEXT")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
        for stmt in [
            "ALTER TABLE digests ADD COLUMN telegraph_url TEXT",
            "ALTER TABLE digests ADD COLUMN telegram_sent_at TEXT",
            "ALTER TABLE recommendations ADD COLUMN telegraph_url TEXT",
            "ALTER TABLE recommendations ADD COLUMN telegram_sent_at TEXT",
        ]:
            try:
                connection.execute(stmt)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        try:
            connection.execute("ALTER TABLE digests ADD COLUMN pdf_path TEXT")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model TEXT NOT NULL,
                task_type TEXT,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                est_cost_usd REAL NOT NULL DEFAULT 0.0,
                called_at TEXT NOT NULL,
                category TEXT,
                cost_usd REAL NOT NULL DEFAULT 0.0,
                duration_ms INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        for stmt in [
            "ALTER TABLE llm_usage ADD COLUMN task_type TEXT",
            "ALTER TABLE llm_usage ADD COLUMN est_cost_usd REAL NOT NULL DEFAULT 0.0",
            "ALTER TABLE llm_usage ADD COLUMN category TEXT",
            "ALTER TABLE llm_usage ADD COLUMN cost_usd REAL NOT NULL DEFAULT 0.0",
            "ALTER TABLE llm_usage ADD COLUMN duration_ms INTEGER NOT NULL DEFAULT 0",
        ]:
            try:
                connection.execute(stmt)
            except sqlite3.OperationalError:
                pass
        connection.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_llm_usage_called_at ON llm_usage(called_at);
            CREATE INDEX IF NOT EXISTS idx_llm_usage_category ON llm_usage(category);
            CREATE INDEX IF NOT EXISTS idx_llm_usage_task_type ON llm_usage(task_type);
            """
        )
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS study_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_label TEXT NOT NULL UNIQUE,
                generated_at TEXT NOT NULL,
                content_md TEXT NOT NULL,
                topics_covered TEXT,
                reminder_sent_tue INTEGER NOT NULL DEFAULT 0,
                reminder_sent_fri INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        for stmt in [
            "ALTER TABLE study_plans ADD COLUMN reminder_sent_at TEXT",
            "ALTER TABLE study_plans ADD COLUMN completed_at TEXT",
            "ALTER TABLE study_plans ADD COLUMN completion_notes TEXT",
        ]:
            try:
                connection.execute(stmt)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS cluster_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at TEXT NOT NULL,
                post_count INTEGER NOT NULL DEFAULT 0,
                cluster_count INTEGER NOT NULL DEFAULT 0,
                unlabeled_count INTEGER NOT NULL DEFAULT 0,
                inertia REAL,
                silhouette_score REAL
            );
            """
        )
        # Phase 1: scoring columns on posts
        for stmt in [
            "ALTER TABLE posts ADD COLUMN signal_score REAL",
            "ALTER TABLE posts ADD COLUMN bucket TEXT",
            "ALTER TABLE posts ADD COLUMN project_matches TEXT",
            "ALTER TABLE posts ADD COLUMN project_relevance_score REAL",
            "ALTER TABLE posts ADD COLUMN interpretation TEXT",
            "ALTER TABLE posts ADD COLUMN score_run_id TEXT",
            "ALTER TABLE posts ADD COLUMN scored_at TEXT",
            "ALTER TABLE posts ADD COLUMN score_breakdown TEXT",
            "ALTER TABLE posts ADD COLUMN routed_model TEXT",
            "ALTER TABLE posts ADD COLUMN user_preference_score REAL",
            "ALTER TABLE posts ADD COLUMN user_adjusted_score REAL",
            "ALTER TABLE posts ADD COLUMN user_override_tag TEXT",
        ]:
            try:
                connection.execute(stmt)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        # Phase 1: post_project_links — add inference tier and rationale columns
        for stmt in [
            "ALTER TABLE post_project_links ADD COLUMN tier TEXT",
            "ALTER TABLE post_project_links ADD COLUMN rationale TEXT",
        ]:
            try:
                connection.execute(stmt)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        # Phase 2: quality metrics for observability (created now, populated in Phase 2)
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS quality_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_label TEXT NOT NULL UNIQUE,
                computed_at TEXT NOT NULL,
                total_posts INTEGER NOT NULL DEFAULT 0,
                strong_count INTEGER NOT NULL DEFAULT 0,
                watch_count INTEGER NOT NULL DEFAULT 0,
                cultural_count INTEGER NOT NULL DEFAULT 0,
                noise_count INTEGER NOT NULL DEFAULT 0,
                avg_signal_score REAL,
                project_match_count INTEGER NOT NULL DEFAULT 0,
                output_word_count INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        # Phase 3v3: feedback loop
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS signal_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                feedback TEXT NOT NULL CHECK(feedback IN ('acted_on', 'skipped', 'marked_important')),
                recorded_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_signal_feedback_post_id ON signal_feedback(post_id);
            CREATE INDEX IF NOT EXISTS idx_signal_feedback_feedback ON signal_feedback(feedback);
            """
        )
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS user_post_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                tag TEXT NOT NULL CHECK(tag IN (
                    'strong',
                    'interesting',
                    'try_in_project',
                    'funny',
                    'low_signal',
                    'read_later'
                )),
                note TEXT,
                recorded_at TEXT NOT NULL,
                UNIQUE(post_id, tag),
                FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_user_post_tags_post_id ON user_post_tags(post_id);
            CREATE INDEX IF NOT EXISTS idx_user_post_tags_tag ON user_post_tags(tag);
            """
        )
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS channel_memory (
                channel_username TEXT PRIMARY KEY,
                summary TEXT NOT NULL DEFAULT '',
                positive_tags INTEGER NOT NULL DEFAULT 0,
                negative_tags INTEGER NOT NULL DEFAULT 0,
                strong_tags INTEGER NOT NULL DEFAULT 0,
                try_tags INTEGER NOT NULL DEFAULT 0,
                interesting_tags INTEGER NOT NULL DEFAULT 0,
                funny_tags INTEGER NOT NULL DEFAULT 0,
                low_signal_tags INTEGER NOT NULL DEFAULT 0,
                read_later_tags INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS project_context_snapshots (
                project_id INTEGER PRIMARY KEY,
                project_name TEXT NOT NULL,
                github_repo TEXT,
                source_commit_at TEXT,
                summary TEXT NOT NULL DEFAULT '',
                open_questions TEXT NOT NULL DEFAULT '',
                recent_changes TEXT NOT NULL DEFAULT '',
                context_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_project_context_snapshots_project_name
                ON project_context_snapshots(project_name);
            CREATE INDEX IF NOT EXISTS idx_project_context_snapshots_updated_at
                ON project_context_snapshots(updated_at);
            """
        )
        # Phase 6v3: insight triage layer
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS insight_triage_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_label TEXT NOT NULL,
                title TEXT NOT NULL,
                idea_type TEXT NOT NULL,
                timing TEXT NOT NULL,
                implementation_mode TEXT NOT NULL,
                confidence TEXT NOT NULL,
                evidence_strength TEXT NOT NULL,
                main_risk TEXT NOT NULL,
                recommendation TEXT NOT NULL
                    CHECK(recommendation IN ('do_now', 'backlog', 'reject_or_defer')),
                reason TEXT NOT NULL,
                source_url TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_insight_triage_week_label
                ON insight_triage_records(week_label);
            CREATE INDEX IF NOT EXISTS idx_insight_triage_recommendation
                ON insight_triage_records(recommendation);
            CREATE TABLE IF NOT EXISTS insight_rejection_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title_fingerprint TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                reason TEXT NOT NULL,
                rejected_at TEXT NOT NULL,
                suppressed_until TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_insight_rejection_memory_fingerprint
                ON insight_rejection_memory(title_fingerprint);
            """
        )
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS signal_evidence_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                raw_post_id INTEGER NOT NULL,
                week_label TEXT NOT NULL,
                evidence_kind TEXT NOT NULL
                    CHECK(evidence_kind IN (
                        'strong_signal',
                        'manual_tag',
                        'project_insight_source',
                        'study_source',
                        'decision_support'
                    )),
                excerpt_text TEXT NOT NULL CHECK(length(trim(excerpt_text)) > 0),
                source_channel TEXT NOT NULL CHECK(length(trim(source_channel)) > 0),
                message_url TEXT,
                posted_at TEXT NOT NULL CHECK(length(trim(posted_at)) > 0),
                topic_labels_json TEXT NOT NULL DEFAULT '[]',
                project_names_json TEXT NOT NULL DEFAULT '[]',
                selection_reason TEXT NOT NULL CHECK(length(trim(selection_reason)) > 0),
                last_used_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
                FOREIGN KEY(raw_post_id) REFERENCES raw_posts(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_signal_evidence_items_post_id
                ON signal_evidence_items(post_id);
            CREATE INDEX IF NOT EXISTS idx_signal_evidence_items_week_label
                ON signal_evidence_items(week_label);
            CREATE INDEX IF NOT EXISTS idx_signal_evidence_items_evidence_kind
                ON signal_evidence_items(evidence_kind);
            CREATE INDEX IF NOT EXISTS idx_signal_evidence_items_source_channel
                ON signal_evidence_items(source_channel);
            CREATE TABLE IF NOT EXISTS decision_journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_scope TEXT NOT NULL
                    CHECK(decision_scope IN ('signal', 'insight', 'study', 'project')),
                subject_ref_type TEXT NOT NULL,
                subject_ref_id TEXT NOT NULL,
                project_name TEXT,
                status TEXT NOT NULL
                    CHECK(status IN ('acted_on', 'ignored', 'deferred', 'rejected', 'completed')),
                reason TEXT,
                evidence_item_ids_json TEXT NOT NULL DEFAULT '[]',
                recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                recorded_by TEXT NOT NULL DEFAULT 'pipeline'
            );
            CREATE INDEX IF NOT EXISTS idx_decision_journal_decision_scope
                ON decision_journal(decision_scope);
            CREATE INDEX IF NOT EXISTS idx_decision_journal_project_name
                ON decision_journal(project_name);
            CREATE INDEX IF NOT EXISTS idx_decision_journal_status
                ON decision_journal(status);
            CREATE INDEX IF NOT EXISTS idx_decision_journal_recorded_at
                ON decision_journal(recorded_at);
            """
        )
        connection.executescript(
            """
            DROP TABLE IF EXISTS decision_journal;
            CREATE TABLE decision_journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_scope TEXT NOT NULL
                    CHECK(decision_scope IN ('signal', 'insight', 'study', 'project')),
                subject_ref_type TEXT NOT NULL,
                subject_ref_id TEXT NOT NULL,
                project_name TEXT,
                status TEXT NOT NULL
                    CHECK(status IN ('acted_on', 'ignored', 'deferred', 'rejected', 'completed')),
                reason TEXT,
                evidence_item_ids_json TEXT NOT NULL DEFAULT '[]',
                recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                recorded_by TEXT NOT NULL DEFAULT 'pipeline'
            );
            CREATE INDEX IF NOT EXISTS idx_decision_journal_decision_scope
                ON decision_journal(decision_scope);
            CREATE INDEX IF NOT EXISTS idx_decision_journal_project_name
                ON decision_journal(project_name);
            CREATE INDEX IF NOT EXISTS idx_decision_journal_status
                ON decision_journal(status);
            CREATE INDEX IF NOT EXISTS idx_decision_journal_recorded_at
                ON decision_journal(recorded_at);
            """
        )
        for stmt in [
            "ALTER TABLE project_context_snapshots ADD COLUMN linked_signal_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE project_context_snapshots ADD COLUMN snapshot_week_label TEXT",
        ]:
            try:
                connection.execute(stmt)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        connection.commit()

    LOGGER.info("Database migrations complete")
    return db_path


def record_feedback(connection: sqlite3.Connection, post_id: int, feedback: str) -> None:
    recorded_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    connection.execute(
        "INSERT INTO signal_feedback (post_id, feedback, recorded_at) VALUES (?, ?, ?)",
        (post_id, feedback, recorded_at),
    )
    connection.commit()


def record_post_tag(connection: sqlite3.Connection, post_id: int, tag: str, note: str | None = None) -> None:
    recorded_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    connection.execute(
        """
        INSERT INTO user_post_tags (post_id, tag, note, recorded_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(post_id, tag) DO UPDATE SET
            note = excluded.note,
            recorded_at = excluded.recorded_at
        """,
        (post_id, tag, note, recorded_at),
    )
    connection.commit()


def record_study_completion(
    connection: sqlite3.Connection,
    week_label: str,
    notes: str | None = None,
) -> None:
    completed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    existing = connection.execute(
        """
        SELECT id
        FROM study_plans
        WHERE week_label = ?
        """,
        (week_label,),
    ).fetchone()
    if existing is None:
        connection.execute(
            """
            INSERT INTO study_plans (
                week_label,
                generated_at,
                content_md,
                topics_covered,
                completed_at,
                completion_notes
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (week_label, completed_at, "", "[]", completed_at, notes),
        )
    else:
        connection.execute(
            """
            UPDATE study_plans
            SET completed_at = ?, completion_notes = ?
            WHERE week_label = ?
            """,
            (completed_at, notes, week_label),
        )
    connection.commit()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run_migrations()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

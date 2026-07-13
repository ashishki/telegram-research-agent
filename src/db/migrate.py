import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

try:
    from db.evidence import (
        record_decision_for_feedback,
        record_signal_evidence_for_manual_tag,
        record_study_completion_decision,
    )
except ModuleNotFoundError:
    from src.db.evidence import (
        record_decision_for_feedback,
        record_signal_evidence_for_manual_tag,
        record_study_completion_decision,
    )


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = "data/agent.db"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _verify_canonical_idea_thread_schema(connection: sqlite3.Connection) -> None:
    """Fail deterministically if an old partial IRX-4 schema is encountered."""

    required_columns = {
        "canonical_idea_threads": {
            "canonical_thread_id",
            "stable_slug",
            "title_ru",
            "title_en",
            "thesis",
            "status",
            "first_seen_at",
            "last_seen_at",
            "evidence_maturity",
            "operator_interest",
            "entities_json",
            "curator_version",
            "current_version",
        },
        "canonical_idea_thread_versions": {
            "canonical_thread_id",
            "version",
            "operation",
            "decision_id",
            "valid_from",
            "valid_to",
        },
        "canonical_idea_thread_atom_history": {
            "canonical_thread_id",
            "atom_id",
            "raw_thread_id",
            "valid_from",
            "valid_to",
        },
        "canonical_idea_thread_alias_history": {
            "canonical_thread_id",
            "alias_type",
            "alias_value",
            "normalized_alias",
            "valid_from",
            "valid_to",
        },
        "canonical_idea_thread_lineage": {
            "relation_type",
            "from_thread_id",
            "to_thread_id",
            "event_at",
        },
        "canonical_idea_thread_curator_decisions": {
            "decision_id",
            "run_id",
            "operation",
            "proposal_json",
            "model",
            "model_version",
            "curator_version",
            "reason",
            "validation_status",
            "decision_status",
        },
    }
    for table_name, expected in required_columns.items():
        columns = {
            str(row[1])
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        missing = sorted(expected - columns)
        if missing:
            raise RuntimeError(
                f"incompatible partial {table_name} schema; missing columns: "
                + ", ".join(missing)
            )


def get_db_path() -> Path:
    raw_path = os.environ.get("AGENT_DB_PATH", DEFAULT_DB_PATH)
    path = Path(raw_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _ensure_artifact_feedback_mvp_type(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table' AND name = 'artifact_feedback_logs'
        LIMIT 1
        """
    ).fetchone()
    table_sql = str(row[0] if row else "")
    if not table_sql or "mvp_weekly" in table_sql:
        return

    LOGGER.info("Rebuilding artifact_feedback_logs to allow mvp_weekly artifact type")
    connection.executescript(
        """
        ALTER TABLE artifact_feedback_logs RENAME TO artifact_feedback_logs_old;
        CREATE TABLE artifact_feedback_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_label TEXT NOT NULL CHECK(length(trim(week_label)) > 0),
            artifact_type TEXT NOT NULL DEFAULT 'research_brief'
                CHECK(artifact_type IN (
                    'research_brief',
                    'implementation_ideas',
                    'mvp_weekly',
                    'study_plan',
                    'channel_intelligence',
                    'other'
                )),
            artifact_path TEXT,
            digest_id INTEGER,
            section TEXT,
            item_ref TEXT,
            feedback TEXT NOT NULL
                CHECK(feedback IN ('useful', 'weak', 'noisy', 'decision_impacting')),
            source_evidence_item_ids_json TEXT NOT NULL DEFAULT '[]'
                CHECK(json_valid(source_evidence_item_ids_json)),
            notes TEXT,
            recorded_at TEXT NOT NULL,
            recorded_by TEXT NOT NULL DEFAULT 'operator',
            FOREIGN KEY(digest_id) REFERENCES digests(id) ON DELETE SET NULL
        );
        INSERT INTO artifact_feedback_logs (
            id,
            week_label,
            artifact_type,
            artifact_path,
            digest_id,
            section,
            item_ref,
            feedback,
            source_evidence_item_ids_json,
            notes,
            recorded_at,
            recorded_by
        )
        SELECT
            id,
            week_label,
            artifact_type,
            artifact_path,
            digest_id,
            section,
            item_ref,
            feedback,
            source_evidence_item_ids_json,
            notes,
            recorded_at,
            recorded_by
        FROM artifact_feedback_logs_old;
        DROP TABLE artifact_feedback_logs_old;
        CREATE INDEX IF NOT EXISTS idx_artifact_feedback_week_label
            ON artifact_feedback_logs(week_label);
        CREATE INDEX IF NOT EXISTS idx_artifact_feedback_artifact_type
            ON artifact_feedback_logs(artifact_type);
        CREATE INDEX IF NOT EXISTS idx_artifact_feedback_feedback
            ON artifact_feedback_logs(feedback);
        CREATE INDEX IF NOT EXISTS idx_artifact_feedback_digest_id
            ON artifact_feedback_logs(digest_id);
        CREATE INDEX IF NOT EXISTS idx_artifact_feedback_recorded_at
            ON artifact_feedback_logs(recorded_at);
        """
    )


def _ensure_ai_report_feedback_contract_types(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table' AND name = 'ai_report_feedback_events'
        LIMIT 1
        """
    ).fetchone()
    table_sql = str(row[0] if row else "")
    required_tokens = (
        "'no_missed_posts'",
        "'trust_too_high'",
        "'trust_too_low'",
        "'verify_first'",
        "'correction'",
        "'retraction'",
        "'accidental_feedback'",
        "'missed_post'",
        "'trust_correction'",
        "'feedback_event'",
        "'operator_context'",
    )
    if not table_sql or all(token in table_sql for token in required_tokens):
        return

    LOGGER.info("Rebuilding ai_report_feedback_events to allow KIR-Q feedback contract types")
    connection.executescript(
        """
        ALTER TABLE ai_report_feedback_events RENAME TO ai_report_feedback_events_old;
        CREATE TABLE ai_report_feedback_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_label TEXT NOT NULL CHECK(length(trim(week_label)) > 0),
            report_path TEXT,
            feedback_type TEXT NOT NULL
                CHECK(feedback_type IN (
                    'read',
                    'useful',
                    'tried',
                    'applied_to_project',
                    'too_shallow',
                    'missed_important_post',
                    'no_missed_posts',
                    'wrong_priority',
                    'not_interested',
                    'noise',
                    'trust_too_high',
                    'trust_too_low',
                    'verify_first',
                    'correction',
                    'retraction',
                    'accidental_feedback'
                )),
            target_type TEXT NOT NULL DEFAULT 'report'
                CHECK(target_type IN (
                    'report',
                    'report_section',
                    'idea_thread',
                    'knowledge_atom',
                    'source_channel',
                    'read_queue',
                    'experiment',
                    'action',
                    'missed_post',
                    'trust_correction',
                    'feedback_event',
                    'operator_context'
                )),
            target_ref TEXT,
            source_url TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            recorded_by TEXT NOT NULL DEFAULT 'operator'
        );
        INSERT INTO ai_report_feedback_events (
            id,
            week_label,
            report_path,
            feedback_type,
            target_type,
            target_ref,
            source_url,
            notes,
            created_at,
            recorded_by
        )
        SELECT
            id,
            week_label,
            report_path,
            feedback_type,
            target_type,
            target_ref,
            source_url,
            notes,
            created_at,
            recorded_by
        FROM ai_report_feedback_events_old;
        DROP TABLE ai_report_feedback_events_old;
        CREATE INDEX IF NOT EXISTS idx_ai_report_feedback_week
            ON ai_report_feedback_events(week_label);
        CREATE INDEX IF NOT EXISTS idx_ai_report_feedback_type
            ON ai_report_feedback_events(feedback_type);
        CREATE INDEX IF NOT EXISTS idx_ai_report_feedback_target
            ON ai_report_feedback_events(target_type, target_ref);
        CREATE INDEX IF NOT EXISTS idx_ai_report_feedback_created
            ON ai_report_feedback_events(created_at);
        """
    )


def _ensure_signal_feedback_operator_interest(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table' AND name = 'signal_feedback'
        LIMIT 1
        """
    ).fetchone()
    table_sql = str(row[0] if row else "")
    if not table_sql or "operator_marked_interesting" in table_sql:
        return

    LOGGER.info("Rebuilding signal_feedback to allow operator_marked_interesting feedback")
    connection.executescript(
        """
        ALTER TABLE signal_feedback RENAME TO signal_feedback_old;
        CREATE TABLE signal_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            feedback TEXT NOT NULL CHECK(feedback IN (
                'acted_on',
                'skipped',
                'marked_important',
                'operator_marked_interesting'
            )),
            recorded_at TEXT NOT NULL
        );
        INSERT INTO signal_feedback (
            id,
            post_id,
            feedback,
            recorded_at
        )
        SELECT
            id,
            post_id,
            feedback,
            recorded_at
        FROM signal_feedback_old;
        DROP TABLE signal_feedback_old;
        CREATE INDEX IF NOT EXISTS idx_signal_feedback_post_id ON signal_feedback(post_id);
        CREATE INDEX IF NOT EXISTS idx_signal_feedback_feedback ON signal_feedback(feedback);
        """
    )


def _ensure_operator_reminders_daily_contract(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table' AND name = 'operator_reminders'
        LIMIT 1
        """
    ).fetchone()
    table_sql = str(row[0] if row else "")
    if not table_sql:
        return
    if all(token in table_sql for token in ("'done'", "'not_done'", "last_prompted_at")):
        return

    column_rows = connection.execute("PRAGMA table_info(operator_reminders)").fetchall()
    columns = {str(column[1]) for column in column_rows}

    LOGGER.info("Rebuilding operator_reminders for daily digest outcome tracking")
    connection.execute("ALTER TABLE operator_reminders RENAME TO operator_reminders_old")
    connection.executescript(
        """
        CREATE TABLE operator_reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            due_at TEXT NOT NULL,
            text TEXT NOT NULL CHECK(length(trim(text)) > 0),
            reminder_type TEXT NOT NULL DEFAULT 'general'
                CHECK(reminder_type IN ('general', 'feedback', 'action', 'read_watch', 'project', 'mvp')),
            source_text TEXT,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending', 'done', 'not_done', 'canceled')),
            created_at TEXT NOT NULL,
            last_prompted_at TEXT,
            completed_at TEXT,
            not_done_at TEXT,
            canceled_at TEXT,
            recorded_by TEXT NOT NULL DEFAULT 'operator'
        );
        """
    )

    def _column(name: str, fallback: str) -> str:
        return name if name in columns else fallback

    last_prompted_expr = _column("last_prompted_at", _column("sent_at", "NULL"))
    completed_expr = _column("completed_at", "NULL")
    not_done_expr = _column("not_done_at", "NULL")
    canceled_expr = _column("canceled_at", "NULL")
    source_text_expr = _column("source_text", "NULL")
    recorded_by_expr = _column("recorded_by", "'operator'")

    connection.execute(
        f"""
        INSERT INTO operator_reminders (
            id,
            due_at,
            text,
            reminder_type,
            source_text,
            status,
            created_at,
            last_prompted_at,
            completed_at,
            not_done_at,
            canceled_at,
            recorded_by
        )
        SELECT
            id,
            due_at,
            text,
            reminder_type,
            {source_text_expr},
            CASE
                WHEN status = 'sent' THEN 'pending'
                WHEN status IN ('pending', 'done', 'not_done', 'canceled') THEN status
                ELSE 'pending'
            END,
            created_at,
            {last_prompted_expr},
            {completed_expr},
            {not_done_expr},
            {canceled_expr},
            {recorded_by_expr}
        FROM operator_reminders_old
        """
    )
    connection.execute("DROP TABLE operator_reminders_old")
    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_operator_reminders_due
            ON operator_reminders(status, due_at);
        CREATE INDEX IF NOT EXISTS idx_operator_reminders_prompted
            ON operator_reminders(status, last_prompted_at);
        CREATE INDEX IF NOT EXISTS idx_operator_reminders_created
            ON operator_reminders(created_at);
        """
    )


def run_migrations() -> Path:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    LOGGER.info("Running database migrations against %s", db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.execute("PRAGMA journal_mode = WAL;")
        connection.executescript(schema_sql)
        _verify_canonical_idea_thread_schema(connection)
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS reaction_sync_state (
                source TEXT NOT NULL,
                channel_username TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                emoji TEXT NOT NULL,
                action_key TEXT NOT NULL,
                applied_at TEXT NOT NULL,
                PRIMARY KEY(source, channel_username, message_id, emoji, action_key)
            );
            CREATE INDEX IF NOT EXISTS idx_reaction_sync_state_message
                ON reaction_sync_state(channel_username, message_id);
            """
        )
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
            CREATE TABLE IF NOT EXISTS knowledge_extraction_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_key TEXT NOT NULL UNIQUE CHECK(length(trim(batch_key)) > 0),
                started_at TEXT NOT NULL,
                completed_at TEXT,
                week_label TEXT NOT NULL CHECK(length(trim(week_label)) > 0),
                channel_username TEXT,
                post_count INTEGER NOT NULL DEFAULT 0 CHECK(post_count >= 0),
                model TEXT NOT NULL CHECK(length(trim(model)) > 0),
                prompt_version TEXT NOT NULL DEFAULT 'unversioned' CHECK(length(trim(prompt_version)) > 0),
                status TEXT NOT NULL DEFAULT 'running'
                    CHECK(status IN ('running', 'completed', 'failed', 'partial')),
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_knowledge_batches_week
                ON knowledge_extraction_batches(week_label);
            CREATE INDEX IF NOT EXISTS idx_knowledge_batches_channel
                ON knowledge_extraction_batches(channel_username);
            CREATE INDEX IF NOT EXISTS idx_knowledge_batches_status
                ON knowledge_extraction_batches(status);
            CREATE INDEX IF NOT EXISTS idx_knowledge_batches_started
                ON knowledge_extraction_batches(started_at);

            CREATE TABLE IF NOT EXISTS knowledge_atoms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                atom_key TEXT NOT NULL UNIQUE CHECK(length(trim(atom_key)) > 0),
                extraction_batch_id INTEGER,
                week_label TEXT,
                atom_type TEXT NOT NULL CHECK(atom_type IN (
                    'tool_release',
                    'model_update',
                    'workflow_pattern',
                    'engineering_practice',
                    'benchmark_claim',
                    'market_signal',
                    'risk_warning',
                    'case_study',
                    'tutorial_resource',
                    'opinion_shift',
                    'research_claim',
                    'pricing_or_limit_change',
                    'regulatory_or_access_change'
                )),
                claim TEXT NOT NULL CHECK(length(trim(claim)) > 0),
                summary TEXT NOT NULL DEFAULT '',
                evidence_quote TEXT NOT NULL CHECK(length(trim(evidence_quote)) > 0),
                source_post_ids_json TEXT NOT NULL
                    CHECK(json_valid(source_post_ids_json)
                          AND json_type(source_post_ids_json) = 'array'
                          AND json_array_length(source_post_ids_json) > 0),
                source_urls_json TEXT NOT NULL
                    CHECK(json_valid(source_urls_json)
                          AND json_type(source_urls_json) = 'array'
                          AND json_array_length(source_urls_json) > 0),
                entities_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(entities_json) AND json_type(entities_json) = 'array'),
                tools_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(tools_json) AND json_type(tools_json) = 'array'),
                models_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(models_json) AND json_type(models_json) = 'array'),
                practices_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(practices_json) AND json_type(practices_json) = 'array'),
                confidence REAL NOT NULL DEFAULT 0.0 CHECK(confidence >= 0.0 AND confidence <= 1.0),
                novelty_score REAL NOT NULL DEFAULT 0.0 CHECK(novelty_score >= 0.0 AND novelty_score <= 1.0),
                practical_utility_score REAL NOT NULL DEFAULT 0.0
                    CHECK(practical_utility_score >= 0.0 AND practical_utility_score <= 1.0),
                frontier_relevance_score REAL NOT NULL DEFAULT 0.0
                    CHECK(frontier_relevance_score >= 0.0 AND frontier_relevance_score <= 1.0),
                operator_relevance_score REAL NOT NULL DEFAULT 0.0
                    CHECK(operator_relevance_score >= 0.0 AND operator_relevance_score <= 1.0),
                staleness_status TEXT NOT NULL DEFAULT 'active'
                    CHECK(staleness_status IN (
                        'fresh',
                        'active',
                        'watch',
                        'stale',
                        'superseded',
                        'resolved',
                        'hype_only',
                        'unknown'
                    )),
                why_it_matters TEXT NOT NULL DEFAULT '',
                expiry_hint TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(extraction_batch_id) REFERENCES knowledge_extraction_batches(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_knowledge_atoms_batch
                ON knowledge_atoms(extraction_batch_id);
            CREATE INDEX IF NOT EXISTS idx_knowledge_atoms_week
                ON knowledge_atoms(week_label);
            CREATE INDEX IF NOT EXISTS idx_knowledge_atoms_type
                ON knowledge_atoms(atom_type);
            CREATE INDEX IF NOT EXISTS idx_knowledge_atoms_staleness
                ON knowledge_atoms(staleness_status);
            CREATE INDEX IF NOT EXISTS idx_knowledge_atoms_first_seen
                ON knowledge_atoms(first_seen_at);
            CREATE INDEX IF NOT EXISTS idx_knowledge_atoms_last_seen
                ON knowledge_atoms(last_seen_at);
            """
        )
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS idea_threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL CHECK(length(trim(title)) > 0),
                slug TEXT NOT NULL UNIQUE CHECK(length(trim(slug)) > 0),
                summary TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active'
                    CHECK(status IN (
                        'active',
                        'stale',
                        'superseded',
                        'resolved',
                        'hype_only',
                        'production_pattern'
                    )),
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                momentum_7d REAL NOT NULL DEFAULT 0.0 CHECK(momentum_7d >= 0.0 AND momentum_7d <= 1.0),
                momentum_30d REAL NOT NULL DEFAULT 0.0 CHECK(momentum_30d >= 0.0 AND momentum_30d <= 1.0),
                momentum_90d REAL NOT NULL DEFAULT 0.0 CHECK(momentum_90d >= 0.0 AND momentum_90d <= 1.0),
                atom_count INTEGER NOT NULL DEFAULT 0 CHECK(atom_count >= 0),
                source_channel_count INTEGER NOT NULL DEFAULT 0 CHECK(source_channel_count >= 0),
                source_channels_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(source_channels_json) AND json_type(source_channels_json) = 'array'),
                key_entities_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(key_entities_json) AND json_type(key_entities_json) = 'array'),
                current_claims_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(current_claims_json) AND json_type(current_claims_json) = 'array'),
                superseded_claims_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(superseded_claims_json) AND json_type(superseded_claims_json) = 'array'),
                contradictions_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(contradictions_json) AND json_type(contradictions_json) = 'array'),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_idea_threads_slug
                ON idea_threads(slug);
            CREATE INDEX IF NOT EXISTS idx_idea_threads_status
                ON idea_threads(status);
            CREATE INDEX IF NOT EXISTS idx_idea_threads_last_seen
                ON idea_threads(last_seen_at);
            CREATE INDEX IF NOT EXISTS idx_idea_threads_momentum_30d
                ON idea_threads(momentum_30d);

            CREATE TABLE IF NOT EXISTS idea_thread_atoms (
                thread_id INTEGER NOT NULL,
                atom_id INTEGER NOT NULL,
                relation TEXT NOT NULL DEFAULT 'supports'
                    CHECK(relation IN ('supports', 'contradicts', 'supersedes', 'related')),
                created_at TEXT NOT NULL,
                PRIMARY KEY(thread_id, atom_id),
                FOREIGN KEY(thread_id) REFERENCES idea_threads(id) ON DELETE CASCADE,
                FOREIGN KEY(atom_id) REFERENCES knowledge_atoms(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_idea_thread_atoms_atom
                ON idea_thread_atoms(atom_id);
            CREATE INDEX IF NOT EXISTS idx_idea_thread_atoms_relation
                ON idea_thread_atoms(relation);
            """
        )
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS frontier_analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_label TEXT NOT NULL UNIQUE CHECK(length(trim(week_label)) > 0),
                generated_at TEXT NOT NULL,
                model TEXT NOT NULL CHECK(length(trim(model)) > 0),
                prompt_version TEXT NOT NULL CHECK(length(trim(prompt_version)) > 0),
                lookback_weeks INTEGER NOT NULL DEFAULT 12 CHECK(lookback_weeks >= 1),
                threads_analyzed INTEGER NOT NULL DEFAULT 0 CHECK(threads_analyzed >= 0),
                atoms_analyzed INTEGER NOT NULL DEFAULT 0 CHECK(atoms_analyzed >= 0),
                executive_brief TEXT NOT NULL DEFAULT '',
                what_changed_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(what_changed_json) AND json_type(what_changed_json) = 'array'),
                trend_narratives_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(trend_narratives_json) AND json_type(trend_narratives_json) = 'array'),
                study_now_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(study_now_json) AND json_type(study_now_json) = 'array'),
                actions_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(actions_json) AND json_type(actions_json) = 'array'),
                caveats_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(caveats_json) AND json_type(caveats_json) = 'array'),
                analysis_json TEXT NOT NULL CHECK(json_valid(analysis_json)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_frontier_analyses_week
                ON frontier_analyses(week_label);
            CREATE INDEX IF NOT EXISTS idx_frontier_analyses_generated
                ON frontier_analyses(generated_at);
            """
        )
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS ai_report_feedback_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_label TEXT NOT NULL CHECK(length(trim(week_label)) > 0),
                report_path TEXT,
                feedback_type TEXT NOT NULL
                    CHECK(feedback_type IN (
                        'read',
                        'useful',
                        'tried',
                        'applied_to_project',
                        'too_shallow',
                        'missed_important_post',
                        'no_missed_posts',
                        'wrong_priority',
                        'not_interested',
                        'noise',
                        'trust_too_high',
                        'trust_too_low',
                        'verify_first',
                        'correction',
                        'retraction',
                        'accidental_feedback'
                    )),
                target_type TEXT NOT NULL DEFAULT 'report'
                    CHECK(target_type IN (
                        'report',
                        'report_section',
                        'idea_thread',
                        'knowledge_atom',
                        'source_channel',
                        'read_queue',
                        'experiment',
                        'action',
                        'missed_post',
                        'trust_correction',
                        'feedback_event',
                        'operator_context'
                    )),
                target_ref TEXT,
                source_url TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                recorded_by TEXT NOT NULL DEFAULT 'operator'
            );
            CREATE INDEX IF NOT EXISTS idx_ai_report_feedback_week
                ON ai_report_feedback_events(week_label);
            CREATE INDEX IF NOT EXISTS idx_ai_report_feedback_type
                ON ai_report_feedback_events(feedback_type);
            CREATE INDEX IF NOT EXISTS idx_ai_report_feedback_target
                ON ai_report_feedback_events(target_type, target_ref);
            CREATE INDEX IF NOT EXISTS idx_ai_report_feedback_created
                ON ai_report_feedback_events(created_at);

            CREATE TABLE IF NOT EXISTS ai_report_feedback_intakes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_label TEXT NOT NULL CHECK(length(trim(week_label)) > 0),
                report_path TEXT,
                input_kind TEXT NOT NULL CHECK(input_kind IN ('text', 'voice_transcript')),
                raw_text TEXT NOT NULL CHECK(length(trim(raw_text)) > 0),
                transcript_text TEXT,
                proposals_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(proposals_json) AND json_type(proposals_json) = 'array'),
                suggestions_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(suggestions_json) AND json_type(suggestions_json) = 'array'),
                confirmation_summary TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending', 'confirmed', 'discarded')),
                created_at TEXT NOT NULL,
                confirmed_at TEXT,
                recorded_by TEXT NOT NULL DEFAULT 'operator'
            );
            CREATE INDEX IF NOT EXISTS idx_ai_report_feedback_intake_week
                ON ai_report_feedback_intakes(week_label);
            CREATE INDEX IF NOT EXISTS idx_ai_report_feedback_intake_status
                ON ai_report_feedback_intakes(status);
            CREATE INDEX IF NOT EXISTS idx_ai_report_feedback_intake_created
                ON ai_report_feedback_intakes(created_at);
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
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS operator_reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                due_at TEXT NOT NULL,
                text TEXT NOT NULL CHECK(length(trim(text)) > 0),
                reminder_type TEXT NOT NULL DEFAULT 'general'
                    CHECK(reminder_type IN ('general', 'feedback', 'action', 'read_watch', 'project', 'mvp')),
                source_text TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending', 'done', 'not_done', 'canceled')),
                created_at TEXT NOT NULL,
                last_prompted_at TEXT,
                completed_at TEXT,
                not_done_at TEXT,
                canceled_at TEXT,
                recorded_by TEXT NOT NULL DEFAULT 'operator'
            );
            CREATE INDEX IF NOT EXISTS idx_operator_reminders_due
                ON operator_reminders(status, due_at);
            CREATE INDEX IF NOT EXISTS idx_operator_reminders_created
                ON operator_reminders(created_at);
            """
        )
        _ensure_operator_reminders_daily_contract(connection)
        connection.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_operator_reminders_due
                ON operator_reminders(status, due_at);
            CREATE INDEX IF NOT EXISTS idx_operator_reminders_prompted
                ON operator_reminders(status, last_prompted_at);
            CREATE INDEX IF NOT EXISTS idx_operator_reminders_created
                ON operator_reminders(created_at);
            """
        )
        for stmt in [
            "ALTER TABLE study_plans ADD COLUMN reminder_sent_at TEXT",
            "ALTER TABLE study_plans ADD COLUMN completed_at TEXT",
            "ALTER TABLE study_plans ADD COLUMN completion_notes TEXT",
            "ALTER TABLE study_plans ADD COLUMN telegraph_url TEXT",
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
                feedback TEXT NOT NULL CHECK(feedback IN (
                    'acted_on',
                    'skipped',
                    'marked_important',
                    'operator_marked_interesting'
                )),
                recorded_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_signal_feedback_post_id ON signal_feedback(post_id);
            CREATE INDEX IF NOT EXISTS idx_signal_feedback_feedback ON signal_feedback(feedback);
            """
        )
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS weekly_usefulness_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_label TEXT NOT NULL CHECK(length(trim(week_label)) > 0),
                useful_sections_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(useful_sections_json)),
                not_useful_sections_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(not_useful_sections_json)),
                decisions_influenced_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(decisions_influenced_json)),
                weak_evidence_notes_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(weak_evidence_notes_json)),
                channels_gaining_trust_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(channels_gaining_trust_json)),
                channels_losing_trust_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(channels_losing_trust_json)),
                notes TEXT,
                recorded_at TEXT NOT NULL,
                recorded_by TEXT NOT NULL DEFAULT 'operator'
            );
            CREATE INDEX IF NOT EXISTS idx_weekly_usefulness_logs_week_label
                ON weekly_usefulness_logs(week_label);
            CREATE INDEX IF NOT EXISTS idx_weekly_usefulness_logs_recorded_at
                ON weekly_usefulness_logs(recorded_at);
            """
        )
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS artifact_feedback_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_label TEXT NOT NULL CHECK(length(trim(week_label)) > 0),
                artifact_type TEXT NOT NULL DEFAULT 'research_brief'
                    CHECK(artifact_type IN (
                        'research_brief',
                        'implementation_ideas',
                        'mvp_weekly',
                        'study_plan',
                        'channel_intelligence',
                        'other'
                    )),
                artifact_path TEXT,
                digest_id INTEGER,
                section TEXT,
                item_ref TEXT,
                feedback TEXT NOT NULL
                    CHECK(feedback IN ('useful', 'weak', 'noisy', 'decision_impacting')),
                source_evidence_item_ids_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(source_evidence_item_ids_json)),
                notes TEXT,
                recorded_at TEXT NOT NULL,
                recorded_by TEXT NOT NULL DEFAULT 'operator',
                FOREIGN KEY(digest_id) REFERENCES digests(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_artifact_feedback_week_label
                ON artifact_feedback_logs(week_label);
            CREATE INDEX IF NOT EXISTS idx_artifact_feedback_artifact_type
                ON artifact_feedback_logs(artifact_type);
            CREATE INDEX IF NOT EXISTS idx_artifact_feedback_feedback
                ON artifact_feedback_logs(feedback);
            CREATE INDEX IF NOT EXISTS idx_artifact_feedback_digest_id
                ON artifact_feedback_logs(digest_id);
            CREATE INDEX IF NOT EXISTS idx_artifact_feedback_recorded_at
                ON artifact_feedback_logs(recorded_at);
            """
        )
        _ensure_artifact_feedback_mvp_type(connection)
        _ensure_ai_report_feedback_contract_types(connection)
        _ensure_signal_feedback_operator_interest(connection)
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_brief_receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receipt_id TEXT NOT NULL UNIQUE,
                type TEXT NOT NULL DEFAULT 'research_brief_receipt'
                    CHECK(type = 'research_brief_receipt'),
                week_label TEXT NOT NULL CHECK(length(trim(week_label)) > 0),
                generated_at TEXT NOT NULL,
                source_project TEXT NOT NULL DEFAULT 'telegram-research-agent',
                source_version TEXT,
                window_start TEXT,
                window_end TEXT,
                included_channels_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(included_channels_json)),
                post_counts_json TEXT NOT NULL DEFAULT '{}'
                    CHECK(json_valid(post_counts_json)),
                source_set_json TEXT NOT NULL DEFAULT '{}'
                    CHECK(json_valid(source_set_json)),
                project_scopes_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(project_scopes_json)),
                topic_scopes_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(topic_scopes_json)),
                llm_provider TEXT,
                llm_model TEXT,
                llm_category TEXT,
                prompt_template_path TEXT,
                prompt_template_version TEXT,
                config_fingerprints_json TEXT NOT NULL DEFAULT '{}'
                    CHECK(json_valid(config_fingerprints_json)),
                generation_params_fingerprint TEXT,
                digest_id INTEGER,
                markdown_path TEXT,
                json_path TEXT,
                html_path TEXT,
                telegraph_url TEXT,
                telegram_delivery_timestamp TEXT,
                telegram_message_id INTEGER,
                fallback_delivery TEXT,
                fallback_delivery_used INTEGER NOT NULL DEFAULT 0
                    CHECK(fallback_delivery_used IN (0, 1)),
                verification_status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(verification_status IN (
                        'pending',
                        'verified',
                        'needs_review',
                        'failed',
                        'waived'
                    )),
                verifier_method TEXT,
                verifier_notes TEXT,
                checked_at TEXT,
                checked_by TEXT,
                health_flags_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(health_flags_json)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(digest_id) REFERENCES digests(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_research_brief_receipts_week_label
                ON research_brief_receipts(week_label);
            CREATE INDEX IF NOT EXISTS idx_research_brief_receipts_digest_id
                ON research_brief_receipts(digest_id);
            CREATE INDEX IF NOT EXISTS idx_research_brief_receipts_verification_status
                ON research_brief_receipts(verification_status);
            CREATE INDEX IF NOT EXISTS idx_research_brief_receipts_generated_at
                ON research_brief_receipts(generated_at);
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
                channel_score REAL NOT NULL DEFAULT 0.5,
                feedback_weight REAL NOT NULL DEFAULT 0.0,
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
        for stmt in [
            "ALTER TABLE channel_memory ADD COLUMN channel_score REAL NOT NULL DEFAULT 0.5",
            "ALTER TABLE channel_memory ADD COLUMN feedback_weight REAL NOT NULL DEFAULT 0.0",
        ]:
            try:
                connection.execute(stmt)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
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
        try:
            connection.execute(
                "DROP INDEX IF EXISTS idx_signal_evidence_items_idempotent"
            )
        except sqlite3.OperationalError as exc:
            if "no such index" not in str(exc).lower():
                LOGGER.warning(
                    "Failed dropping legacy signal_evidence_items index",
                    exc_info=True,
                )
                raise
        try:
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_sei_unique_per_week
                ON signal_evidence_items(post_id, week_label, evidence_kind)
                """
            )
        except sqlite3.OperationalError as exc:
            if "already exists" not in str(exc).lower():
                LOGGER.warning(
                    "Failed creating signal_evidence_items unique index",
                    exc_info=True,
                )
                raise
        for stmt in [
            "ALTER TABLE project_context_snapshots ADD COLUMN linked_signal_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE project_context_snapshots ADD COLUMN snapshot_week_label TEXT",
        ]:
            try:
                connection.execute(stmt)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS channel_repeated_claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                claim_key TEXT NOT NULL UNIQUE,
                normalized_claim TEXT NOT NULL CHECK(length(trim(normalized_claim)) > 0),
                claim_type TEXT NOT NULL DEFAULT 'general',
                status TEXT NOT NULL DEFAULT 'candidate'
                    CHECK(status IN ('candidate', 'repeated', 'weak', 'rejected')),
                evidence_strength TEXT NOT NULL DEFAULT 'weak'
                    CHECK(evidence_strength IN ('weak', 'moderate', 'strong')),
                first_seen_week TEXT,
                last_seen_week TEXT,
                occurrence_count INTEGER NOT NULL DEFAULT 0,
                channel_count INTEGER NOT NULL DEFAULT 0,
                project_name TEXT,
                topic_label TEXT,
                entity_labels_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(entity_labels_json)),
                evidence_item_ids_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(evidence_item_ids_json)),
                refresh_scope_json TEXT NOT NULL DEFAULT '{}'
                    CHECK(json_valid(refresh_scope_json)),
                extraction_version TEXT NOT NULL DEFAULT 'unversioned',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_channel_repeated_claims_project
                ON channel_repeated_claims(project_name);
            CREATE INDEX IF NOT EXISTS idx_channel_repeated_claims_topic
                ON channel_repeated_claims(topic_label);
            CREATE INDEX IF NOT EXISTS idx_channel_repeated_claims_status
                ON channel_repeated_claims(status);
            CREATE INDEX IF NOT EXISTS idx_channel_repeated_claims_last_seen
                ON channel_repeated_claims(last_seen_week);

            CREATE TABLE IF NOT EXISTS channel_narratives (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                narrative_key TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL CHECK(length(trim(title)) > 0),
                summary TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'candidate'
                    CHECK(status IN ('candidate', 'active', 'stale', 'rejected')),
                project_name TEXT,
                topic_label TEXT,
                first_seen_week TEXT,
                last_seen_week TEXT,
                supporting_post_count INTEGER NOT NULL DEFAULT 0,
                supporting_channel_count INTEGER NOT NULL DEFAULT 0,
                linked_claim_count INTEGER NOT NULL DEFAULT 0,
                evidence_item_ids_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(evidence_item_ids_json)),
                source_channels_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(source_channels_json)),
                refresh_scope_json TEXT NOT NULL DEFAULT '{}'
                    CHECK(json_valid(refresh_scope_json)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_channel_narratives_project
                ON channel_narratives(project_name);
            CREATE INDEX IF NOT EXISTS idx_channel_narratives_topic
                ON channel_narratives(topic_label);
            CREATE INDEX IF NOT EXISTS idx_channel_narratives_status
                ON channel_narratives(status);
            CREATE INDEX IF NOT EXISTS idx_channel_narratives_last_seen
                ON channel_narratives(last_seen_week);

            CREATE TABLE IF NOT EXISTS claim_occurrences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                claim_id INTEGER NOT NULL,
                post_id INTEGER,
                signal_evidence_item_id INTEGER,
                week_label TEXT NOT NULL,
                source_channel TEXT NOT NULL CHECK(length(trim(source_channel)) > 0),
                message_url TEXT,
                posted_at TEXT,
                occurrence_text TEXT NOT NULL CHECK(length(trim(occurrence_text)) > 0),
                extraction_reason TEXT NOT NULL DEFAULT '',
                project_name TEXT,
                topic_label TEXT,
                extraction_version TEXT NOT NULL DEFAULT 'unversioned',
                created_at TEXT NOT NULL,
                FOREIGN KEY(claim_id) REFERENCES channel_repeated_claims(id) ON DELETE CASCADE,
                FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE SET NULL,
                FOREIGN KEY(signal_evidence_item_id) REFERENCES signal_evidence_items(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_claim_occurrences_claim_id
                ON claim_occurrences(claim_id);
            CREATE INDEX IF NOT EXISTS idx_claim_occurrences_week_label
                ON claim_occurrences(week_label);
            CREATE INDEX IF NOT EXISTS idx_claim_occurrences_source_channel
                ON claim_occurrences(source_channel);
            CREATE INDEX IF NOT EXISTS idx_claim_occurrences_project
                ON claim_occurrences(project_name);

            CREATE TABLE IF NOT EXISTS source_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_username TEXT NOT NULL CHECK(length(trim(channel_username)) > 0),
                week_label TEXT NOT NULL,
                scope_key TEXT NOT NULL DEFAULT 'global',
                window_start TEXT,
                window_end TEXT,
                project_name TEXT,
                topic_label TEXT,
                post_count INTEGER NOT NULL DEFAULT 0,
                scored_count INTEGER NOT NULL DEFAULT 0,
                evidence_count INTEGER NOT NULL DEFAULT 0,
                cited_count INTEGER NOT NULL DEFAULT 0,
                acted_on_count INTEGER NOT NULL DEFAULT 0,
                skipped_count INTEGER NOT NULL DEFAULT 0,
                rejected_count INTEGER NOT NULL DEFAULT 0,
                low_signal_count INTEGER NOT NULL DEFAULT 0,
                repeated_claim_count INTEGER NOT NULL DEFAULT 0,
                useful_count INTEGER NOT NULL DEFAULT 0,
                counters_json TEXT NOT NULL DEFAULT '{}'
                    CHECK(json_valid(counters_json)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(channel_username, week_label, scope_key)
            );
            CREATE INDEX IF NOT EXISTS idx_source_observations_channel
                ON source_observations(channel_username);
            CREATE INDEX IF NOT EXISTS idx_source_observations_week_label
                ON source_observations(week_label);
            CREATE INDEX IF NOT EXISTS idx_source_observations_project
                ON source_observations(project_name);
            CREATE INDEX IF NOT EXISTS idx_source_observations_topic
                ON source_observations(topic_label);

            CREATE TABLE IF NOT EXISTS intelligence_entity_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_label TEXT NOT NULL CHECK(length(trim(entity_label)) > 0),
                entity_type TEXT NOT NULL DEFAULT 'unknown',
                linked_object_type TEXT NOT NULL
                    CHECK(linked_object_type IN (
                        'post',
                        'evidence',
                        'claim',
                        'narrative',
                        'project',
                        'channel',
                        'topic'
                    )),
                linked_object_id TEXT NOT NULL,
                project_name TEXT,
                topic_label TEXT,
                source_table TEXT,
                source_row_id INTEGER,
                confidence REAL NOT NULL DEFAULT 0.0,
                reason TEXT NOT NULL DEFAULT '',
                extractor_version TEXT NOT NULL DEFAULT 'unversioned',
                week_label TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(entity_label, entity_type, linked_object_type, linked_object_id, extractor_version)
            );
            CREATE INDEX IF NOT EXISTS idx_intelligence_entity_links_entity
                ON intelligence_entity_links(entity_label, entity_type);
            CREATE INDEX IF NOT EXISTS idx_intelligence_entity_links_object
                ON intelligence_entity_links(linked_object_type, linked_object_id);
            CREATE INDEX IF NOT EXISTS idx_intelligence_entity_links_project
                ON intelligence_entity_links(project_name);
            CREATE INDEX IF NOT EXISTS idx_intelligence_entity_links_week
                ON intelligence_entity_links(week_label);

            CREATE TABLE IF NOT EXISTS project_intelligence_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL CHECK(length(trim(project_name)) > 0),
                linked_object_type TEXT NOT NULL
                    CHECK(linked_object_type IN (
                        'claim',
                        'narrative',
                        'entity',
                        'source_observation',
                        'rollup'
                    )),
                linked_object_id TEXT NOT NULL,
                week_label TEXT,
                relevance_score REAL NOT NULL DEFAULT 0.0,
                match_reason TEXT NOT NULL DEFAULT '',
                evidence_item_ids_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(evidence_item_ids_json)),
                active_project INTEGER NOT NULL DEFAULT 1
                    CHECK(active_project IN (0, 1)),
                refresh_scope_json TEXT NOT NULL DEFAULT '{}'
                    CHECK(json_valid(refresh_scope_json)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(project_name, linked_object_type, linked_object_id, week_label)
            );
            CREATE INDEX IF NOT EXISTS idx_project_intelligence_links_project
                ON project_intelligence_links(project_name);
            CREATE INDEX IF NOT EXISTS idx_project_intelligence_links_object
                ON project_intelligence_links(linked_object_type, linked_object_id);
            CREATE INDEX IF NOT EXISTS idx_project_intelligence_links_week
                ON project_intelligence_links(week_label);

            CREATE TABLE IF NOT EXISTS narrative_claim_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                narrative_id INTEGER NOT NULL,
                claim_id INTEGER NOT NULL,
                link_reason TEXT NOT NULL DEFAULT '',
                shared_evidence_count INTEGER NOT NULL DEFAULT 0,
                shared_entities_json TEXT NOT NULL DEFAULT '[]'
                    CHECK(json_valid(shared_entities_json)),
                confidence REAL NOT NULL DEFAULT 0.0,
                created_at TEXT NOT NULL,
                UNIQUE(narrative_id, claim_id),
                FOREIGN KEY(narrative_id) REFERENCES channel_narratives(id) ON DELETE CASCADE,
                FOREIGN KEY(claim_id) REFERENCES channel_repeated_claims(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_narrative_claim_links_narrative
                ON narrative_claim_links(narrative_id);
            CREATE INDEX IF NOT EXISTS idx_narrative_claim_links_claim
                ON narrative_claim_links(claim_id);

            CREATE TABLE IF NOT EXISTS channel_intelligence_weekly_rollups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_label TEXT NOT NULL,
                scope_key TEXT NOT NULL DEFAULT 'global',
                project_name TEXT,
                topic_label TEXT,
                source_channel TEXT,
                section_name TEXT NOT NULL DEFAULT 'default',
                item_type TEXT NOT NULL
                    CHECK(item_type IN (
                        'narrative',
                        'claim',
                        'source_observation',
                        'entity_link',
                        'project_link'
                    )),
                item_id TEXT NOT NULL,
                input_row_ids_json TEXT NOT NULL DEFAULT '{}'
                    CHECK(json_valid(input_row_ids_json)),
                summary_json TEXT NOT NULL DEFAULT '{}'
                    CHECK(json_valid(summary_json)),
                weak_evidence INTEGER NOT NULL DEFAULT 0
                    CHECK(weak_evidence IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(week_label, scope_key, section_name, item_type, item_id)
            );
            CREATE INDEX IF NOT EXISTS idx_channel_intelligence_rollups_week
                ON channel_intelligence_weekly_rollups(week_label);
            CREATE INDEX IF NOT EXISTS idx_channel_intelligence_rollups_project
                ON channel_intelligence_weekly_rollups(project_name);
            CREATE INDEX IF NOT EXISTS idx_channel_intelligence_rollups_topic
                ON channel_intelligence_weekly_rollups(topic_label);
            CREATE INDEX IF NOT EXISTS idx_channel_intelligence_rollups_source
                ON channel_intelligence_weekly_rollups(source_channel);
            """
        )
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
    try:
        record_decision_for_feedback(connection, post_id, feedback)
        connection.commit()
    except Exception:
        LOGGER.warning(
            "Decision journal write failed for feedback post_id=%s feedback=%s",
            post_id,
            feedback,
            exc_info=True,
        )


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
    try:
        record_signal_evidence_for_manual_tag(connection, post_id, tag)
        connection.commit()
    except Exception:
        LOGGER.warning(
            "Signal evidence write failed for tag post_id=%s tag=%s",
            post_id,
            tag,
            exc_info=True,
        )


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
    try:
        record_study_completion_decision(connection, week_label)
        connection.commit()
    except Exception:
        LOGGER.warning(
            "Decision journal write failed for study completion week_label=%s",
            week_label,
            exc_info=True,
        )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run_migrations()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS raw_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_username TEXT NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    posted_at TEXT NOT NULL,
    text TEXT,
    media_type TEXT,
    media_caption TEXT,
    forward_from TEXT,
    view_count INTEGER,
    message_url TEXT,
    raw_json TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    image_description TEXT,
    UNIQUE(channel_id, message_id)
);

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_post_id INTEGER NOT NULL UNIQUE,
    channel_username TEXT NOT NULL,
    posted_at TEXT NOT NULL,
    content TEXT NOT NULL,
    url_count INTEGER NOT NULL DEFAULT 0,
    has_code INTEGER NOT NULL DEFAULT 0,
    language_detected TEXT,
    word_count INTEGER NOT NULL DEFAULT 0,
    normalized_at TEXT NOT NULL,
    FOREIGN KEY(raw_post_id) REFERENCES raw_posts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    description TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    post_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS post_topics (
    post_id INTEGER NOT NULL,
    topic_id INTEGER NOT NULL,
    confidence REAL NOT NULL,
    PRIMARY KEY(post_id, topic_id),
    FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY(topic_id) REFERENCES topics(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS digests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_label TEXT NOT NULL UNIQUE,
    generated_at TEXT NOT NULL,
    content_md TEXT NOT NULL,
    content_json TEXT,
    pdf_path TEXT,
    post_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_label TEXT NOT NULL UNIQUE,
    generated_at TEXT NOT NULL,
    content_md TEXT NOT NULL
);

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
            'wrong_priority',
            'not_interested',
            'noise'
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
            'action'
        )),
    target_ref TEXT,
    source_url TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    recorded_by TEXT NOT NULL DEFAULT 'operator'
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    keywords TEXT,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS post_project_links (
    post_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL,
    relevance_score REAL NOT NULL,
    note TEXT,
    PRIMARY KEY(post_id, project_id),
    FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reaction_sync_state (
    source TEXT NOT NULL,
    channel_username TEXT NOT NULL,
    message_id INTEGER NOT NULL,
    emoji TEXT NOT NULL,
    action_key TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    PRIMARY KEY(source, channel_username, message_id, emoji, action_key)
);

CREATE VIRTUAL TABLE IF NOT EXISTS posts_fts USING fts5(
    content,
    content='posts',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS posts_ai AFTER INSERT ON posts BEGIN
    INSERT INTO posts_fts(rowid, content)
    VALUES (new.id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS posts_ad AFTER DELETE ON posts BEGIN
    INSERT INTO posts_fts(posts_fts, rowid, content)
    VALUES ('delete', old.id, old.content);
END;

CREATE TRIGGER IF NOT EXISTS posts_au AFTER UPDATE ON posts BEGIN
    INSERT INTO posts_fts(posts_fts, rowid, content)
    VALUES ('delete', old.id, old.content);
    INSERT INTO posts_fts(rowid, content)
    VALUES (new.id, new.content);
END;

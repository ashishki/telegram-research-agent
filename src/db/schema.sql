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

-- IRX-4 canonical curation is deliberately additive.  The mutable
-- idea_threads/idea_thread_atoms tables above remain raw compatibility and
-- audit provenance; canonical identity and history live only in these tables.
CREATE TABLE IF NOT EXISTS canonical_idea_threads (
    canonical_thread_id TEXT PRIMARY KEY
        CHECK(canonical_thread_id GLOB 'ct_[0-9a-f]*'
              AND substr(canonical_thread_id, 4) NOT GLOB '*[^0-9a-f]*'
              AND length(canonical_thread_id) = 27),
    stable_slug TEXT NOT NULL UNIQUE
        CHECK(length(trim(stable_slug)) BETWEEN 1 AND 96
              AND stable_slug = lower(stable_slug)
              AND stable_slug NOT GLOB '*[^a-z0-9-]*'
              AND stable_slug NOT GLOB '-*'
              AND stable_slug NOT GLOB '*-'
              AND stable_slug NOT GLOB '*--*'),
    title_ru TEXT NOT NULL CHECK(length(trim(title_ru)) > 0),
    normalized_title_ru TEXT NOT NULL CHECK(length(trim(normalized_title_ru)) > 0),
    title_en TEXT NOT NULL CHECK(length(trim(title_en)) > 0),
    normalized_title_en TEXT NOT NULL CHECK(length(trim(normalized_title_en)) > 0),
    thesis TEXT NOT NULL CHECK(length(trim(thesis)) > 0),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active', 'stale', 'merged', 'split', 'resolved', 'archived')),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    evidence_maturity TEXT NOT NULL DEFAULT 'single_source'
        CHECK(evidence_maturity IN (
            'single_source',
            'repeated_signal',
            'multi_channel',
            'primary_verified',
            'externally_corroborated',
            'decision_grade'
        )),
    operator_interest REAL NOT NULL DEFAULT 0.0
        CHECK(operator_interest >= 0.0 AND operator_interest <= 1.0),
    entities_json TEXT NOT NULL DEFAULT '[]'
        CHECK(json_valid(entities_json) AND json_type(entities_json) = 'array'),
    curator_version TEXT NOT NULL CHECK(length(trim(curator_version)) > 0),
    current_version INTEGER NOT NULL DEFAULT 1 CHECK(current_version >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_canonical_idea_threads_active_title_ru
    ON canonical_idea_threads(normalized_title_ru)
    WHERE status = 'active';
CREATE UNIQUE INDEX IF NOT EXISTS uq_canonical_idea_threads_active_title_en
    ON canonical_idea_threads(normalized_title_en)
    WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_canonical_idea_threads_status
    ON canonical_idea_threads(status);
CREATE INDEX IF NOT EXISTS idx_canonical_idea_threads_last_seen
    ON canonical_idea_threads(last_seen_at);

CREATE TABLE IF NOT EXISTS canonical_idea_thread_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_thread_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK(version >= 1),
    stable_slug TEXT NOT NULL
        CHECK(length(trim(stable_slug)) BETWEEN 1 AND 96
              AND stable_slug = lower(stable_slug)
              AND stable_slug NOT GLOB '*[^a-z0-9-]*'
              AND stable_slug NOT GLOB '-*'
              AND stable_slug NOT GLOB '*-'
              AND stable_slug NOT GLOB '*--*'),
    title_ru TEXT NOT NULL CHECK(length(trim(title_ru)) > 0),
    normalized_title_ru TEXT NOT NULL CHECK(length(trim(normalized_title_ru)) > 0),
    title_en TEXT NOT NULL CHECK(length(trim(title_en)) > 0),
    normalized_title_en TEXT NOT NULL CHECK(length(trim(normalized_title_en)) > 0),
    thesis TEXT NOT NULL CHECK(length(trim(thesis)) > 0),
    status TEXT NOT NULL
        CHECK(status IN ('active', 'stale', 'merged', 'split', 'resolved', 'archived')),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    evidence_maturity TEXT NOT NULL
        CHECK(evidence_maturity IN (
            'single_source',
            'repeated_signal',
            'multi_channel',
            'primary_verified',
            'externally_corroborated',
            'decision_grade'
        )),
    operator_interest REAL NOT NULL
        CHECK(operator_interest >= 0.0 AND operator_interest <= 1.0),
    entities_json TEXT NOT NULL DEFAULT '[]'
        CHECK(json_valid(entities_json) AND json_type(entities_json) = 'array'),
    curator_version TEXT NOT NULL CHECK(length(trim(curator_version)) > 0),
    operation TEXT NOT NULL
        CHECK(operation IN (
            'create', 'update', 'merge', 'split', 'stale', 'operator_correction',
            'keep_separate', 'keep_together', 'defer'
        )),
    decision_id TEXT NOT NULL CHECK(length(trim(decision_id)) > 0),
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(canonical_thread_id, version),
    CHECK(valid_to IS NULL OR valid_to > valid_from),
    FOREIGN KEY(canonical_thread_id)
        REFERENCES canonical_idea_threads(canonical_thread_id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_canonical_idea_thread_versions_current
    ON canonical_idea_thread_versions(canonical_thread_id)
    WHERE valid_to IS NULL;
CREATE INDEX IF NOT EXISTS idx_canonical_idea_thread_versions_as_of
    ON canonical_idea_thread_versions(canonical_thread_id, valid_from, valid_to);
CREATE INDEX IF NOT EXISTS idx_canonical_idea_thread_versions_slug_as_of
    ON canonical_idea_thread_versions(stable_slug, valid_from, valid_to);

CREATE TABLE IF NOT EXISTS canonical_idea_thread_atom_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_thread_id TEXT NOT NULL,
    atom_id INTEGER NOT NULL,
    raw_thread_id INTEGER,
    relation TEXT NOT NULL DEFAULT 'supports'
        CHECK(relation IN ('supports', 'contradicts', 'supersedes', 'related')),
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    assigned_decision_id TEXT NOT NULL CHECK(length(trim(assigned_decision_id)) > 0),
    retired_decision_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(canonical_thread_id, atom_id, valid_from),
    CHECK(valid_to IS NULL OR valid_to > valid_from),
    FOREIGN KEY(canonical_thread_id)
        REFERENCES canonical_idea_threads(canonical_thread_id) ON DELETE RESTRICT,
    FOREIGN KEY(atom_id) REFERENCES knowledge_atoms(id) ON DELETE RESTRICT,
    FOREIGN KEY(raw_thread_id) REFERENCES idea_threads(id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_canonical_atom_current_owner
    ON canonical_idea_thread_atom_history(atom_id)
    WHERE valid_to IS NULL;
CREATE INDEX IF NOT EXISTS idx_canonical_atom_history_thread_as_of
    ON canonical_idea_thread_atom_history(canonical_thread_id, valid_from, valid_to);
CREATE INDEX IF NOT EXISTS idx_canonical_atom_history_atom_as_of
    ON canonical_idea_thread_atom_history(atom_id, valid_from, valid_to);
CREATE INDEX IF NOT EXISTS idx_canonical_atom_history_raw_thread
    ON canonical_idea_thread_atom_history(raw_thread_id);

CREATE TABLE IF NOT EXISTS canonical_idea_thread_alias_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_thread_id TEXT NOT NULL,
    alias_type TEXT NOT NULL
        CHECK(alias_type IN (
            'raw_thread_id',
            'raw_thread_slug',
            'compatibility_ref',
            'legacy_ref',
            'title',
            'model_version',
            'manual'
        )),
    alias_value TEXT NOT NULL CHECK(length(trim(alias_value)) > 0),
    normalized_alias TEXT NOT NULL CHECK(length(trim(normalized_alias)) > 0),
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    assigned_decision_id TEXT NOT NULL CHECK(length(trim(assigned_decision_id)) > 0),
    retired_decision_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(canonical_thread_id, alias_type, normalized_alias, valid_from),
    CHECK(valid_to IS NULL OR valid_to > valid_from),
    FOREIGN KEY(canonical_thread_id)
        REFERENCES canonical_idea_threads(canonical_thread_id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_canonical_alias_current_owner
    ON canonical_idea_thread_alias_history(alias_type, normalized_alias)
    WHERE valid_to IS NULL;
CREATE INDEX IF NOT EXISTS idx_canonical_alias_history_thread_as_of
    ON canonical_idea_thread_alias_history(canonical_thread_id, valid_from, valid_to);
CREATE INDEX IF NOT EXISTS idx_canonical_alias_history_lookup_as_of
    ON canonical_idea_thread_alias_history(normalized_alias, valid_from, valid_to);

CREATE TABLE IF NOT EXISTS canonical_idea_thread_lineage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    relation_type TEXT NOT NULL CHECK(relation_type IN ('merge', 'split')),
    from_thread_id TEXT NOT NULL,
    to_thread_id TEXT NOT NULL,
    decision_id TEXT NOT NULL CHECK(length(trim(decision_id)) > 0),
    event_at TEXT NOT NULL,
    reason TEXT NOT NULL CHECK(length(trim(reason)) > 0),
    created_at TEXT NOT NULL,
    UNIQUE(relation_type, from_thread_id, to_thread_id, event_at),
    CHECK(from_thread_id <> to_thread_id),
    FOREIGN KEY(from_thread_id)
        REFERENCES canonical_idea_threads(canonical_thread_id) ON DELETE RESTRICT,
    FOREIGN KEY(to_thread_id)
        REFERENCES canonical_idea_threads(canonical_thread_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_canonical_lineage_from
    ON canonical_idea_thread_lineage(from_thread_id, event_at);
CREATE INDEX IF NOT EXISTS idx_canonical_lineage_to
    ON canonical_idea_thread_lineage(to_thread_id, event_at);

CREATE TABLE IF NOT EXISTS canonical_idea_thread_curator_decisions (
    decision_id TEXT PRIMARY KEY CHECK(length(trim(decision_id)) > 0),
    run_id TEXT NOT NULL CHECK(length(trim(run_id)) > 0),
    operation TEXT NOT NULL
        CHECK(operation IN (
            'create', 'update', 'merge', 'split', 'stale', 'operator_correction',
            'keep_separate', 'keep_together', 'defer'
        )),
    proposal_json TEXT NOT NULL CHECK(json_valid(proposal_json)),
    evidence_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(evidence_json)),
    model TEXT NOT NULL CHECK(length(trim(model)) > 0),
    model_version TEXT NOT NULL CHECK(length(trim(model_version)) > 0),
    curator_version TEXT NOT NULL CHECK(length(trim(curator_version)) > 0),
    reason TEXT NOT NULL CHECK(length(trim(reason)) > 0),
    validation_status TEXT NOT NULL DEFAULT 'pending'
        CHECK(validation_status IN ('pending', 'passed', 'rejected')),
    validation_errors_json TEXT NOT NULL DEFAULT '[]'
        CHECK(json_valid(validation_errors_json)
              AND json_type(validation_errors_json) = 'array'),
    decision_status TEXT NOT NULL DEFAULT 'proposed'
        CHECK(decision_status IN ('proposed', 'applied', 'rejected')),
    actor TEXT NOT NULL DEFAULT 'curator' CHECK(length(trim(actor)) > 0),
    proposed_at TEXT NOT NULL,
    validated_at TEXT,
    applied_at TEXT,
    result_json TEXT CHECK(result_json IS NULL OR json_valid(result_json)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_canonical_curator_decisions_run
    ON canonical_idea_thread_curator_decisions(run_id, operation);
CREATE INDEX IF NOT EXISTS idx_canonical_curator_decisions_status
    ON canonical_idea_thread_curator_decisions(decision_status, validation_status);

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

CREATE TABLE IF NOT EXISTS ai_report_feedback_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_label TEXT NOT NULL CHECK(length(trim(week_label)) > 0),
    report_path TEXT,
    report_run_id TEXT,
    report_surface TEXT NOT NULL DEFAULT 'weekly_brief'
        CHECK(report_surface IN (
            'weekly_brief',
            'knowledge_atlas',
            'mvp_radar',
            'reaction_personalization',
            'project_action',
            'visual',
            'audit_explorer',
            'report_package'
        )),
    section_id TEXT NOT NULL DEFAULT 'report' CHECK(length(trim(section_id)) > 0),
    item_ref TEXT NOT NULL DEFAULT 'report' CHECK(length(trim(item_ref)) > 0),
    feedback_type TEXT NOT NULL
        CHECK(feedback_type IN (
            'read',
            'useful',
            'tried',
            'applied_to_project',
            'too_shallow',
            'too_long',
            'confusing_visual',
            'missing_visual',
            'duplicate_content',
            'action_completed',
            'radar_decision_useful',
            'reaction_effect_missing',
            'source_trust_correction',
            'desired_report_change',
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
    feedback_classification TEXT NOT NULL DEFAULT 'desired_report_change'
        CHECK(feedback_classification IN (
            'useful',
            'wrong_priority',
            'too_shallow',
            'too_long',
            'confusing_visual',
            'missing_visual',
            'duplicate_content',
            'action_completed',
            'applied_to_project',
            'radar_decision_useful',
            'reaction_effect_missing',
            'source_trust_correction',
            'desired_report_change'
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
    confirmation_state TEXT NOT NULL DEFAULT 'confirmed'
        CHECK(confirmation_state IN ('pending', 'confirmed', 'discarded')),
    application_status TEXT NOT NULL DEFAULT 'unchanged'
        CHECK(application_status IN (
            'applied',
            'unchanged',
            'code_config_required',
            'rejected',
            'pending'
        )),
    application_reason TEXT NOT NULL DEFAULT 'Legacy feedback row preserved through additive IRX-12 fields.',
    originating_report_item_ref TEXT,
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

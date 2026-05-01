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

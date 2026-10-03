-- Consistency store schema (HANDOVER §11.1).
-- One store shared by all decoys; every row is scoped by host_id.

CREATE TABLE IF NOT EXISTS hosts (
    host_id  TEXT PRIMARY KEY,
    ip       TEXT,
    hostname TEXT,
    os       TEXT,
    persona  TEXT,
    gen_type TEXT                 -- real | static | topology | llm_store
);

CREATE TABLE IF NOT EXISTS files (
    host_id TEXT,
    path    TEXT,
    content TEXT,
    owner   TEXT DEFAULT 'root',
    mode    TEXT DEFAULT '0644',  -- a leading 'd' in mode marks a directory
    mtime   TEXT,
    planted INTEGER DEFAULT 0,    -- 1 = planted by the clue-chain generator
    PRIMARY KEY (host_id, path)
);

CREATE TABLE IF NOT EXISTS users (
    host_id  TEXT,
    username TEXT,
    uid      INTEGER,
    password TEXT,
    shell    TEXT DEFAULT '/bin/bash',
    home     TEXT,
    planted  INTEGER DEFAULT 0,
    PRIMARY KEY (host_id, username)
);

CREATE TABLE IF NOT EXISTS procs (
    host_id TEXT,
    pid     INTEGER,
    user    TEXT,
    cmd     TEXT
);

CREATE TABLE IF NOT EXISTS history (
    host_id    TEXT,
    session_id TEXT,
    ts         TEXT,
    command    TEXT,
    response   TEXT
);

CREATE INDEX IF NOT EXISTS idx_files_host   ON files (host_id);
CREATE INDEX IF NOT EXISTS idx_users_host   ON users (host_id);
CREATE INDEX IF NOT EXISTS idx_procs_host   ON procs (host_id);
CREATE INDEX IF NOT EXISTS idx_history_host ON history (host_id, session_id);

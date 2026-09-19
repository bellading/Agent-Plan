-- AgentPlan v1 schema

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'bella',
    title TEXT NOT NULL,
    notes TEXT,
    category TEXT,
    type TEXT NOT NULL CHECK (type IN ('single', 'goal')),
    importance TEXT CHECK (importance IN ('high', 'med', 'low')),
    urgency TEXT CHECK (urgency IN ('high', 'med', 'low')),
    action TEXT CHECK (action IN ('now', 'schedule', 'routine', 'drop')),
    status TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo', 'doing', 'done', 'missed', 'routine', 'dropped')),
    remind_at TEXT,
    snooze_until TEXT,
    deadline TEXT,
    notified_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);

-- v1 single-user context for the triage prompt; user_id kept so adding
-- a second user later is additive, not a schema change.
CREATE TABLE IF NOT EXISTS user_profile (
    user_id TEXT PRIMARY KEY,
    focus TEXT,
    availability TEXT
);

-- AI问答 conversation history, so the chat view survives a page reload.
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'bella',
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 计划列表 category tiles. sort_order keeps 其他 pinned last; user-added
-- custom categories (the "+" tile) land in between. INSERT OR IGNORE below
-- runs on every startup (schema.sql is executed unconditionally), so
-- existing databases get the defaults too, not just fresh installs.
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    sort_order INTEGER NOT NULL
);

INSERT OR IGNORE INTO categories (name, sort_order) VALUES
    ('学习', 10), ('工作', 20), ('运动', 30), ('食物', 40), ('其他', 999999);

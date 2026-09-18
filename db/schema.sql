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

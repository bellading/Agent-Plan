-- AgentPlan schema -- multi-user

-- One row per registered person. There's no admin/invite concept yet:
-- anyone who can reach the site can register their own account, and every
-- other table's owner_id scopes that account's data away from everyone
-- else's.
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL REFERENCES users(id),
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

-- Per-user context for the AI 问答 prompt (focus / availability). Nothing
-- writes to this yet -- it's read with a fallback to "未设置" -- but it's
-- kept per-owner so a future settings UI has somewhere to put it.
CREATE TABLE IF NOT EXISTS user_profile (
    owner_id INTEGER PRIMARY KEY REFERENCES users(id),
    focus TEXT,
    availability TEXT
);

-- A chat "branch" / thread in AI 问答. Each conversation has its own
-- independent message history and its own plan-confirm/add-confirm state
-- (see chat_messages.action_type below), so switching to a new conversation
-- never carries over an unrelated one's half-finished confirmation flow.
-- title is NULL until the conversation's first message is sent, at which
-- point it's set from that message's text; updated_at is bumped on every
-- new message so the branch list can sort most-recently-active first.
CREATE TABLE IF NOT EXISTS chat_conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- AI问答 conversation history, so the chat view survives a page reload.
-- action_type tags an assistant row with which confirmation step it was
-- ('plan_confirm' or 'add_confirm'), so chat_reply_stream can enforce the
-- satisfaction-before-add order in code instead of trusting the model to
-- remember it.
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL REFERENCES users(id),
    conversation_id INTEGER REFERENCES chat_conversations(id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    feedback TEXT CHECK (feedback IN ('up', 'down')),
    action_type TEXT CHECK (action_type IN ('plan_confirm', 'add_confirm')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 计划列表 category tiles, per owner -- one person's custom category never
-- shows up in someone else's grid. sort_order keeps 其他 pinned last;
-- defaults are seeded per-account at registration time (see
-- tasks_repo.seed_default_categories), not here, since there's no single
-- "the" user anymore to seed them for at schema-creation time.
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    sort_order INTEGER NOT NULL,
    UNIQUE (owner_id, name)
);

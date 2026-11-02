"""Create (or reset) the AgentPlan SQLite database from schema.sql + seed.sql."""

import os
import sqlite3
import sys
from pathlib import Path

DB_DIR = Path(__file__).parent
# AGENTPLAN_DB_PATH lets a deployment point the database at a persistent
# volume (e.g. Railway/Render mount it outside the app's own ephemeral
# filesystem) instead of living inside the repo checkout, which gets wiped
# on every redeploy. Defaults to the local-dev path when unset.
DB_PATH = Path(os.environ["AGENTPLAN_DB_PATH"]) if os.environ.get("AGENTPLAN_DB_PATH") else DB_DIR / "agent_plan.db"
SCHEMA_PATH = DB_DIR / "schema.sql"
SEED_PATH = DB_DIR / "seed.sql"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    """Add a column if it's missing, so existing databases (created before
    this column existed) pick it up without a manual migration. schema.sql's
    CREATE TABLE IF NOT EXISTS alone can't do this for a table that already
    exists without the column.
    """
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def _backfill_legacy_conversation(conn: sqlite3.Connection) -> None:
    """One-time migration: chat_messages rows created before AI 问答 had
    multiple conversation branches all have conversation_id = NULL. Give
    them a single conversation (titled from their first user message) so
    they still show up in the branch list instead of silently vanishing.
    """
    orphan_count = conn.execute(
        "SELECT COUNT(*) FROM chat_messages WHERE conversation_id IS NULL"
    ).fetchone()[0]
    if orphan_count == 0:
        return

    first_user_msg = conn.execute(
        "SELECT content FROM chat_messages WHERE conversation_id IS NULL AND role = 'user' "
        "ORDER BY id LIMIT 1"
    ).fetchone()
    title = first_user_msg[0][:18] if first_user_msg and first_user_msg[0] else "以前的对话"

    earliest, latest = conn.execute(
        "SELECT MIN(created_at), MAX(created_at) FROM chat_messages WHERE conversation_id IS NULL"
    ).fetchone()

    cur = conn.execute(
        "INSERT INTO chat_conversations (title, created_at, updated_at) VALUES (?, ?, ?)",
        (title, earliest, latest),
    )
    conn.execute(
        "UPDATE chat_messages SET conversation_id = ? WHERE conversation_id IS NULL",
        (cur.lastrowid,),
    )


# Tables that hold per-user data and so need an owner_id column added when
# migrating a database created before AgentPlan had user accounts at all.
_OWNED_TABLES = ["tasks", "categories", "chat_conversations", "chat_messages", "user_profile"]


def any_users_exist(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None


def backfill_first_owner(conn: sqlite3.Connection, user_id: int) -> None:
    """Called once, right after the very first account is ever registered:
    assigns every pre-existing row that has no owner (owner_id IS NULL --
    data from before AgentPlan had accounts, or a legacy user_id TEXT column
    with no matching owner_id yet) to that first account, instead of it
    silently becoming invisible once every query starts filtering by
    owner_id. Safe to call only once -- later registrations must NOT touch
    other people's already-owned rows, so the caller only invokes this when
    any_users_exist() was false right before creating the new account.
    """
    for table in _OWNED_TABLES:
        conn.execute(f"UPDATE {table} SET owner_id = ? WHERE owner_id IS NULL", (user_id,))


def init_db(reset: bool = False, seed: bool = True) -> None:
    """Create the schema and, only on a genuinely empty tasks table, load the
    seed data. Safe to call on every startup: never re-runs seed.sql (which
    isn't idempotent) against a database that already has real tasks in it.
    """
    if reset and DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        _ensure_column(conn, "chat_messages", "feedback", "feedback TEXT")
        _ensure_column(conn, "chat_messages", "action_type", "action_type TEXT")
        _ensure_column(conn, "chat_messages", "conversation_id", "conversation_id INTEGER")
        _ensure_column(conn, "users", "email", "email TEXT")
        for table in _OWNED_TABLES:
            _ensure_column(conn, table, "owner_id", "owner_id INTEGER")
        _backfill_legacy_conversation(conn)
        if seed:
            row_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            if row_count == 0:
                conn.executescript(SEED_PATH.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()

    print(f"DB ready at {DB_PATH}")


if __name__ == "__main__":
    init_db(reset="--reset" in sys.argv, seed="--no-seed" not in sys.argv)

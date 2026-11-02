"""Create (or reset) the AgentPlan SQLite database from schema.sql + seed.sql."""

import sqlite3
import sys
from pathlib import Path

DB_DIR = Path(__file__).parent
DB_PATH = DB_DIR / "agent_plan.db"
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

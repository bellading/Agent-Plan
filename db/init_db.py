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


def init_db(reset: bool = False, seed: bool = True) -> None:
    """Create the schema and, only on a genuinely empty tasks table, load the
    seed data. Safe to call on every startup: never re-runs seed.sql (which
    isn't idempotent) against a database that already has real tasks in it.
    """
    if reset and DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(SCHEMA_PATH.read_text())
        if seed:
            row_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            if row_count == 0:
                conn.executescript(SEED_PATH.read_text())
        conn.commit()
    finally:
        conn.close()

    print(f"DB ready at {DB_PATH}")


if __name__ == "__main__":
    init_db(reset="--reset" in sys.argv, seed="--no-seed" not in sys.argv)

"""Create (or reset) the AgentPlan SQLite database from schema.sql + seed.sql."""

import sqlite3
import sys
from pathlib import Path

DB_DIR = Path(__file__).parent
DB_PATH = DB_DIR / "agent_plan.db"
SCHEMA_PATH = DB_DIR / "schema.sql"
SEED_PATH = DB_DIR / "seed.sql"


def init_db(reset: bool = False, seed: bool = True) -> None:
    if reset and DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(SCHEMA_PATH.read_text())
        if seed:
            conn.executescript(SEED_PATH.read_text())
        conn.commit()
    finally:
        conn.close()

    print(f"DB ready at {DB_PATH}")


if __name__ == "__main__":
    init_db(reset="--reset" in sys.argv, seed="--no-seed" not in sys.argv)

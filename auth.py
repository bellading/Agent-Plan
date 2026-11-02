"""Multi-user login for AgentPlan: anyone can register their own account;
each account's data is isolated by owner_id everywhere else in the app.

The Flask session secret key is still a single, file-based, server-side
value (not per-user) -- that's app configuration, not account data, so it
doesn't belong in the users table.
"""

import secrets as secrets_module
import sqlite3
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

SECRETS_DIR = Path(__file__).parent / ".secrets"
SECRET_KEY_FILE = SECRETS_DIR / "flask_secret_key.txt"


def create_user(conn: sqlite3.Connection, username: str, password: str) -> int:
    """Raises sqlite3.IntegrityError if the username is already taken
    (username has a UNIQUE constraint) -- the caller turns that into a
    friendly "用户名已被占用" message rather than a 500.
    """
    cur = conn.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, generate_password_hash(password)),
    )
    conn.commit()
    return cur.lastrowid


def verify_user(conn: sqlite3.Connection, username: str, password: str) -> int | None:
    row = conn.execute(
        "SELECT id, password_hash FROM users WHERE username = ?", (username,)
    ).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        return None
    return row["id"]


def get_username(conn: sqlite3.Connection, user_id: int) -> str | None:
    row = conn.execute("SELECT username FROM users WHERE id = ?", (user_id,)).fetchone()
    return row["username"] if row else None


def get_flask_secret_key() -> str:
    """A random key persisted to disk so Flask's signed session cookie stays
    valid across restarts instead of logging everyone out every time the
    server restarts.
    """
    SECRETS_DIR.mkdir(exist_ok=True)
    if SECRET_KEY_FILE.exists():
        return SECRET_KEY_FILE.read_text(encoding="utf-8").strip()
    key = secrets_module.token_hex(32)
    SECRET_KEY_FILE.write_text(key, encoding="utf-8")
    return key

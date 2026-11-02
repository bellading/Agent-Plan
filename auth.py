"""Single-user login for AgentPlan: one username/password pair, stored
locally and never committed (see .secrets/, which is gitignored).

There's no multi-account concept here on purpose -- this app runs on
Bella's own machine for her own use, so "login" just means "set a
password once, then type it each time before the app opens."
"""

import json
import secrets as secrets_module
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

SECRETS_DIR = Path(__file__).parent / ".secrets"
AUTH_FILE = SECRETS_DIR / "auth.json"
SECRET_KEY_FILE = SECRETS_DIR / "flask_secret_key.txt"


def has_account() -> bool:
    return AUTH_FILE.exists()


def create_account(username: str, password: str) -> None:
    SECRETS_DIR.mkdir(exist_ok=True)
    AUTH_FILE.write_text(
        json.dumps({"username": username, "password_hash": generate_password_hash(password)}),
        encoding="utf-8",
    )


def verify_login(username: str, password: str) -> bool:
    if not has_account():
        return False
    data = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
    return username == data["username"] and check_password_hash(data["password_hash"], password)


def get_username() -> str | None:
    if not has_account():
        return None
    return json.loads(AUTH_FILE.read_text(encoding="utf-8"))["username"]


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

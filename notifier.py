"""Pluggable reminder push channel.

Default: Server酱 (https://sct.ftqq.com) — pushes a WeChat 服务号 template
message from a single HTTP call, no app install needed. Not Telegram,
since the target user is in mainland China.

Get a SendKey: scan the WeChat QR code at https://sct.ftqq.com/. Then either
  export SERVERCHAN_SENDKEY=SCT...
or save it to .secrets/serverchan_sendkey.txt (gitignored) so it persists
across terminal sessions without re-exporting.
"""

import os
from pathlib import Path

import requests

SECRET_FILE = Path(__file__).parent / ".secrets" / "serverchan_sendkey.txt"


def _sendkey() -> str | None:
    env_key = os.environ.get("SERVERCHAN_SENDKEY")
    if env_key:
        return env_key
    if SECRET_FILE.exists():
        return SECRET_FILE.read_text().strip()
    return None


def send_wechat(title: str, content: str = "") -> bool:
    """Push a reminder to WeChat via Server酱. Returns True only on confirmed send."""
    sendkey = _sendkey()
    if not sendkey:
        print(f"[notifier] SERVERCHAN_SENDKEY not configured, would have sent: {title}")
        return False

    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    resp = requests.post(url, data={"title": title, "desp": content}, timeout=10)
    resp.raise_for_status()
    return resp.json().get("code") == 0

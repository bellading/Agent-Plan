"""Pluggable reminder push channels.

Email (send_email): the primary channel now that AgentPlan is multi-user --
every account has its own reminder email (users.email), unlike a WeChat
push key which is tied to one person's WeChat account and can't be handed
out per-user. Sent via Gmail SMTP with an App Password (not your normal
Gmail password -- Google requires a separate 16-character app password for
SMTP once 2-Step Verification is on):
  1. Turn on 2-Step Verification: https://myaccount.google.com/signinoptions/two-step-verification
  2. Generate an app password: https://myaccount.google.com/apppasswords
     (choose "Mail" / a custom name like "AgentPlan")
  3. Set either as env vars (GMAIL_ADDRESS, GMAIL_APP_PASSWORD) or save to
     .secrets/gmail_address.txt / .secrets/gmail_app_password.txt
     (gitignored, persists locally without re-exporting).
This runs server-side (on Render, not Bella's own network), so mainland
China connectivity to Gmail isn't a factor here.

send_wechat: the original channel, kept as-is for anyone who'd rather set
up Server酱 (https://sct.ftqq.com) instead -- a single SendKey, not
per-user, so it only really fits a single-person deployment.
"""

import os
import smtplib
from email.mime.text import MIMEText
from pathlib import Path

import requests

SECRET_FILE = Path(__file__).parent / ".secrets" / "serverchan_sendkey.txt"
GMAIL_ADDRESS_FILE = Path(__file__).parent / ".secrets" / "gmail_address.txt"
GMAIL_APP_PASSWORD_FILE = Path(__file__).parent / ".secrets" / "gmail_app_password.txt"


def _sendkey() -> str | None:
    env_key = os.environ.get("SERVERCHAN_SENDKEY")
    if env_key:
        return env_key
    if SECRET_FILE.exists():
        return SECRET_FILE.read_text(encoding="utf-8").strip()
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


def _gmail_credentials() -> tuple[str, str] | None:
    address = os.environ.get("GMAIL_ADDRESS") or (
        GMAIL_ADDRESS_FILE.read_text(encoding="utf-8").strip() if GMAIL_ADDRESS_FILE.exists() else None
    )
    app_password = os.environ.get("GMAIL_APP_PASSWORD") or (
        GMAIL_APP_PASSWORD_FILE.read_text(encoding="utf-8").strip() if GMAIL_APP_PASSWORD_FILE.exists() else None
    )
    if not address or not app_password:
        return None
    return address, app_password


def has_email_configured() -> bool:
    return _gmail_credentials() is not None


def send_email(to_address: str, subject: str, body: str = "") -> bool:
    """Send a reminder email via Gmail SMTP. Returns True only on confirmed send."""
    creds = _gmail_credentials()
    if not creds:
        print(f"[notifier] GMAIL_ADDRESS/GMAIL_APP_PASSWORD not configured, would have sent: {subject}")
        return False
    gmail_address, app_password = creds

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = gmail_address
    msg["To"] = to_address

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(gmail_address, app_password)
            server.sendmail(gmail_address, [to_address], msg.as_string())
        return True
    except smtplib.SMTPException as exc:
        print(f"[notifier] failed to send email to {to_address}: {exc}")
        return False

"""Task triage via 通义千问 (Qwen), through DashScope's OpenAI-compatible endpoint.

Get an API key at https://bailian.console.aliyun.com/ (阿里云百炼/DashScope).
Save it either as:
  export DASHSCOPE_API_KEY=sk-...
or in .secrets/qwen_api_key.txt (gitignored, persists across terminal sessions).
"""

import json
import os
import re
from pathlib import Path

from openai import OpenAI

PROMPT_PATH = Path(__file__).parent / "prompts" / "triage_prompt.md"
SECRET_FILE = Path(__file__).parent / ".secrets" / "qwen_api_key.txt"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen-plus"

VALID_LEVELS = {"high", "med", "low"}
VALID_TYPES = {"single", "goal"}
VALID_ACTIONS = {"now", "schedule", "routine", "drop"}


def _api_key() -> str | None:
    env_key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("QWEN_API_KEY")
    if env_key:
        return env_key
    if SECRET_FILE.exists():
        return SECRET_FILE.read_text(encoding="utf-8").strip()
    return None


def _load_system_prompt(context: dict) -> str:
    text = PROMPT_PATH.read_text(encoding="utf-8")
    match = re.search(r"## System Prompt\n\n```\n(.*?)\n```", text, re.DOTALL)
    if not match:
        raise RuntimeError("triage_prompt.md: could not find the System Prompt code block")
    template = match.group(1)
    return (
        template
        .replace("{{focus}}", context["focus"])
        .replace("{{availability}}", context["availability"])
        .replace("{{open_count}}", str(context["open_count"]))
        .replace("{{open_summary}}", context["open_summary"])
    )


def get_user_context(conn) -> dict:
    profile = conn.execute(
        "SELECT focus, availability FROM user_profile WHERE user_id = 'bella'"
    ).fetchone()
    focus = (profile["focus"] if profile and profile["focus"] else None) or "未设置"
    availability = (profile["availability"] if profile and profile["availability"] else None) or "未设置"

    open_rows = conn.execute(
        "SELECT title FROM tasks WHERE status NOT IN ('done', 'dropped')"
    ).fetchall()
    open_count = len(open_rows)
    open_summary = "、".join(r["title"] for r in open_rows[:10]) or "无"

    return {
        "focus": focus,
        "availability": availability,
        "open_count": open_count,
        "open_summary": open_summary,
    }


def triage(text: str, context: dict) -> dict:
    """Call Qwen with the triage prompt and return the parsed, field-validated JSON."""
    api_key = _api_key()
    if not api_key:
        raise RuntimeError(
            "DASHSCOPE_API_KEY not configured (env var or .secrets/qwen_api_key.txt)"
        )

    client = OpenAI(api_key=api_key, base_url=BASE_URL)
    system_prompt = _load_system_prompt(context)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
        response_format={"type": "json_object"},
    )

    try:
        result = json.loads(response.choices[0].message.content)
    except (json.JSONDecodeError, IndexError, AttributeError) as exc:
        raise RuntimeError(f"Qwen returned unparseable output: {exc}") from exc

    return {
        "title": (result.get("title") or text).strip(),
        "notes": result.get("notes") or "",
        "category": result.get("category") or "",
        "type": result.get("type") if result.get("type") in VALID_TYPES else "single",
        "importance": result.get("importance") if result.get("importance") in VALID_LEVELS else None,
        "urgency": result.get("urgency") if result.get("urgency") in VALID_LEVELS else None,
        "action": result.get("action") if result.get("action") in VALID_ACTIONS else None,
        "needs_ask": result.get("needs_ask"),
        "reasoning": result.get("reasoning"),
    }

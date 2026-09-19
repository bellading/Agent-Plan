"""AI 问答: a conversational planning assistant via 通义千问 (Qwen), using
DashScope's OpenAI-compatible endpoint with tool calling. Replaces the old
one-shot triage prompt — the model now discusses a task with the user
(asking for missing timing, giving concrete suggestions) before it actually
creates/edits/deletes anything, by calling tools against tasks_repo.

Get an API key at https://bailian.console.aliyun.com/ (阿里云百炼/DashScope).
Save it either as:
  export DASHSCOPE_API_KEY=sk-...
or in .secrets/qwen_api_key.txt (gitignored, persists across terminal sessions).
"""

import json
import os
import re
import sqlite3
from pathlib import Path

from openai import OpenAI

import tasks_repo

CHAT_PROMPT_PATH = Path(__file__).parent / "prompts" / "chat_prompt.md"
SECRET_FILE = Path(__file__).parent / ".secrets" / "qwen_api_key.txt"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen-plus"
MAX_TOOL_ROUNDS = 5

VALID_LEVELS = {"high", "med", "low"}
VALID_TYPES = {"single", "goal"}
VALID_ACTIONS = {"now", "schedule", "routine", "drop"}
VALID_STATUSES = {"todo", "doing", "done", "missed", "routine", "dropped"}

TASK_PROPERTIES = {
    "title": {"type": "string", "description": "任务主题"},
    "notes": {"type": "string", "description": "备注，或目标型任务的计划详情"},
    "category": {"type": "string", "enum": tasks_repo.CATEGORIES},
    "type": {"type": "string", "enum": sorted(VALID_TYPES)},
    "importance": {"type": "string", "enum": sorted(VALID_LEVELS)},
    "urgency": {"type": "string", "enum": sorted(VALID_LEVELS)},
    "action": {"type": "string", "enum": sorted(VALID_ACTIONS)},
    "status": {"type": "string", "enum": sorted(VALID_STATUSES)},
    "remind_at": {"type": "string", "description": "提醒时间，格式 YYYY-MM-DD HH:MM"},
    "deadline": {"type": "string", "description": "截止时间，格式 YYYY-MM-DD HH:MM"},
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "在讨论清楚做什么、重要紧急程度、大概时间之后，创建一条新任务",
            "parameters": {
                "type": "object",
                "properties": TASK_PROPERTIES,
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_task",
            "description": "修改一条已有任务的部分字段。先用 list_open_tasks 确认 task_id",
            "parameters": {
                "type": "object",
                "properties": {"task_id": {"type": "integer"}, **TASK_PROPERTIES},
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_task",
            "description": "删除一条任务。先用 list_open_tasks 确认 task_id",
            "parameters": {
                "type": "object",
                "properties": {"task_id": {"type": "integer"}},
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_open_tasks",
            "description": "查看当前所有未完成任务（含 id、标题、分类等），用于修改/删除前定位任务",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def _api_key() -> str | None:
    env_key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("QWEN_API_KEY")
    if env_key:
        return env_key
    if SECRET_FILE.exists():
        return SECRET_FILE.read_text(encoding="utf-8").strip()
    return None


def _load_chat_prompt(context: dict) -> str:
    text = CHAT_PROMPT_PATH.read_text(encoding="utf-8")
    match = re.search(r"## System Prompt\n\n```\n(.*?)\n```", text, re.DOTALL)
    if not match:
        raise RuntimeError("chat_prompt.md: could not find the System Prompt code block")
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

    open_rows = tasks_repo.list_open_tasks(conn)
    open_count = len(open_rows)
    open_summary = "、".join(r["title"] for r in open_rows[:10]) or "无"

    return {
        "focus": focus,
        "availability": availability,
        "open_count": open_count,
        "open_summary": open_summary,
    }


def _sanitize_task_fields(args: dict) -> dict:
    fields = {k: v for k, v in args.items() if k in tasks_repo.TASK_FIELDS}
    if "type" in fields and fields["type"] not in VALID_TYPES:
        fields.pop("type")
    if "importance" in fields and fields["importance"] not in VALID_LEVELS:
        fields.pop("importance")
    if "urgency" in fields and fields["urgency"] not in VALID_LEVELS:
        fields.pop("urgency")
    if "action" in fields and fields["action"] not in VALID_ACTIONS:
        fields.pop("action")
    if "status" in fields and fields["status"] not in VALID_STATUSES:
        fields.pop("status")
    if "category" in fields and fields["category"] not in tasks_repo.CATEGORIES:
        fields["category"] = "其他"
    return fields


def _execute_tool(conn, name: str, args: dict) -> dict:
    try:
        if name == "create_task":
            title = (args.get("title") or "").strip()
            if not title:
                return {"error": "title is required"}
            fields = _sanitize_task_fields(args)
            fields["title"] = title
            new_id = tasks_repo.insert_task(conn, fields)
            return {"ok": True, "id": new_id}

        if name == "update_task":
            task_id = args.get("task_id")
            if task_id is None:
                return {"error": "task_id is required"}
            fields = _sanitize_task_fields(args)
            updated = tasks_repo.update_task(conn, int(task_id), fields)
            return {"ok": updated}

        if name == "delete_task":
            task_id = args.get("task_id")
            if task_id is None:
                return {"error": "task_id is required"}
            deleted = tasks_repo.delete_task(conn, int(task_id))
            return {"ok": deleted}

        if name == "list_open_tasks":
            return {"tasks": tasks_repo.list_open_tasks(conn)}

        return {"error": f"unknown tool: {name}"}
    except sqlite3.IntegrityError as exc:
        return {"error": str(exc)}


def chat_reply(conn, history: list[dict]) -> str:
    """history is the full message list (role/content dicts), ending with the
    latest user message. Returns the assistant's final natural-language reply,
    having executed any tool calls the model made along the way.
    """
    api_key = _api_key()
    if not api_key:
        raise RuntimeError(
            "DASHSCOPE_API_KEY not configured (env var or .secrets/qwen_api_key.txt)"
        )

    client = OpenAI(api_key=api_key, base_url=BASE_URL)
    context = get_user_context(conn)
    system_prompt = _load_chat_prompt(context)
    messages = [{"role": "system", "content": system_prompt}, *history]

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
        )
        message = response.choices[0].message

        if not message.tool_calls:
            return message.content or ""

        messages.append({
            "role": "assistant",
            "content": message.content,
            "tool_calls": [tc.model_dump() for tc in message.tool_calls],
        })
        for tool_call in message.tool_calls:
            try:
                args = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = _execute_tool(conn, tool_call.function.name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, ensure_ascii=False),
            })

    return "这次讨论有点绕，能再说一遍你想做什么吗？"

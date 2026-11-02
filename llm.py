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
MODEL = "qwen-max"
MAX_TOOL_ROUNDS = 5
MAX_TOKENS = 2000

# How long a trailing chunk of text has to be, and how many times it has to
# recur in the response so far, before we treat the model as stuck in a
# decoding repetition loop and cut the round short. 36 chars is roughly
# "这样可以吗？如果满意的话，要不要把这个加入计划表？" -- long enough that
# ordinary phrasing doesn't trip it, short enough to catch a loop within one
# or two repeats instead of letting it run to MAX_TOKENS.
LOOP_TAIL_LEN = 36
LOOP_TAIL_REPEATS = 2


def _is_repeating(text: str) -> bool:
    if len(text) < LOOP_TAIL_LEN * LOOP_TAIL_REPEATS:
        return False
    tail = text[-LOOP_TAIL_LEN:]
    return text.count(tail) >= LOOP_TAIL_REPEATS

# Appended as the generator's very last yield when the model has signaled
# (via the present_plan_for_confirmation / ask_add_to_plan tools below) that
# the frontend should show a pair of choice buttons after this message.
# Emitted by our own code, never by the model's free text, so it's a
# reliable marker — app.py strips it before persisting chat history.
ACTION_MARKER_RE = r"\[\[ACTION:(plan_confirm|add_confirm)\]\]"

VALID_LEVELS = {"high", "med", "low"}
VALID_TYPES = {"single", "goal"}
VALID_ACTIONS = {"now", "schedule", "routine", "drop"}
VALID_STATUSES = {"todo", "doing", "done", "missed", "routine", "dropped"}

def _task_properties(categories: list[str]) -> dict:
    return {
        "title": {"type": "string", "description": "任务主题"},
        "notes": {"type": "string", "description": "备注，或目标型任务的计划详情"},
        "category": {
            "type": "string",
            "enum": categories,
            "description": "只能是现有分类之一；新分类只能由用户在计划列表里手动添加，你不要自己发明新的",
        },
        "type": {"type": "string", "enum": sorted(VALID_TYPES)},
        "importance": {"type": "string", "enum": sorted(VALID_LEVELS)},
        "urgency": {"type": "string", "enum": sorted(VALID_LEVELS)},
        "action": {"type": "string", "enum": sorted(VALID_ACTIONS)},
        "status": {"type": "string", "enum": sorted(VALID_STATUSES)},
        "remind_at": {"type": "string", "description": "提醒时间，格式 YYYY-MM-DD HH:MM"},
        "deadline": {"type": "string", "description": "截止时间，格式 YYYY-MM-DD HH:MM"},
    }


def _build_tools(categories: list[str]) -> list[dict]:
    task_properties = _task_properties(categories)
    return [
        {
            "type": "function",
            "function": {
                "name": "create_task",
                "description": "在讨论清楚做什么、重要紧急程度、大概时间之后，创建一条新任务",
                "parameters": {
                    "type": "object",
                    "properties": task_properties,
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
                    "properties": {"task_id": {"type": "integer"}, **task_properties},
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
        {
            "type": "function",
            "function": {
                "name": "present_plan_for_confirmation",
                "description": (
                    "你已经整理出一份完整、具体的计划（可以是简单一件事，也可以是目标型的详细计划），"
                    "准备讲给用户听并询问她满不满意时调用这个工具（不需要参数）。重要：调用这个工具之前"
                    "不要先输出任何文字——不要先讲计划再调用，而是直接调用；完整的计划内容要放在调用"
                    "之后的下一段回复里讲清楚，这样才不会漏掉或者重复。注意：这一步绝不能同时调用 "
                    "create_task，要等用户确认。"
                ),
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ask_add_to_plan",
                "description": (
                    "用户已经明确表示对计划满意之后，你要询问'要不要把这个加入计划表'时调用这个工具"
                    "（不需要参数），然后在同一轮回复里用自然语言问她。"
                ),
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


def has_api_key() -> bool:
    return _api_key() is not None


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
        .replace("{{categories}}", "、".join(context["categories"]))
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
    categories = tasks_repo.list_categories(conn)

    return {
        "focus": focus,
        "availability": availability,
        "open_count": open_count,
        "open_summary": open_summary,
        "categories": categories,
    }


def _sanitize_task_fields(args: dict, categories: list[str]) -> dict:
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
    if "category" in fields and fields["category"] not in categories:
        fields["category"] = tasks_repo.FALLBACK_CATEGORY
    return fields


def _execute_tool(conn, name: str, args: dict, categories: list[str]) -> dict:
    try:
        if name == "create_task":
            title = (args.get("title") or "").strip()
            if not title:
                return {"error": "title is required"}
            fields = _sanitize_task_fields(args, categories)
            fields["title"] = title
            new_id = tasks_repo.insert_task(conn, fields)
            return {"ok": True, "id": new_id}

        if name == "update_task":
            task_id = args.get("task_id")
            if task_id is None:
                return {"error": "task_id is required"}
            fields = _sanitize_task_fields(args, categories)
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


def _last_action_type(conn) -> str | None:
    row = conn.execute(
        "SELECT action_type FROM chat_messages WHERE role = 'assistant' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return row["action_type"] if row else None


def chat_reply_stream(conn, history: list[dict]):
    """Generator yielding the assistant's reply text as it streams in.

    history is the full message list (role/content dicts), ending with the
    latest user message. Tool-calling rounds (the model deciding to
    create/update/delete/list tasks) are executed silently and never
    yielded — only the final natural-language answer streams out, so the
    caller can join everything yielded to get the complete reply text.

    The plan-confirm -> add-confirm -> create_task order is enforced here,
    not just requested in the prompt: ask_add_to_plan is rejected unless the
    most recent assistant turn was a plan_confirm, and create_task is
    rejected unless it was an add_confirm. A rejection comes back as a tool
    error the model can react to (e.g. call present_plan_for_confirmation
    properly) rather than silently letting it skip straight to creating
    something the user never actually confirmed.
    """
    api_key = _api_key()
    if not api_key:
        raise RuntimeError(
            "DASHSCOPE_API_KEY not configured (env var or .secrets/qwen_api_key.txt)"
        )

    client = OpenAI(api_key=api_key, base_url=BASE_URL)
    context = get_user_context(conn)
    system_prompt = _load_chat_prompt(context)
    tools = _build_tools(context["categories"])
    messages = [{"role": "system", "content": system_prompt}, *history]
    pending_action = None
    # Frozen at turn start — reflects what was true BEFORE this reply began,
    # and is never mutated while processing this turn's tool calls. This is
    # what keeps the model from chaining present_plan_for_confirmation and
    # ask_add_to_plan inside a single reply: the guard below must only trust
    # state the user's own prior turn actually established, not state this
    # turn just invented a moment ago.
    history_action_type = _last_action_type(conn)
    # True once ANY of the three confirmation-flow tools has been called
    # (successfully or not) during THIS turn. Blocks every further
    # confirmation-flow call in the same turn, independent of
    # history_action_type — this is what stops the model from re-presenting
    # the plan twice in one reply (history_action_type alone can't catch
    # that: calling present_plan_for_confirmation doesn't change it), and
    # also stops it from riding a stale plan_confirm/add_confirm left over
    # from an earlier, abandoned turn straight through to the next step
    # without the user ever actually replying in between.
    advanced_this_turn = False

    for _ in range(MAX_TOOL_ROUNDS):
        # Once a confirmation-flow step has happened this turn, stop handing
        # the model any tools at all for the rest of the reply. Otherwise a
        # rejected call (see advanced_this_turn below) doesn't make the
        # model give up — it just retries the same call next round, and
        # since each retry re-narrates the question first, that's what
        # turns into the same sentence repeating itself over and over until
        # MAX_TOOL_ROUNDS is hit. With no tools offered, it can only write
        # the closing text and stop, which is all it should be doing anyway
        # once a step has fired.
        stream = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=None if advanced_this_turn else tools,
            stream=True,
            temperature=0.2,
            max_tokens=MAX_TOKENS,
        )

        tool_calls_acc = {}
        content_parts = []

        for chunk in stream:
            delta = chunk.choices[0].delta
            if getattr(delta, "content", None):
                content_parts.append(delta.content)
                yield delta.content
                # Qwen occasionally free-wheels into a decoding repetition
                # loop once it has no tool call left to make (see
                # advanced_this_turn above) — it just keeps re-emitting the
                # same closing question forever instead of stopping. Cut the
                # round short the moment that's detected rather than riding
                # it out to MAX_TOKENS.
                if _is_repeating("".join(content_parts)):
                    break
            for tc in getattr(delta, "tool_calls", None) or []:
                entry = tool_calls_acc.setdefault(tc.index, {"id": None, "name": None, "arguments": ""})
                if tc.id:
                    entry["id"] = tc.id
                if tc.function and tc.function.name:
                    entry["name"] = tc.function.name
                if tc.function and tc.function.arguments:
                    entry["arguments"] += tc.function.arguments

        if not tool_calls_acc:
            if pending_action:
                yield f"\n[[ACTION:{pending_action}]]"
            return

        ordered_calls = [tool_calls_acc[i] for i in sorted(tool_calls_acc)]
        messages.append({
            "role": "assistant",
            "content": "".join(content_parts) or None,
            "tool_calls": [
                {
                    "id": call["id"],
                    "type": "function",
                    "function": {"name": call["name"], "arguments": call["arguments"]},
                }
                for call in ordered_calls
            ],
        })
        for call in ordered_calls:
            if call["name"] == "present_plan_for_confirmation":
                if advanced_this_turn:
                    result = {
                        "error": "这次回复里已经调用过确认流程的工具了，不要再重复调用、也不要把计划"
                                 "再完整写一遍——如果是因为上一个工具调用报错，就直接针对报错简短说明"
                                 "或者问清楚就好，不要重新展示计划。真正要重新展示计划，必须等用户发"
                                 "来新的一条消息之后，在那之后的回复里才能调用。",
                    }
                else:
                    pending_action = "plan_confirm"
                    advanced_this_turn = True
                    result = {"ok": True}

            elif call["name"] == "ask_add_to_plan":
                if advanced_this_turn or history_action_type != "plan_confirm":
                    result = {
                        "error": "顺序不对：还没有先调用 present_plan_for_confirmation 展示计划并"
                                 "得到用户在上一轮回复里明确表示满意，不能跳过这一步直接问是否加入，"
                                 "也不能在同一次回复里紧接着调用——必须先调用 "
                                 "present_plan_for_confirmation，然后到此为止，等用户发来新的一条"
                                 "消息明确表示满意之后，才能在那之后的回复里调用 ask_add_to_plan。",
                    }
                else:
                    pending_action = "add_confirm"
                    advanced_this_turn = True
                    result = {"ok": True}

            elif call["name"] == "create_task":
                if advanced_this_turn or history_action_type != "add_confirm":
                    result = {
                        "error": "顺序不对：还没有走完'展示计划→满意确认→询问是否加入'这个流程"
                                 "（用户还没有在单独一条新消息里明确说'加入'），不能直接创建任务，"
                                 "也不能在同一次回复里紧接着调用——必须等用户发来新的一条消息明确"
                                 "说'加入'之后，才能在那之后的回复里调用 create_task。",
                    }
                else:
                    advanced_this_turn = True
                    try:
                        args = json.loads(call["arguments"] or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    result = _execute_tool(conn, "create_task", args, context["categories"])

            else:
                try:
                    args = json.loads(call["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = _execute_tool(conn, call["name"], args, context["categories"])

            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": json.dumps(result, ensure_ascii=False),
            })

    yield "这次讨论有点绕，能再说一遍你想做什么吗？"

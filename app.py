"""AgentPlan v2: two-view web app (AI 问答 chat + 计划列表 by category)."""

import re
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

import llm
import tasks_repo
from db.init_db import get_conn, init_db

TZ = ZoneInfo("Asia/Shanghai")

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/tasks")
def list_tasks():
    conn = get_conn()
    tasks = tasks_repo.list_tasks(conn)
    conn.close()
    return jsonify(tasks)


@app.route("/api/tasks", methods=["POST"])
def create_task():
    data = request.get_json(force=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400

    task_type = data.get("type") or "single"
    if task_type not in ("single", "goal"):
        return jsonify({"error": "type must be 'single' or 'goal'"}), 400

    fields = {**data, "title": title, "type": task_type}
    conn = get_conn()
    try:
        new_id = tasks_repo.insert_task(conn, fields)
    except sqlite3.IntegrityError as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        conn.close()
    return jsonify({"ok": True, "id": new_id}), 201


@app.route("/api/tasks/<int:task_id>", methods=["PATCH"])
def update_task(task_id):
    data = request.get_json(force=True) or {}
    conn = get_conn()
    try:
        updated = tasks_repo.update_task(conn, task_id, data)
    except sqlite3.IntegrityError as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        conn.close()
    if not updated:
        return jsonify({"error": "no valid fields, or task not found"}), 400
    return jsonify({"ok": True})


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    conn = get_conn()
    deleted = tasks_repo.delete_task(conn, task_id)
    conn.close()
    if not deleted:
        return jsonify({"error": "task not found"}), 404
    return jsonify({"ok": True})


@app.route("/api/categories")
def list_categories():
    conn = get_conn()
    counts = tasks_repo.category_counts(conn)
    conn.close()
    return jsonify(counts)


@app.route("/api/categories", methods=["POST"])
def create_category():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    conn = get_conn()
    tasks_repo.add_category(conn, name)
    conn.close()
    return jsonify({"ok": True}), 201


@app.route("/api/conversations")
def list_conversations():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, title, created_at, updated_at FROM chat_conversations "
        "ORDER BY updated_at DESC, id DESC"
    ).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@app.route("/api/conversations", methods=["POST"])
def create_conversation():
    now_str = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO chat_conversations (title, created_at, updated_at) VALUES (NULL, ?, ?)",
        (now_str, now_str),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return jsonify({"id": new_id, "title": None, "created_at": now_str, "updated_at": now_str}), 201


@app.route("/api/chat/history")
def chat_history():
    conversation_id = request.args.get("conversation_id", type=int)
    if not conversation_id:
        return jsonify({"error": "conversation_id is required"}), 400
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, role, content, feedback, created_at FROM chat_messages "
        "WHERE conversation_id = ? ORDER BY id",
        (conversation_id,),
    ).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@app.route("/api/chat/<int:message_id>/feedback", methods=["POST"])
def set_chat_feedback(message_id):
    data = request.get_json(force=True) or {}
    feedback = data.get("feedback")
    if feedback not in ("up", "down", None):
        return jsonify({"error": "feedback must be 'up', 'down', or null"}), 400

    conn = get_conn()
    cur = conn.execute(
        "UPDATE chat_messages SET feedback = ? WHERE id = ? AND role = 'assistant'",
        (feedback, message_id),
    )
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        return jsonify({"error": "message not found"}), 404
    return jsonify({"ok": True})


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True) or {}
    text = (data.get("text") or "").strip()
    conversation_id = data.get("conversation_id")
    if not text:
        return jsonify({"error": "text is required"}), 400
    if not conversation_id:
        return jsonify({"error": "conversation_id is required"}), 400

    if not llm.has_api_key():
        return jsonify({
            "error": "DASHSCOPE_API_KEY not configured (env var or .secrets/qwen_api_key.txt)"
        }), 502

    conn = get_conn()
    conv_row = conn.execute(
        "SELECT id FROM chat_conversations WHERE id = ?", (conversation_id,)
    ).fetchone()
    if not conv_row:
        conn.close()
        return jsonify({"error": "conversation not found"}), 404

    history_rows = conn.execute(
        "SELECT role, content FROM chat_messages WHERE conversation_id = ? ORDER BY id",
        (conversation_id,),
    ).fetchall()
    history = [dict(row) for row in history_rows]
    history.append({"role": "user", "content": text})

    def generate():
        reply_parts = []
        try:
            for piece in llm.chat_reply_stream(conn, history, conversation_id):
                reply_parts.append(piece)
                yield piece
        except Exception as exc:
            error_text = f"（出错了：{exc}）"
            reply_parts.append(error_text)
            yield error_text
        finally:
            # strip the trailing [[ACTION:...]] marker before persisting —
            # it's a live UI signal for the just-streamed response, not
            # something that belongs in the saved conversation text. The
            # captured group is kept as action_type so chat_reply_stream can
            # enforce plan_confirm -> add_confirm -> create_task ordering on
            # the *next* turn without re-parsing stored text.
            raw_reply = "".join(reply_parts)
            match = re.search(llm.ACTION_MARKER_RE, raw_reply)
            action_type = match.group(1) if match else None
            reply_text = re.sub(r"\n?" + llm.ACTION_MARKER_RE + r"\s*$", "", raw_reply)
            now_str = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                "INSERT INTO chat_messages (role, content, conversation_id, created_at) "
                "VALUES ('user', ?, ?, ?)",
                (text, conversation_id, now_str),
            )
            conn.execute(
                "INSERT INTO chat_messages (role, content, action_type, conversation_id, created_at) "
                "VALUES ('assistant', ?, ?, ?, ?)",
                (reply_text, action_type, conversation_id, now_str),
            )
            # bump updated_at so this conversation floats to the top of the
            # branch list, and give it a title from the first real message
            # once it has one (COALESCE leaves an existing title alone).
            conn.execute(
                "UPDATE chat_conversations SET updated_at = ?, title = COALESCE(title, ?) "
                "WHERE id = ?",
                (now_str, text[:18], conversation_id),
            )
            conn.commit()
            conn.close()

    return Response(stream_with_context(generate()), mimetype="text/plain; charset=utf-8")


if __name__ == "__main__":
    init_db(seed=True)
    app.run(debug=True, port=5000)

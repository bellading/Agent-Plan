"""AgentPlan v2: two-view web app (AI 问答 chat + 计划列表 by category)."""

import sqlite3

from flask import Flask, jsonify, render_template, request

import llm
import tasks_repo
from db.init_db import get_conn, init_db

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


@app.route("/api/chat/history")
def chat_history():
    conn = get_conn()
    rows = conn.execute(
        "SELECT role, content, created_at FROM chat_messages ORDER BY id"
    ).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400

    conn = get_conn()
    history_rows = conn.execute(
        "SELECT role, content FROM chat_messages ORDER BY id"
    ).fetchall()
    history = [dict(row) for row in history_rows]
    history.append({"role": "user", "content": text})

    try:
        reply = llm.chat_reply(conn, history)
    except Exception as exc:
        conn.close()
        return jsonify({"error": str(exc)}), 502

    conn.execute(
        "INSERT INTO chat_messages (role, content) VALUES ('user', ?), ('assistant', ?)",
        (text, reply),
    )
    conn.commit()
    conn.close()

    return jsonify({"ok": True, "reply": reply})


if __name__ == "__main__":
    init_db(seed=True)
    app.run(debug=True, port=5000)

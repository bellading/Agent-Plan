"""AgentPlan v1 table page: read/update tasks in the SQLite DB from a browser."""

import sqlite3
from datetime import datetime

from flask import Flask, jsonify, render_template, request

import llm
from db.init_db import DB_PATH, get_conn, init_db

app = Flask(__name__)

EDITABLE_FIELDS = {
    "title", "notes", "category", "importance", "urgency",
    "action", "status", "remind_at", "deadline",
}


def _insert_task(conn, fields: dict) -> int:
    columns = ", ".join(fields)
    placeholders = ", ".join("?" for _ in fields)
    cur = conn.execute(
        f"INSERT INTO tasks ({columns}) VALUES ({placeholders})", list(fields.values())
    )
    conn.commit()
    return cur.lastrowid


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/tasks")
def list_tasks():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM tasks ORDER BY (status = 'done'), deadline IS NULL, deadline, remind_at"
    ).fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@app.route("/api/tasks", methods=["POST"])
def create_task():
    data = request.get_json(force=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400

    task_type = data.get("type") or "single"
    if task_type not in ("single", "goal"):
        return jsonify({"error": "type must be 'single' or 'goal'"}), 400

    fields = {
        "title": title,
        "notes": data.get("notes") or "",
        "category": data.get("category") or "",
        "type": task_type,
        "importance": data.get("importance") or None,
        "urgency": data.get("urgency") or None,
        "action": data.get("action") or None,
        "remind_at": data.get("remind_at") or None,
        "deadline": data.get("deadline") or None,
    }
    conn = get_conn()
    try:
        new_id = _insert_task(conn, fields)
    except sqlite3.IntegrityError as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        conn.close()
    return jsonify({"ok": True, "id": new_id}), 201


@app.route("/api/quick-add", methods=["POST"])
def quick_add():
    """Bot-style intake: one line of text in, AI-triaged task out."""
    data = request.get_json(force=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400

    conn = get_conn()
    try:
        context = llm.get_user_context(conn)
        result = llm.triage(text, context)
    except Exception as exc:
        conn.close()
        return jsonify({"error": str(exc)}), 502

    fields = {
        "title": result["title"],
        "notes": result["notes"],
        "category": result["category"],
        "type": result["type"],
        "importance": result["importance"],
        "urgency": result["urgency"],
        "action": result["action"],
        "remind_at": None,
        "deadline": None,
    }
    try:
        new_id = _insert_task(conn, fields)
    except sqlite3.IntegrityError as exc:
        conn.close()
        return jsonify({"error": str(exc)}), 400
    conn.close()

    return jsonify({
        "ok": True,
        "id": new_id,
        "needs_ask": result["needs_ask"],
        "reasoning": result["reasoning"],
    }), 201


@app.route("/api/tasks/<int:task_id>", methods=["PATCH"])
def update_task(task_id):
    data = request.get_json(force=True) or {}
    fields = {k: v for k, v in data.items() if k in EDITABLE_FIELDS}
    if not fields:
        return jsonify({"error": "no valid fields"}), 400

    if fields.get("status") == "done":
        fields["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elif "status" in fields:
        fields["completed_at"] = None

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    conn = get_conn()
    try:
        conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", [*fields.values(), task_id])
        conn.commit()
    except sqlite3.IntegrityError as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        conn.close()
    return jsonify({"ok": True})


if __name__ == "__main__":
    if not DB_PATH.exists():
        init_db(seed=True)
    app.run(debug=True, port=5000)

"""AgentPlan v1 table page: read/update tasks in the SQLite DB from a browser."""

import sqlite3
from datetime import datetime

from flask import Flask, jsonify, render_template, request

from db.init_db import DB_PATH, init_db

app = Flask(__name__)

EDITABLE_FIELDS = {
    "title", "notes", "category", "importance", "urgency",
    "action", "status", "remind_at", "deadline",
}


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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
    conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", [*fields.values(), task_id])
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


if __name__ == "__main__":
    if not DB_PATH.exists():
        init_db(seed=True)
    app.run(debug=True, port=5000)

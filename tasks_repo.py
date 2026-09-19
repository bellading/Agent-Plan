"""Shared task CRUD, used by both the REST endpoints (app.py) and the
AI chat's tool calls (llm.py) so there's exactly one insert/update/delete
implementation instead of two copies drifting apart.
"""

from datetime import datetime

TASK_FIELDS = {
    "title", "notes", "category", "type", "importance", "urgency",
    "action", "status", "remind_at", "deadline",
}

FALLBACK_CATEGORY = "其他"


def list_categories(conn) -> list[str]:
    rows = conn.execute("SELECT name FROM categories ORDER BY sort_order, id").fetchall()
    return [row["name"] for row in rows]


def add_category(conn, name: str) -> None:
    name = name.strip()
    if not name:
        raise ValueError("category name is required")
    next_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), 0) + 10 FROM categories WHERE sort_order < 999999"
    ).fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO categories (name, sort_order) VALUES (?, ?)", (name, next_order)
    )
    conn.commit()


def category_counts(conn) -> list[dict]:
    """Category tiles with task counts. Any task whose stored category isn't
    a known one (legacy data, or a category since renamed/removed) folds
    into 其他 rather than silently disappearing from every count.
    """
    categories = list_categories(conn)
    rows = conn.execute("SELECT category, COUNT(*) c FROM tasks GROUP BY category").fetchall()
    counts = {row["category"]: row["c"] for row in rows}

    result = []
    for name in categories:
        if name == FALLBACK_CATEGORY:
            continue
        result.append({"name": name, "count": counts.pop(name, 0)})
    result.append({"name": FALLBACK_CATEGORY, "count": counts.pop(FALLBACK_CATEGORY, 0) + sum(counts.values())})
    return result


def list_tasks(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM tasks ORDER BY (status = 'done'), deadline IS NULL, deadline, remind_at"
    ).fetchall()
    return [dict(row) for row in rows]


def list_open_tasks(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT id, title, category, importance, urgency, action, status, remind_at, deadline "
        "FROM tasks WHERE status NOT IN ('done', 'dropped') ORDER BY id"
    ).fetchall()
    return [dict(row) for row in rows]


def insert_task(conn, fields: dict) -> int:
    fields = {k: v for k, v in fields.items() if k in TASK_FIELDS}
    if not fields.get("type"):
        fields["type"] = "single"
    columns = ", ".join(fields)
    placeholders = ", ".join("?" for _ in fields)
    cur = conn.execute(
        f"INSERT INTO tasks ({columns}) VALUES ({placeholders})", list(fields.values())
    )
    conn.commit()
    return cur.lastrowid


def update_task(conn, task_id: int, fields: dict) -> bool:
    fields = {k: v for k, v in fields.items() if k in TASK_FIELDS}
    if not fields:
        return False

    if fields.get("status") == "done":
        fields["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elif "status" in fields:
        fields["completed_at"] = None

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    cur = conn.execute(
        f"UPDATE tasks SET {set_clause} WHERE id = ?", [*fields.values(), task_id]
    )
    conn.commit()
    return cur.rowcount > 0


def delete_task(conn, task_id: int) -> bool:
    cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    return cur.rowcount > 0

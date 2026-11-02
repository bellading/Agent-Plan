"""Shared task CRUD, used by both the REST endpoints (app.py) and the
AI chat's tool calls (llm.py) so there's exactly one insert/update/delete
implementation instead of two copies drifting apart.

Every function takes owner_id and scopes its query to it -- this is the
actual access-control boundary between different people's data, not just a
cosmetic filter, so update_task/delete_task in particular double as
ownership checks: an update or delete for a task that exists but belongs to
someone else matches zero rows, exactly like a task that doesn't exist.
"""

from datetime import datetime

TASK_FIELDS = {
    "title", "notes", "category", "type", "importance", "urgency",
    "action", "status", "remind_at", "deadline",
}

FALLBACK_CATEGORY = "其他"
DEFAULT_CATEGORIES = [("学习", 10), ("工作", 20), ("运动", 30), ("食物", 40), (FALLBACK_CATEGORY, 999999)]


def seed_default_categories(conn, owner_id: int) -> None:
    """Called once when a new account is created, so their 计划列表 grid
    isn't empty on first login. INSERT OR IGNORE so it's safe to call again
    without duplicating rows if it's ever invoked twice for the same owner.
    """
    conn.executemany(
        "INSERT OR IGNORE INTO categories (owner_id, name, sort_order) VALUES (?, ?, ?)",
        [(owner_id, name, order) for name, order in DEFAULT_CATEGORIES],
    )
    conn.commit()


def list_categories(conn, owner_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM categories WHERE owner_id = ? ORDER BY sort_order, id", (owner_id,)
    ).fetchall()
    return [row["name"] for row in rows]


def add_category(conn, owner_id: int, name: str) -> None:
    name = name.strip()
    if not name:
        raise ValueError("category name is required")
    next_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), 0) + 10 FROM categories WHERE owner_id = ? AND sort_order < 999999",
        (owner_id,),
    ).fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO categories (owner_id, name, sort_order) VALUES (?, ?, ?)",
        (owner_id, name, next_order),
    )
    conn.commit()


def category_counts(conn, owner_id: int) -> list[dict]:
    """Category tiles with task counts. Any task whose stored category isn't
    a known one (legacy data, or a category since renamed/removed) folds
    into 其他 rather than silently disappearing from every count.
    """
    categories = list_categories(conn, owner_id)
    rows = conn.execute(
        "SELECT category, COUNT(*) c FROM tasks WHERE owner_id = ? GROUP BY category", (owner_id,)
    ).fetchall()
    counts = {row["category"]: row["c"] for row in rows}

    result = []
    for name in categories:
        if name == FALLBACK_CATEGORY:
            continue
        result.append({"name": name, "count": counts.pop(name, 0)})
    result.append({"name": FALLBACK_CATEGORY, "count": counts.pop(FALLBACK_CATEGORY, 0) + sum(counts.values())})
    return result


def list_tasks(conn, owner_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM tasks WHERE owner_id = ? "
        "ORDER BY (status = 'done'), deadline IS NULL, deadline, remind_at",
        (owner_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def list_open_tasks(conn, owner_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, title, category, importance, urgency, action, status, remind_at, deadline "
        "FROM tasks WHERE owner_id = ? AND status NOT IN ('done', 'dropped') ORDER BY id",
        (owner_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def insert_task(conn, owner_id: int, fields: dict) -> int:
    fields = {k: v for k, v in fields.items() if k in TASK_FIELDS}
    if not fields.get("type"):
        fields["type"] = "single"
    fields["owner_id"] = owner_id
    columns = ", ".join(fields)
    placeholders = ", ".join("?" for _ in fields)
    cur = conn.execute(
        f"INSERT INTO tasks ({columns}) VALUES ({placeholders})", list(fields.values())
    )
    conn.commit()
    return cur.lastrowid


def update_task(conn, owner_id: int, task_id: int, fields: dict) -> bool:
    fields = {k: v for k, v in fields.items() if k in TASK_FIELDS}
    if not fields:
        return False

    if fields.get("status") == "done":
        fields["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    elif "status" in fields:
        fields["completed_at"] = None

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    cur = conn.execute(
        f"UPDATE tasks SET {set_clause} WHERE id = ? AND owner_id = ?",
        [*fields.values(), task_id, owner_id],
    )
    conn.commit()
    return cur.rowcount > 0


def delete_task(conn, owner_id: int, task_id: int) -> bool:
    cur = conn.execute("DELETE FROM tasks WHERE id = ? AND owner_id = ?", (task_id, owner_id))
    conn.commit()
    return cur.rowcount > 0

"""Reminder scheduler: polls the tasks table and pushes due reminders.

A 'routine' task (e.g. the daily SQL practice block) reschedules itself a
day later after firing, so one row keeps producing daily reminders. Any
other task fires once and is marked notified so it won't repeat until its
remind_at is changed (e.g. by editing it in the table page).
"""

import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from db.init_db import get_conn
from notifier import send_wechat

TZ = ZoneInfo("Asia/Shanghai")
POLL_INTERVAL_SECONDS = 60


def due_tasks(conn, now_str):
    return conn.execute(
        """
        SELECT * FROM tasks
        WHERE status NOT IN ('done', 'dropped')
          AND remind_at IS NOT NULL
          AND remind_at <= ?
          AND (snooze_until IS NULL OR snooze_until <= ?)
          AND (notified_at IS NULL OR notified_at < remind_at)
        """,
        (now_str, now_str),
    ).fetchall()


def bump_daily(remind_at: str) -> str:
    dt = datetime.strptime(remind_at, "%Y-%m-%d %H:%M")
    return (dt + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")


def tick() -> int:
    now_str = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    tasks = due_tasks(conn, now_str)

    sent_count = 0
    for t in tasks:
        title = f"提醒：{t['title']}"
        deadline_line = f"\n\n截止：{t['deadline']}" if t["deadline"] else ""
        content = f"{t['notes'] or ''}{deadline_line}".strip()

        if not send_wechat(title, content):
            continue
        sent_count += 1

        if t["action"] == "routine":
            conn.execute(
                "UPDATE tasks SET remind_at = ?, notified_at = NULL WHERE id = ?",
                (bump_daily(t["remind_at"]), t["id"]),
            )
        else:
            conn.execute(
                "UPDATE tasks SET notified_at = ? WHERE id = ?",
                (now_str, t["id"]),
            )

    conn.commit()
    conn.close()
    return sent_count


if __name__ == "__main__":
    print(f"AgentPlan scheduler started, polling every {POLL_INTERVAL_SECONDS}s (Ctrl+C to stop)")
    while True:
        try:
            n = tick()
            if n:
                print(f"[{datetime.now(TZ):%H:%M:%S}] sent {n} reminder(s)")
        except Exception as exc:  # keep polling even if one tick fails
            print("scheduler error:", exc)
        time.sleep(POLL_INTERVAL_SECONDS)

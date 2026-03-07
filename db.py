import json
import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parent / "retrace.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def clear_events() -> None:
    """Delete all events from the database."""
    with get_connection() as conn:
        conn.execute("DELETE FROM memory_events")
        conn.commit()


def init_db() -> None:
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                url TEXT NOT NULL,
                title TEXT,
                text TEXT,
                timestamp TEXT NOT NULL,
                metadata TEXT
            )
        """)
        conn.commit()


def insert_event(
    type: str,
    url: str,
    timestamp: str,
    title: str | None = None,
    text: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO memory_events (type, url, title, text, timestamp, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                type,
                url,
                title,
                text,
                timestamp,
                json.dumps(metadata) if metadata else None,
            ),
        )
        conn.commit()
        return cur.lastrowid


def list_events(limit: int = 100) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, type, url, title, text, timestamp, metadata FROM memory_events ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_event(r) for r in rows]


def get_event_by_id(event_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, type, url, title, text, timestamp, metadata FROM memory_events WHERE id = ?",
            (event_id,),
        ).fetchone()
    return _row_to_event(row) if row else None


def get_timeline(limit_days: int = 31) -> list[dict[str, Any]]:
    """Return events grouped by day. Each item: { "date": "YYYY-MM-DD", "events": [...] }. Most recent day first."""
    events = list_events(limit=500)
    by_date: dict[str, list[dict[str, Any]]] = {}
    for e in events:
        ts = e.get("timestamp") or ""
        date = ts.split("T")[0] if "T" in ts else ts[:10]
        if not date or len(date) < 10:
            continue
        by_date.setdefault(date, []).append(e)
    # Sort dates descending, cap number of days
    sorted_dates = sorted(by_date.keys(), reverse=True)[:limit_days]
    return [{"date": d, "events": by_date[d]} for d in sorted_dates]


def get_events_by_ids(event_ids: list[int]) -> list[dict[str, Any]]:
    """Return events for the given ids, in the same order. Skips missing ids."""
    if not event_ids:
        return []
    placeholders = ",".join("?" * len(event_ids))
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT id, type, url, title, text, timestamp, metadata FROM memory_events WHERE id IN ({placeholders})",
            event_ids,
        ).fetchall()
    by_id = {r["id"]: _row_to_event(r) for r in rows}
    return [by_id[eid] for eid in event_ids if eid in by_id]


def _row_to_event(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    if d.get("metadata"):
        d["metadata"] = json.loads(d["metadata"])
    return d

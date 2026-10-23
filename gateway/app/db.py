"""Очередь событий шлюза: входящие от интеграций и исходящие наружу."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

DB_PATH = os.environ.get("GATEWAY_DB", "/data/gateway.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    direction TEXT NOT NULL,
    external_id TEXT,
    chat_id TEXT NOT NULL,
    sender TEXT,
    sender_name TEXT,
    username TEXT,
    text TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_event_source_external
    ON event (source, external_id)
    WHERE external_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_event_pull
    ON event (direction, status, id);
"""

OUTBOUND_PENDING = "pending"
INBOUND_PENDING = "pending"
DONE = "delivered"
FAILED = "failed"


def connect() -> sqlite3.Connection:
    directory = os.path.dirname(DB_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Лёгкие миграции существующей базы шлюза."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(event)")}
    if "username" not in columns:
        conn.execute("ALTER TABLE event ADD COLUMN username TEXT")
        conn.commit()
    if "media" not in columns:
        # JSON-список вложений: [{"url": ...}] или [{"file_id": ...}] (Telegram)
        conn.execute("ALTER TABLE event ADD COLUMN media TEXT")
        conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_inbound(
    conn: sqlite3.Connection,
    *,
    source: str,
    external_id: Optional[str],
    chat_id: str,
    text: str,
    sender: Optional[str] = None,
    sender_name: Optional[str] = None,
    username: Optional[str] = None,
    occurred_at: Optional[str] = None,
    media: Optional[str] = None,
) -> Optional[int]:
    """Кладём входящее событие. None — уже было, дубль."""
    try:
        cursor = conn.execute(
            """
            INSERT INTO event (
                source, direction, external_id, chat_id, sender, sender_name,
                username, text, media, occurred_at, status, updated_at
            ) VALUES (?, 'inbound', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source,
                external_id,
                chat_id,
                sender,
                sender_name,
                username,
                text,
                media,
                occurred_at or _now(),
                INBOUND_PENDING,
                _now(),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    except sqlite3.IntegrityError:
        conn.rollback()
        return None


def resolve_chat(
    conn: sqlite3.Connection, source: str, username: str
) -> Optional[str]:
    """Последний открытый чат по нику пользователя (или по числовому id)."""
    key = (username or "").strip().lstrip("@")
    if not key:
        return None
    row = conn.execute(
        """
        SELECT chat_id FROM event
        WHERE source = ? AND direction = 'inbound'
          AND username IS NOT NULL AND username = ? COLLATE NOCASE
        ORDER BY id DESC LIMIT 1
        """,
        (source, key),
    ).fetchone()
    if row is None and key.lstrip("-").isdigit():
        row = conn.execute(
            """
            SELECT chat_id FROM event
            WHERE source = ? AND direction = 'inbound' AND chat_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (source, key),
        ).fetchone()
    return row["chat_id"] if row else None


def pull_inbound(conn: sqlite3.Connection, after_id: int, limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, source, chat_id, sender, sender_name, username, text, media, occurred_at
        FROM event
        WHERE direction = 'inbound' AND id > ?
        ORDER BY id
        LIMIT ?
        """,
        (after_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def enqueue_outbound(
    conn: sqlite3.Connection,
    *,
    source: str,
    chat_id: str,
    text: str,
    media: Optional[str] = None,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO event (
            source, direction, chat_id, text, media, occurred_at, status, updated_at
        ) VALUES (?, 'outbound', ?, ?, ?, ?, ?, ?)
        """,
        (source, chat_id, text, media, _now(), OUTBOUND_PENDING, _now()),
    )
    conn.commit()
    return int(cursor.lastrowid)


def next_outbound(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, source, chat_id, text, media, attempts
        FROM event
        WHERE direction = 'outbound' AND status = ?
        ORDER BY id
        LIMIT 1
        """,
        (OUTBOUND_PENDING,),
    ).fetchone()


def mark_sent(conn: sqlite3.Connection, event_id: int) -> None:
    conn.execute(
        "UPDATE event SET status = ?, updated_at = ?, last_error = NULL WHERE id = ?",
        (DONE, _now(), event_id),
    )
    conn.commit()


def mark_failed(conn: sqlite3.Connection, event_id: int, error: str, retryable: bool) -> None:
    conn.execute(
        """
        UPDATE event
        SET status = ?, attempts = attempts + 1, last_error = ?, updated_at = ?
        WHERE id = ?
        """,
        (FAILED if not retryable else OUTBOUND_PENDING, error[:500], _now(), event_id),
    )
    conn.commit()


def retry(conn: sqlite3.Connection, event_id: int) -> bool:
    cursor = conn.execute(
        "UPDATE event SET status = ?, attempts = 0, updated_at = ? WHERE id = ?",
        (OUTBOUND_PENDING, _now(), event_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def stats(conn: sqlite3.Connection) -> dict[str, int]:
    row = conn.execute(
        """
        SELECT
            SUM(CASE WHEN direction = 'inbound' AND status = 'pending' THEN 1 ELSE 0 END) AS inbound_pending,
            SUM(CASE WHEN direction = 'outbound' AND status = 'pending' THEN 1 ELSE 0 END) AS outbound_pending,
            SUM(CASE WHEN direction = 'outbound' AND status = 'failed' THEN 1 ELSE 0 END) AS outbound_failed,
            COUNT(*) AS total
        FROM event
        """
    ).fetchone()
    return {key: int(row[key] or 0) for key in row.keys()}

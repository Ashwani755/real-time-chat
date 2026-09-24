"""SQLite persistence helpers for chat messages.

This module deliberately has no FastAPI dependency. The backend can call these
functions from its own request or WebSocket handlers.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path(__file__).resolve().with_name("chat.db")


class DatabaseError(RuntimeError):
    """Raised when a chat database operation cannot be completed."""


def _normalise_path(db_path: str | Path | None) -> Path:
    return Path(db_path) if db_path is not None else DEFAULT_DB_PATH


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = _normalise_path(db_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection
    except (OSError, sqlite3.Error) as exc:
        raise DatabaseError(f"Could not connect to chat database: {path}") from exc


def init_db(db_path: str | Path | None = None) -> None:
    """Create the messages table when it does not already exist."""

    try:
        with closing(_connect(db_path)) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT NOT NULL,
                        message TEXT NOT NULL,
                        timestamp TEXT NOT NULL
                    )
                    """
                )
    except sqlite3.Error as exc:
        raise DatabaseError("Could not initialise the messages table") from exc


def _timestamp_text(timestamp: str | datetime) -> str:
    if isinstance(timestamp, datetime):
        return timestamp.isoformat()
    if isinstance(timestamp, str) and timestamp.strip():
        return timestamp
    raise ValueError("timestamp must be a non-empty ISO 8601 string or datetime")


def _validate_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _message_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "message_id": row["id"],
        "username": row["username"],
        "message": row["message"],
        "timestamp": row["timestamp"],
    }


def save_message(
    username: str,
    message: str,
    timestamp: str | datetime,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Store one message and return its WebSocket-ready representation."""

    clean_username = _validate_text(username, "username")
    clean_message = _validate_text(message, "message")
    clean_timestamp = _timestamp_text(timestamp)
    init_db(db_path)

    try:
        with closing(_connect(db_path)) as connection:
            with connection:
                cursor = connection.execute(
                    "INSERT INTO messages (username, message, timestamp) VALUES (?, ?, ?)",
                    (clean_username, clean_message, clean_timestamp),
                )
                message_id = cursor.lastrowid
    except sqlite3.Error as exc:
        raise DatabaseError("Could not save chat message") from exc

    return {
        "message_id": message_id,
        "username": clean_username,
        "message": clean_message,
        "timestamp": clean_timestamp,
    }


def get_messages(
    db_path: str | Path | None = None,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return saved messages oldest-first, optionally limited to the newest N."""

    if limit is not None and (
        not isinstance(limit, int) or isinstance(limit, bool) or limit < 1
    ):
        raise ValueError("limit must be a positive integer")
    init_db(db_path)

    try:
        with closing(_connect(db_path)) as connection:
            if limit is None:
                rows = connection.execute(
                    "SELECT id, username, message, timestamp FROM messages ORDER BY id"
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT id, username, message, timestamp
                    FROM (
                        SELECT id, username, message, timestamp
                        FROM messages ORDER BY id DESC LIMIT ?
                    )
                    ORDER BY id
                    """,
                    (limit,),
                ).fetchall()
    except sqlite3.Error as exc:
        raise DatabaseError("Could not retrieve chat history") from exc

    return [_message_dict(row) for row in rows]


def get_chat_history(
    db_path: str | Path | None = None,
    *,
    limit: int | None = None,
) -> dict[str, Any]:
    """Return a complete chat-history payload for a WebSocket client."""

    return {
        "type": "chat_history",
        "data": {"messages": get_messages(db_path, limit=limit)},
    }

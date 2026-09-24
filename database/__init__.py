"""Public SQLite persistence API for chat messages."""

from .chat import DatabaseError, get_chat_history, get_messages, init_db, save_message

__all__ = [
    "DatabaseError",
    "get_chat_history",
    "get_messages",
    "init_db",
    "save_message",
]

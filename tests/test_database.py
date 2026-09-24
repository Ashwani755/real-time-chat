import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime
from pathlib import Path

from backend.database import (
    DatabaseError,
    get_chat_history,
    get_messages,
    init_db,
    save_message,
)


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test-chat.db"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_init_db_creates_expected_table(self) -> None:
        init_db(self.db_path)
        with closing(sqlite3.connect(self.db_path)) as connection:
            columns = connection.execute("PRAGMA table_info(messages)").fetchall()

        self.assertEqual(
            [column[1] for column in columns],
            ["id", "username", "message", "timestamp"],
        )

    def test_save_and_get_messages_in_websocket_format(self) -> None:
        first = save_message("Alice", "Hello!", "2026-09-22T14:30:00", self.db_path)
        second = save_message(
            "Bob", "Hi Alice", datetime(2026, 9, 22, 14, 31), self.db_path
        )

        self.assertEqual(first["message_id"], 1)
        self.assertEqual(get_messages(self.db_path), [first, second])
        self.assertEqual(
            get_chat_history(self.db_path),
            {"type": "chat_history", "data": {"messages": [first, second]}},
        )

    def test_limit_returns_newest_messages_in_chronological_order(self) -> None:
        for number in range(3):
            save_message(
                "Alice",
                f"Message {number}",
                f"2026-09-22T14:3{number}:00",
                self.db_path,
            )

        self.assertEqual(
            [item["message_id"] for item in get_messages(self.db_path, limit=2)],
            [2, 3],
        )

    def test_rejects_empty_values(self) -> None:
        with self.assertRaises(ValueError):
            save_message("", "Hello", "2026-09-22T14:30:00", self.db_path)

    def test_schema_error_is_wrapped(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("CREATE TABLE messages (wrong_column TEXT)")
            connection.commit()

        with self.assertRaises(DatabaseError):
            get_messages(self.db_path)


if __name__ == "__main__":
    unittest.main()

"""
WebSocket Connection Manager.

Manages active WebSocket connections, handles message broadcasting,
user tracking (online users), and provides integration hooks for SQLite
and MQTT services (to be integrated by Member 3).
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional
from fastapi import WebSocket

logger = logging.getLogger("websocket_manager")


class ConnectionManager:
    """Manages active WebSocket connections and broadcasting."""

    def __init__(self) -> None:
        # Map of username -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()
        self._message_counter: int = 100

        # Extension hooks for Member 3 (SQLite & MQTT)
        self.message_handlers: List[Callable[[str, str, int, str], Coroutine[Any, Any, None]]] = []
        self.user_join_handlers: List[Callable[[str, str], Coroutine[Any, Any, None]]] = []
        self.user_leave_handlers: List[Callable[[str, str], Coroutine[Any, Any, None]]] = []

    def next_message_id(self) -> int:
        """Generate an auto-incrementing message ID."""
        self._message_counter += 1
        return self._message_counter

    @staticmethod
    def get_timestamp() -> str:
        """Return the current local timestamp in ISO format (YYYY-MM-DDTHH:MM:SS)."""
        return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    async def connect(self, websocket: WebSocket, username: str) -> bool:
        """
        Accept a WebSocket connection and register the user.
        Returns True if registration succeeds, False if the username is taken.
        """
        async with self._lock:
            if username in self.active_connections:
                logger.warning("Username '%s' is already connected.", username)
                return False

            await websocket.accept()
            self.active_connections[username] = websocket
            logger.info("User '%s' connected. Active users: %d", username, len(self.active_connections))
            return True

    async def disconnect(self, username: str) -> None:
        """Remove a user from active connections."""
        async with self._lock:
            if username in self.active_connections:
                del self.active_connections[username]
                logger.info("User '%s' disconnected. Active users: %d", username, len(self.active_connections))

    def is_user_online(self, username: str) -> bool:
        """Check whether a username is currently online."""
        return username in self.active_connections

    def get_online_users(self) -> List[str]:
        """Return a sorted list of usernames currently connected."""
        return sorted(list(self.active_connections.keys()))

    async def send_personal_message(self, message: Dict[str, Any], websocket: WebSocket) -> None:
        """Send a JSON message to a specific WebSocket client."""
        try:
            await websocket.send_json(message)
        except Exception as exc:
            logger.error("Failed to send personal message: %s", exc)

    async def send_to_user(self, username: str, message: Dict[str, Any]) -> bool:
        """Send a JSON message to a user by username."""
        ws = self.active_connections.get(username)
        if ws:
            await self.send_personal_message(message, ws)
            return True
        return False

    async def broadcast(self, message: Dict[str, Any], exclude_username: Optional[str] = None) -> None:
        """
        Broadcast a JSON message to all connected clients.
        If exclude_username is provided, skip that user.
        Dead connections are cleaned up automatically.
        """
        disconnected_users = []

        async with self._lock:
            targets = list(self.active_connections.items())

        for user, ws in targets:
            if exclude_username and user == exclude_username:
                continue
            try:
                await ws.send_json(message)
            except Exception as exc:
                logger.warning("Error broadcasting to '%s': %s. Marking for cleanup.", user, exc)
                disconnected_users.append(user)

        if disconnected_users:
            async with self._lock:
                for user in disconnected_users:
                    if user in self.active_connections:
                        del self.active_connections[user]

    # ---------------------------------------------------------
    # Extensibility Hooks for Member 3 (SQLite / MQTT Integration)
    # ---------------------------------------------------------
    def register_on_message(self, handler: Callable[[str, str, int, str], Coroutine[Any, Any, None]]) -> None:
        """
        Register a callback for chat messages.
        Signature: async def handler(username: str, message: str, message_id: int, timestamp: str) -> None
        """
        self.message_handlers.append(handler)

    def register_on_user_join(self, handler: Callable[[str, str], Coroutine[Any, Any, None]]) -> None:
        """
        Register a callback when a user joins.
        Signature: async def handler(username: str, timestamp: str) -> None
        """
        self.user_join_handlers.append(handler)

    def register_on_user_leave(self, handler: Callable[[str, str], Coroutine[Any, Any, None]]) -> None:
        """
        Register a callback when a user leaves.
        Signature: async def handler(username: str, timestamp: str) -> None
        """
        self.user_leave_handlers.append(handler)

    async def trigger_on_message(self, username: str, message: str, message_id: int, timestamp: str) -> None:
        """Execute registered message hooks asynchronously (non-blocking)."""
        for handler in self.message_handlers:
            try:
                asyncio.create_task(handler(username, message, message_id, timestamp))
            except Exception as exc:
                logger.error("Error executing message hook: %s", exc)

    async def trigger_on_user_join(self, username: str, timestamp: str) -> None:
        """Execute registered join hooks asynchronously (non-blocking)."""
        for handler in self.user_join_handlers:
            try:
                asyncio.create_task(handler(username, timestamp))
            except Exception as exc:
                logger.error("Error executing join hook: %s", exc)

    async def trigger_on_user_leave(self, username: str, timestamp: str) -> None:
        """Execute registered leave hooks asynchronously (non-blocking)."""
        for handler in self.user_leave_handlers:
            try:
                asyncio.create_task(handler(username, timestamp))
            except Exception as exc:
                logger.error("Error executing leave hook: %s", exc)


# Global singleton instance for easy import across the backend
manager = ConnectionManager()

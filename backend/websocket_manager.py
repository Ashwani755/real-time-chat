"""
WebSocket Connection Manager.

Manages active WebSocket connections across rooms, handles message broadcasting,
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
    """Manages active WebSocket connections, multi-room partitioning, and broadcasting."""

    def __init__(self) -> None:
        # Map of room_name -> { username -> WebSocket }
        self.rooms: Dict[str, Dict[str, WebSocket]] = {}
        # Legacy/direct dictionary for backward compatibility with tests and single-room access
        self.active_connections: Dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()
        self._message_counter: int = 100

        # Extension hooks for Member 3 (SQLite & MQTT)
        self.message_handlers: List[Callable[..., Coroutine[Any, Any, None]]] = []
        self.user_join_handlers: List[Callable[..., Coroutine[Any, Any, None]]] = []
        self.user_leave_handlers: List[Callable[..., Coroutine[Any, Any, None]]] = []

    def clear(self) -> None:
        """Clear all connections and hooks (useful for testing resets)."""
        self.rooms.clear()
        self.active_connections.clear()
        self.message_handlers.clear()
        self.user_join_handlers.clear()
        self.user_leave_handlers.clear()

    def next_message_id(self) -> int:
        """Generate an auto-incrementing message ID."""
        self._message_counter += 1
        return self._message_counter

    @staticmethod
    def get_timestamp() -> str:
        """Return the current local timestamp in ISO format (YYYY-MM-DDTHH:MM:SS)."""
        return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    async def connect(self, websocket: WebSocket, username: str, room: str = "general") -> bool:
        """
        Accept a WebSocket connection and register the user in a room.
        Returns True if registration succeeds, False if the username is taken in that room.
        """
        async with self._lock:
            room_dict = self.rooms.setdefault(room, {})
            if username in room_dict:
                logger.warning("Username '%s' is already connected to room '%s'.", username, room)
                return False

            await websocket.accept()
            room_dict[username] = websocket
            if room == "general":
                self.active_connections[username] = websocket

            logger.info("User '%s' connected to room '%s'. Room active users: %d", username, room, len(room_dict))
            return True

    async def disconnect(self, username: str, room: str = "general") -> None:
        """Remove a user from active connections in a room."""
        async with self._lock:
            room_dict = self.rooms.get(room)
            if room_dict and username in room_dict:
                del room_dict[username]
                if not room_dict and room != "general":
                    del self.rooms[room]
                logger.info("User '%s' disconnected from room '%s'.", username, room)

            if room == "general" and username in self.active_connections:
                del self.active_connections[username]

    def is_user_online(self, username: str, room: str = "general") -> bool:
        """Check whether a username is currently online in a room."""
        room_dict = self.rooms.get(room)
        if room_dict:
            return username in room_dict
        return False

    def get_online_users(self, room: str = "general") -> List[str]:
        """Return a sorted list of usernames currently connected to a room."""
        room_dict = self.rooms.get(room, {})
        return sorted(list(room_dict.keys()))

    def get_all_online_users(self) -> List[str]:
        """Return a sorted list of all unique connected users across all rooms."""
        all_users = set()
        for r_dict in self.rooms.values():
            all_users.update(r_dict.keys())
        return sorted(list(all_users))

    async def send_personal_message(self, message: Dict[str, Any], websocket: WebSocket) -> None:
        """Send a JSON message to a specific WebSocket client."""
        try:
            await websocket.send_json(message)
        except Exception as exc:
            logger.error("Failed to send personal message: %s", exc)

    async def send_to_user(self, username: str, message: Dict[str, Any], room: str = "general") -> bool:
        """Send a JSON message to a specific user in a room."""
        room_dict = self.rooms.get(room, {})
        ws = room_dict.get(username)
        if ws:
            await self.send_personal_message(message, ws)
            return True
        return False

    async def broadcast(self, message: Dict[str, Any], room: str = "general", exclude_username: Optional[str] = None) -> None:
        """
        Broadcast a JSON message to all connected clients in a specific room.
        If exclude_username is provided, skip that user.
        Dead connections are cleaned up automatically.
        """
        disconnected_users = []

        async with self._lock:
            room_dict = self.rooms.get(room, {})
            targets = list(room_dict.items())

        for user, ws in targets:
            if exclude_username and user == exclude_username:
                continue
            try:
                await ws.send_json(message)
            except Exception as exc:
                logger.warning("Error broadcasting to '%s' in room '%s': %s. Marking for cleanup.", user, room, exc)
                disconnected_users.append(user)

        if disconnected_users:
            async with self._lock:
                room_dict = self.rooms.get(room)
                if room_dict:
                    for user in disconnected_users:
                        if user in room_dict:
                            del room_dict[user]
                        if room == "general" and user in self.active_connections:
                            del self.active_connections[user]

    # ---------------------------------------------------------
    # Extensibility Hooks for Member 3 (SQLite / MQTT Integration)
    # ---------------------------------------------------------
    def register_on_message(self, handler: Callable[..., Coroutine[Any, Any, None]]) -> None:
        """
        Register a callback for chat messages.
        Signature: async def handler(username: str, message: str, message_id: int, timestamp: str, room: str = "general") -> None
        """
        self.message_handlers.append(handler)

    def register_on_user_join(self, handler: Callable[..., Coroutine[Any, Any, None]]) -> None:
        """
        Register a callback when a user joins.
        Signature: async def handler(username: str, timestamp: str, room: str = "general") -> None
        """
        self.user_join_handlers.append(handler)

    def register_on_user_leave(self, handler: Callable[..., Coroutine[Any, Any, None]]) -> None:
        """
        Register a callback when a user leaves.
        Signature: async def handler(username: str, timestamp: str, room: str = "general") -> None
        """
        self.user_leave_handlers.append(handler)

    async def trigger_on_message(self, username: str, message: str, message_id: int, timestamp: str, room: str = "general") -> None:
        """Execute registered message hooks asynchronously (non-blocking)."""
        for handler in self.message_handlers:
            try:
                # Support both 4-arg and 5-arg (with room) signatures
                try:
                    asyncio.create_task(handler(username, message, message_id, timestamp, room))
                except TypeError:
                    asyncio.create_task(handler(username, message, message_id, timestamp))
            except Exception as exc:
                logger.error("Error executing message hook: %s", exc)

    async def trigger_on_user_join(self, username: str, timestamp: str, room: str = "general") -> None:
        """Execute registered join hooks asynchronously (non-blocking)."""
        for handler in self.user_join_handlers:
            try:
                try:
                    asyncio.create_task(handler(username, timestamp, room))
                except TypeError:
                    asyncio.create_task(handler(username, timestamp))
            except Exception as exc:
                logger.error("Error executing join hook: %s", exc)

    async def trigger_on_user_leave(self, username: str, timestamp: str, room: str = "general") -> None:
        """Execute registered leave hooks asynchronously (non-blocking)."""
        for handler in self.user_leave_handlers:
            try:
                try:
                    asyncio.create_task(handler(username, timestamp, room))
                except TypeError:
                    asyncio.create_task(handler(username, timestamp))
            except Exception as exc:
                logger.error("Error executing leave hook: %s", exc)


# Global singleton instance for easy import across the backend
manager = ConnectionManager()

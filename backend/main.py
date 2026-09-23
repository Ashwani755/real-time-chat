"""
FastAPI Backend Server for Real-Time Chat Application.

Provides:
- HTTP endpoints: Health check, API info, online users query.
- Static file serving for Frontend (index.html, rooms.html, style.css, app.js, rooms.js).
- CORS middleware for cross-origin frontend testing.
- WebSocket endpoints:
  - /ws/{username}: Primary global chat endpoint.
  - /ws/{room}/{username}: Multi-room partitioned chat endpoint.
"""

import json
import logging
import os
from typing import Any, Dict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

from backend.websocket_manager import manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("backend.main")

app = FastAPI(
    title="Real-Time Chat Application Backend",
    description="FastAPI WebSocket backend for real-time team chat",
    version="1.0.0"
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------------------------------------
# REST API Endpoints
# -------------------------------------------------------------
@app.get("/api")
@app.get("/api/status")
async def api_status() -> Dict[str, Any]:
    """API metadata and status endpoint."""
    return {
        "service": "Real-Time Chat Backend",
        "status": "running",
        "endpoints": {
            "global_websocket": "/ws/{username}",
            "room_websocket": "/ws/{room}/{username}",
            "health": "/health",
            "online_users": "/online-users",
            "docs": "/docs"
        }
    }


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/online-users")
async def get_online_users(room: str = "general") -> Dict[str, Any]:
    """Query currently connected users for a room (or all rooms)."""
    clean_room = room.strip().replace("#", "").lower()
    users = manager.get_online_users(clean_room)
    return {
        "room": clean_room,
        "users": users,
        "count": len(users),
        "total_all_rooms": len(manager.get_all_online_users())
    }


# -------------------------------------------------------------
# WebSocket Core Handler
# -------------------------------------------------------------
async def handle_chat_session(websocket: WebSocket, username: str, room: str = "general") -> None:
    """Core WebSocket handler supporting both single-room and multi-room connections."""
    clean_username = username.strip()
    clean_room = room.strip().replace("#", "").lower() or "general"

    # 1. Validate username
    if not clean_username:
        await websocket.accept()
        await manager.send_personal_message({
            "type": "error",
            "data": {
                "code": "INVALID_USERNAME",
                "message": "Username cannot be empty or blank."
            }
        }, websocket)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Check for duplicate username in this room
    if manager.is_user_online(clean_username, clean_room):
        await websocket.accept()
        await manager.send_personal_message({
            "type": "error",
            "data": {
                "code": "USERNAME_TAKEN",
                "message": f"Username '{clean_username}' is already in use in room '{clean_room}'."
            }
        }, websocket)
        await websocket.close(code=4001, reason="Username already taken")
        return

    # 2. Connect user to room
    connected = await manager.connect(websocket, clean_username, clean_room)
    if not connected:
        return

    join_timestamp = manager.get_timestamp()
    is_connected = True

    try:
        # Send initial state to the newly connected user
        await manager.send_personal_message({
            "type": "online_users",
            "data": {
                "room": clean_room,
                "users": manager.get_online_users(clean_room)
            }
        }, websocket)

        # Send empty chat history placeholder (for Member 3 SQLite integration)
        await manager.send_personal_message({
            "type": "chat_history",
            "data": {
                "room": clean_room,
                "messages": []
            }
        }, websocket)

        # Broadcast user_joined notification to room
        await manager.broadcast({
            "type": "user_joined",
            "data": {
                "room": clean_room,
                "username": clean_username,
                "timestamp": join_timestamp
            }
        }, room=clean_room)

        # Broadcast updated online_users to room
        await manager.broadcast({
            "type": "online_users",
            "data": {
                "room": clean_room,
                "users": manager.get_online_users(clean_room)
            }
        }, room=clean_room)

        # Trigger join hook for Member 3
        await manager.trigger_on_user_join(clean_username, join_timestamp, clean_room)

        # 3. Message loop
        while True:
            data_str = await websocket.receive_text()

            # Parse JSON
            try:
                payload = json.loads(data_str)
            except (json.JSONDecodeError, TypeError):
                await manager.send_personal_message({
                    "type": "error",
                    "data": {
                        "code": "INVALID_JSON",
                        "message": "Malformed JSON payload."
                    }
                }, websocket)
                continue

            # Validate basic payload structure
            if not isinstance(payload, dict) or "type" not in payload:
                await manager.send_personal_message({
                    "type": "error",
                    "data": {
                        "code": "INVALID_FORMAT",
                        "message": "Payload must be a JSON object with a 'type' field."
                    }
                }, websocket)
                continue

            msg_type = payload.get("type")

            # Handle Chat Message
            if msg_type == "chat_message":
                data = payload.get("data")
                if not isinstance(data, dict):
                    await manager.send_personal_message({
                        "type": "error",
                        "data": {
                            "code": "INVALID_MESSAGE",
                            "message": "Chat message data must be a JSON object."
                        }
                    }, websocket)
                    continue

                raw_msg = data.get("message")
                if not isinstance(raw_msg, str) or not raw_msg.strip():
                    await manager.send_personal_message({
                        "type": "error",
                        "data": {
                            "code": "INVALID_MESSAGE",
                            "message": "Message cannot be empty."
                        }
                    }, websocket)
                    continue

                clean_msg = raw_msg.strip()
                msg_id = manager.next_message_id()
                msg_timestamp = manager.get_timestamp()

                chat_response = {
                    "type": "chat_message",
                    "data": {
                        "message_id": msg_id,
                        "room": clean_room,
                        "username": clean_username,
                        "message": clean_msg,
                        "timestamp": msg_timestamp
                    }
                }

                # Broadcast to all connected users in this room
                await manager.broadcast(chat_response, room=clean_room)

                # Trigger message hook for Member 3 (SQLite / MQTT)
                await manager.trigger_on_message(clean_username, clean_msg, msg_id, msg_timestamp, clean_room)

            # Handle explicit Join event
            elif msg_type == "join":
                await manager.send_personal_message({
                    "type": "online_users",
                    "data": {
                        "room": clean_room,
                        "users": manager.get_online_users(clean_room)
                    }
                }, websocket)

            # Handle Leave event
            elif msg_type == "leave":
                logger.info("User '%s' requested to leave room '%s'.", clean_username, clean_room)
                break

            # Handle Unknown Type
            else:
                await manager.send_personal_message({
                    "type": "error",
                    "data": {
                        "code": "UNKNOWN_TYPE",
                        "message": f"Unknown message type '{msg_type}'."
                    }
                }, websocket)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnect detected for user '%s' in room '%s'.", clean_username, clean_room)
    except Exception as exc:
        logger.error("Unexpected error in websocket for '%s' (room '%s'): %s", clean_username, clean_room, exc)
    finally:
        if is_connected:
            await manager.disconnect(clean_username, clean_room)
            leave_timestamp = manager.get_timestamp()

            # Broadcast user_left notification to room
            await manager.broadcast({
                "type": "user_left",
                "data": {
                    "room": clean_room,
                    "username": clean_username,
                    "timestamp": leave_timestamp
                }
            }, room=clean_room)

            # Broadcast updated online_users list to room
            await manager.broadcast({
                "type": "online_users",
                "data": {
                    "room": clean_room,
                    "users": manager.get_online_users(clean_room)
                }
            }, room=clean_room)

            # Trigger leave hook for Member 3
            await manager.trigger_on_user_leave(clean_username, leave_timestamp, clean_room)


# -------------------------------------------------------------
# WebSocket Endpoints
# -------------------------------------------------------------
@app.websocket("/ws/{username}")
async def websocket_global_endpoint(websocket: WebSocket, username: str) -> None:
    """Primary WebSocket endpoint: ws://localhost:8000/ws/{username}."""
    await handle_chat_session(websocket, username=username, room="general")


@app.websocket("/ws/{room}/{username}")
async def websocket_room_endpoint(websocket: WebSocket, room: str, username: str) -> None:
    """Multi-room WebSocket endpoint: ws://localhost:8000/ws/{room}/{username}."""
    await handle_chat_session(websocket, username=username, room=room)


# -------------------------------------------------------------
# Mount Frontend Static Files
# -------------------------------------------------------------
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    logger.info("Frontend static files mounted from: %s", frontend_dir)


def start() -> None:
    """Run backend with uvicorn on http://127.0.0.1:8000."""
    print("=" * 60)
    print("  Real-Time Chat Server Starting")
    print("  Open in your browser: http://localhost:8000")
    print("  Multi-room UI:        http://localhost:8000/rooms.html")
    print("  WebSocket Endpoint:   ws://localhost:8000/ws/{username}")
    print("=" * 60)
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    start()

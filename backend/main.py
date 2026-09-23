"""
FastAPI Backend Server for Real-Time Chat Application.

Provides:
- HTTP endpoints: Health check, root info, online users query.
- CORS middleware for frontend development.
- WebSocket endpoint: /ws/{username} handling real-time messaging,
  user presence (join/leave), online user lists, message validation,
  and error reporting.
"""

import json
import logging
from typing import Any, Dict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
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

# Enable CORS for frontend integration (Member 2)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> Dict[str, Any]:
    """Root endpoint providing service information."""
    return {
        "service": "Real-Time Chat Backend",
        "status": "running",
        "websocket_endpoint": "/ws/{username}",
        "docs_url": "/docs"
    }


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/online-users")
async def get_online_users() -> Dict[str, Any]:
    """Query currently connected users."""
    users = manager.get_online_users()
    return {
        "users": users,
        "count": len(users)
    }


@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str) -> None:
    """
    WebSocket endpoint for real-time chat.
    ws://localhost:8000/ws/{username}
    """
    clean_username = username.strip()

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

    # Check for duplicate username
    if manager.is_user_online(clean_username):
        await websocket.accept()
        await manager.send_personal_message({
            "type": "error",
            "data": {
                "code": "USERNAME_TAKEN",
                "message": f"Username '{clean_username}' is already in use."
            }
        }, websocket)
        await websocket.close(code=4001, reason="Username already taken")
        return

    # 2. Connect user
    connected = await manager.connect(websocket, clean_username)
    if not connected:
        return

    join_timestamp = manager.get_timestamp()
    is_connected = True

    try:
        # Send initial state to the newly connected user
        await manager.send_personal_message({
            "type": "online_users",
            "data": {
                "users": manager.get_online_users()
            }
        }, websocket)

        # Send empty chat history placeholder (for Member 3 SQLite integration)
        await manager.send_personal_message({
            "type": "chat_history",
            "data": {
                "messages": []
            }
        }, websocket)

        # Broadcast user_joined notification to all users
        await manager.broadcast({
            "type": "user_joined",
            "data": {
                "username": clean_username,
                "timestamp": join_timestamp
            }
        })

        # Broadcast updated online_users to all connected users
        await manager.broadcast({
            "type": "online_users",
            "data": {
                "users": manager.get_online_users()
            }
        })

        # Trigger join hook for Member 3
        await manager.trigger_on_user_join(clean_username, join_timestamp)

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
                        "username": clean_username,
                        "message": clean_msg,
                        "timestamp": msg_timestamp
                    }
                }

                # Broadcast to all connected users
                await manager.broadcast(chat_response)

                # Trigger message hook for Member 3 (SQLite / MQTT)
                await manager.trigger_on_message(clean_username, clean_msg, msg_id, msg_timestamp)

            # Handle explicit Join event
            elif msg_type == "join":
                # Acknowledge and send current online users
                await manager.send_personal_message({
                    "type": "online_users",
                    "data": {
                        "users": manager.get_online_users()
                    }
                }, websocket)

            # Handle Leave event
            elif msg_type == "leave":
                logger.info("User '%s' requested to leave.", clean_username)
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
        logger.info("WebSocket disconnect detected for user '%s'.", clean_username)
    except Exception as exc:
        logger.error("Unexpected error in websocket connection for '%s': %s", clean_username, exc)
    finally:
        if is_connected:
            await manager.disconnect(clean_username)
            leave_timestamp = manager.get_timestamp()

            # Broadcast user_left notification
            await manager.broadcast({
                "type": "user_left",
                "data": {
                    "username": clean_username,
                    "timestamp": leave_timestamp
                }
            })

            # Broadcast updated online_users list
            await manager.broadcast({
                "type": "online_users",
                "data": {
                    "users": manager.get_online_users()
                }
            })

            # Trigger leave hook for Member 3
            await manager.trigger_on_user_leave(clean_username, leave_timestamp)


def start() -> None:
    """Run backend with uvicorn on http://localhost:8000."""
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    start()

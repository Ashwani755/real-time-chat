"""
Automated Test Suite for Real-Time Chat Backend & WebSocket Server.

Tests:
- Serving of frontend static files (HTML, CSS, JS).
- API Status, Health, and Online Users HTTP Endpoints.
- Single user connection lifecycle (online_users, chat_history, user_joined).
- Real-time message exchange and broadcast across multiple users.
- Message validation (empty / whitespace messages).
- Payload error handling (malformed JSON, invalid format, unknown message types).
- User disconnection and presence tracking (user_left, online_users update).
- Duplicate username rejection per room.
- Multi-room WebSocket partitioning (/ws/{room}/{username}).
- Integration hooks for Member 3 (SQLite / MQTT callbacks).
"""

import asyncio
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.websocket_manager import manager


@pytest.fixture(autouse=True)
def reset_manager_state():
    """Ensure manager state is clear before each test."""
    manager.clear()
    yield
    manager.clear()


def test_root_serves_frontend_html():
    """Test the root HTTP endpoint serves frontend index.html with 200 OK."""
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "Real-Time Chat" in response.text
    assert "app.js" in response.text


def test_rooms_html_served():
    """Test /rooms.html is accessible and served by backend."""
    client = TestClient(app)
    response = client.get("/rooms.html")
    assert response.status_code == 200
    assert "rooms.js" in response.text


def test_api_status_endpoint():
    """Test the /api/status HTTP endpoint returns JSON metadata."""
    client = TestClient(app)
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert "endpoints" in data


def test_health_endpoint():
    """Test the /health HTTP endpoint."""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_online_users_http_endpoint():
    """Test /online-users endpoint when no users are connected."""
    client = TestClient(app)
    response = client.get("/online-users")
    assert response.status_code == 200
    data = response.json()
    assert data["users"] == []
    assert data["count"] == 0


def test_websocket_connect_and_initial_messages():
    """Test connection lifecycle and initial messages received by a new client."""
    client = TestClient(app)
    with client.websocket_connect("/ws/Alice") as ws:
        # Message 1: Initial online_users list
        msg1 = ws.receive_json()
        assert msg1["type"] == "online_users"
        assert "Alice" in msg1["data"]["users"]

        # Message 2: Initial chat_history
        msg2 = ws.receive_json()
        assert msg2["type"] == "chat_history"
        assert isinstance(msg2["data"]["messages"], list)

        # Message 3: user_joined broadcast
        msg3 = ws.receive_json()
        assert msg3["type"] == "user_joined"
        assert msg3["data"]["username"] == "Alice"
        assert "timestamp" in msg3["data"]

        # Message 4: updated online_users broadcast
        msg4 = ws.receive_json()
        assert msg4["type"] == "online_users"
        assert "Alice" in msg4["data"]["users"]


def test_websocket_chat_message_broadcast():
    """Test sending a valid chat message and receiving proper formatting with ID and timestamp."""
    client = TestClient(app)
    with client.websocket_connect("/ws/Alice") as ws:
        # Drain initial 4 connection messages
        for _ in range(4):
            ws.receive_json()

        # Send chat message
        ws.send_json({
            "type": "chat_message",
            "data": {
                "message": "Hello everyone!"
            }
        })

        # Receive formatted broadcast
        response = ws.receive_json()
        assert response["type"] == "chat_message"
        data = response["data"]
        assert data["username"] == "Alice"
        assert data["message"] == "Hello everyone!"
        assert "message_id" in data
        assert "timestamp" in data


def test_multiple_users_chat_exchange():
    """Test real-time message exchange between two connected users."""
    client = TestClient(app)
    with client.websocket_connect("/ws/Alice") as ws_alice:
        # Drain Alice's initial messages
        for _ in range(4):
            ws_alice.receive_json()

        with client.websocket_connect("/ws/Bob") as ws_bob:
            # Alice should receive Bob's user_joined and updated online_users
            alice_saw_join = ws_alice.receive_json()
            assert alice_saw_join["type"] == "user_joined"
            assert alice_saw_join["data"]["username"] == "Bob"

            alice_saw_users = ws_alice.receive_json()
            assert alice_saw_users["type"] == "online_users"
            assert set(alice_saw_users["data"]["users"]) == {"Alice", "Bob"}

            # Drain Bob's initial messages
            for _ in range(4):
                ws_bob.receive_json()

            # Alice sends a message
            ws_alice.send_json({
                "type": "chat_message",
                "data": {
                    "message": "Hey Bob!"
                }
            })

            # Both Alice and Bob should receive the broadcast
            alice_msg = ws_alice.receive_json()
            bob_msg = ws_bob.receive_json()

            assert alice_msg["type"] == "chat_message"
            assert alice_msg["data"]["username"] == "Alice"
            assert alice_msg["data"]["message"] == "Hey Bob!"

            assert bob_msg["type"] == "chat_message"
            assert bob_msg["data"]["username"] == "Alice"
            assert bob_msg["data"]["message"] == "Hey Bob!"
            assert bob_msg["data"]["message_id"] == alice_msg["data"]["message_id"]


def test_empty_message_validation():
    """Test sending empty and whitespace-only messages triggers INVALID_MESSAGE error."""
    client = TestClient(app)
    with client.websocket_connect("/ws/Alice") as ws:
        for _ in range(4):
            ws.receive_json()

        # Test empty string
        ws.send_json({"type": "chat_message", "data": {"message": ""}})
        err1 = ws.receive_json()
        assert err1["type"] == "error"
        assert err1["data"]["code"] == "INVALID_MESSAGE"
        assert err1["data"]["message"] == "Message cannot be empty."

        # Test whitespace string
        ws.send_json({"type": "chat_message", "data": {"message": "   \n\t  "}})
        err2 = ws.receive_json()
        assert err2["type"] == "error"
        assert err2["data"]["code"] == "INVALID_MESSAGE"


def test_malformed_json_handling():
    """Test sending non-JSON payload returns INVALID_JSON error."""
    client = TestClient(app)
    with client.websocket_connect("/ws/Alice") as ws:
        for _ in range(4):
            ws.receive_json()

        # Send raw invalid text
        ws.send_text("this is not json {")
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["data"]["code"] == "INVALID_JSON"


def test_unknown_message_type():
    """Test sending an unrecognized message type returns UNKNOWN_TYPE error."""
    client = TestClient(app)
    with client.websocket_connect("/ws/Alice") as ws:
        for _ in range(4):
            ws.receive_json()

        ws.send_json({"type": "ping", "data": {}})
        err = ws.receive_json()
        assert err["type"] == "error"
        assert err["data"]["code"] == "UNKNOWN_TYPE"


def test_duplicate_username_rejection():
    """Test connecting with an active username returns USERNAME_TAKEN error."""
    client = TestClient(app)
    with client.websocket_connect("/ws/Alice"):
        with client.websocket_connect("/ws/Alice") as ws2:
            err = ws2.receive_json()
            assert err["type"] == "error"
            assert err["data"]["code"] == "USERNAME_TAKEN"


def test_user_leave_event():
    """Test client sending 'leave' gracefully exits and broadcasts user_left."""
    client = TestClient(app)
    with client.websocket_connect("/ws/Alice") as ws_alice:
        for _ in range(4):
            ws_alice.receive_json()

        with client.websocket_connect("/ws/Bob") as ws_bob:
            # Drain join events on Alice
            ws_alice.receive_json()
            ws_alice.receive_json()
            # Drain Bob's initial messages
            for _ in range(4):
                ws_bob.receive_json()

            # Bob sends leave
            ws_bob.send_json({"type": "leave"})

        # Alice receives Bob's leave notification
        leave_msg = ws_alice.receive_json()
        assert leave_msg["type"] == "user_left"
        assert leave_msg["data"]["username"] == "Bob"

        # Alice receives updated online users
        users_msg = ws_alice.receive_json()
        assert users_msg["type"] == "online_users"
        assert users_msg["data"]["users"] == ["Alice"]


def test_multi_room_partitioning():
    """Test that users in different rooms are isolated from each other's messages."""
    client = TestClient(app)

    # Alice connects to #gaming
    with client.websocket_connect("/ws/gaming/Alice") as ws_alice:
        for _ in range(4):
            ws_alice.receive_json()

        # Bob connects to #tech
        with client.websocket_connect("/ws/tech/Bob") as ws_bob:
            for _ in range(4):
                ws_bob.receive_json()

            # Charlie connects to #gaming (same room as Alice)
            with client.websocket_connect("/ws/gaming/Charlie") as ws_charlie:
                # Alice receives Charlie's join notification in #gaming
                alice_join = ws_alice.receive_json()
                assert alice_join["type"] == "user_joined"
                assert alice_join["data"]["username"] == "Charlie"
                assert alice_join["data"]["room"] == "gaming"

                # Drain Charlie's initial messages
                for _ in range(4):
                    ws_charlie.receive_json()

                # Alice sends message in #gaming
                ws_alice.send_json({
                    "type": "chat_message",
                    "data": {"message": "GG everyone!"}
                })

                # Charlie in #gaming receives it
                charlie_msg = ws_charlie.receive_json()
                assert charlie_msg["type"] == "chat_message"
                assert charlie_msg["data"]["message"] == "GG everyone!"
                assert charlie_msg["data"]["room"] == "gaming"


def test_member3_integration_hooks():
    """Test registration and asynchronous triggering of Member 3 hooks."""
    recorded_messages = []
    recorded_joins = []
    recorded_leaves = []

    async def sample_msg_hook(username, message, msg_id, timestamp, room="general"):
        recorded_messages.append({"username": username, "message": message, "id": msg_id, "ts": timestamp, "room": room})

    async def sample_join_hook(username, timestamp, room="general"):
        recorded_joins.append({"username": username, "ts": timestamp, "room": room})

    async def sample_leave_hook(username, timestamp, room="general"):
        recorded_leaves.append({"username": username, "ts": timestamp, "room": room})

    manager.register_on_message(sample_msg_hook)
    manager.register_on_user_join(sample_join_hook)
    manager.register_on_user_leave(sample_leave_hook)

    client = TestClient(app)
    with client.websocket_connect("/ws/Charlie") as ws:
        for _ in range(4):
            ws.receive_json()

        ws.send_json({"type": "chat_message", "data": {"message": "Test hook message"}})
        ws.receive_json()

    # Allow event loop tasks to run
    assert len(recorded_joins) == 1
    assert recorded_joins[0]["username"] == "Charlie"

    assert len(recorded_messages) == 1
    assert recorded_messages[0]["username"] == "Charlie"
    assert recorded_messages[0]["message"] == "Test hook message"

    assert len(recorded_leaves) == 1
    assert recorded_leaves[0]["username"] == "Charlie"

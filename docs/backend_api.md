# Backend & WebSocket API Documentation

This document specifies the backend server endpoints, WebSocket communication contracts, payload schemas, and integration guides for the Real-Time Chat Application.

Developed by **Member 1 (Backend + WebSocket Developer)** on the `backend` branch.

---

## 1. Server Configuration

- **HTTP Base URL**: `http://localhost:8000`
- **WebSocket Base URL**: `ws://localhost:8000/ws/{username}`
- **Interactive API Docs (Swagger UI)**: `http://localhost:8000/docs`
- **CORS**: Enabled for all origins (`*`) to allow frontend development across ports and local files.

### Starting the Server
```bash
# Using uvicorn directly
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Or running main module
python -m backend.main
```

---

## 2. HTTP Endpoints

| Method | Endpoint | Description | Sample Response |
|---|---|---|---|
| `GET` | `/` | Root info & service health status | `{"service": "Real-Time Chat Backend", "status": "running", "websocket_endpoint": "/ws/{username}"}` |
| `GET` | `/health` | Liveness health check | `{"status": "healthy"}` |
| `GET` | `/online-users` | Snapshot of connected users | `{"users": ["Alice", "Bob"], "count": 2}` |

---

## 3. WebSocket Protocol (`ws://localhost:8000/ws/{username}`)

### 3.1 Connection Handshake
1. Client establishes connection to:
   ```
   ws://localhost:8000/ws/{username}
   ```
   *Replace `{username}` with the URL-encoded username (e.g., `Alice`).*

2. Upon connection, the server immediately sends:
   - `online_users`: Current list of online users including the new user.
   - `chat_history`: Initial message history (ready for Member 3 SQLite integration).
   - `user_joined`: Notification broadcast to all connected users.
   - `online_users`: Updated broadcast to all connected users.

3. **Rejection Cases**:
   - If username is empty/blank: Server sends `INVALID_USERNAME` error and closes socket.
   - If username is already connected: Server sends `USERNAME_TAKEN` error and closes socket with code `4001`.

---

### 3.2 Client → Server Message Formats

#### A. Chat Message
Sent when a user types and sends a message.
```json
{
  "type": "chat_message",
  "data": {
    "message": "Hello everyone!"
  }
}
```

#### B. Explicit Join (Optional)
Can be sent to re-sync or confirm connection state:
```json
{
  "type": "join",
  "data": {
    "username": "Alice"
  }
}
```

#### C. Leave
Sent when the user clicks 'Logout' or explicitly leaves:
```json
{
  "type": "leave"
}
```

---

### 3.3 Server → Client Message Formats

#### A. `chat_message`
Broadcast to all connected clients when a message is sent.
```json
{
  "type": "chat_message",
  "data": {
    "message_id": 101,
    "username": "Alice",
    "message": "Hello everyone!",
    "timestamp": "2026-09-23T14:30:00"
  }
}
```

#### B. `user_joined`
Broadcast when any user successfully connects.
```json
{
  "type": "user_joined",
  "data": {
    "username": "Alice",
    "timestamp": "2026-09-23T14:30:00"
  }
}
```

#### C. `user_left`
Broadcast when a user disconnects or sends a `leave` event.
```json
{
  "type": "user_left",
  "data": {
    "username": "Alice",
    "timestamp": "2026-09-23T14:35:00"
  }
}
```

#### D. `online_users`
Broadcast whenever the roster changes (user joins or leaves), or sent on connect.
```json
{
  "type": "online_users",
  "data": {
    "users": ["Alice", "Bob", "Charlie"]
  }
}
```

#### E. `chat_history`
Sent to a newly connected client with past chat history.
```json
{
  "type": "chat_history",
  "data": {
    "messages": [
      {
        "message_id": 101,
        "username": "Alice",
        "message": "Hello everyone!",
        "timestamp": "2026-09-23T14:30:00"
      }
    ]
  }
}
```

#### F. `error`
Sent directly to the client if an invalid action is performed.
```json
{
  "type": "error",
  "data": {
    "code": "INVALID_MESSAGE",
    "message": "Message cannot be empty."
  }
}
```

Error codes:
- `INVALID_MESSAGE`: Empty or whitespace-only message text.
- `INVALID_JSON`: Malformed JSON syntax.
- `INVALID_FORMAT`: Missing `type` field or bad payload structure.
- `UNKNOWN_TYPE`: Unrecognized `type` field.
- `USERNAME_TAKEN`: Attempted to connect with an already-logged-in username.
- `INVALID_USERNAME`: Missing or empty username in URL.

---

## 4. Frontend Integration Guide (For Member 2)

Here is a standard JavaScript snippet to connect to the backend:

```javascript
const username = "Alice";
const socket = new WebSocket(`ws://localhost:8000/ws/${encodeURIComponent(username)}`);

socket.onopen = (event) => {
  console.log("Connected to chat server!");
};

socket.onmessage = (event) => {
  const payload = JSON.parse(event.data);

  switch (payload.type) {
    case "chat_message":
      // Display message in UI
      console.log(`[${payload.data.timestamp}] ${payload.data.username}: ${payload.data.message}`);
      break;

    case "user_joined":
      // Display join alert in chat
      console.log(`User joined: ${payload.data.username}`);
      break;

    case "user_left":
      // Display leave alert in chat
      console.log(`User left: ${payload.data.username}`);
      break;

    case "online_users":
      // Update sidebar / user list in UI
      console.log("Online users:", payload.data.users);
      break;

    case "chat_history":
      // Populate previous messages
      console.log("Chat history:", payload.data.messages);
      break;

    case "error":
      // Show error popup / notification to user
      console.error(`Error (${payload.data.code}): ${payload.data.message}`);
      break;
  }
};

// Sending a chat message
function sendChatMessage(text) {
  socket.send(JSON.stringify({
    type: "chat_message",
    data: {
      message: text
    }
  }));
}

// Leaving
function disconnectChat() {
  socket.send(JSON.stringify({ type: "leave" }));
  socket.close();
}
```

---

## 5. SQLite & MQTT Integration Guide (For Member 3)

The `ConnectionManager` in `backend/websocket_manager.py` exposes non-blocking extension hooks to easily plug in SQLite message persistence and MQTT event publishing without modifying core WebSocket logic:

```python
from backend.websocket_manager import manager
from your_db_module import save_chat_message, log_user_event
from your_mqtt_module import publish_mqtt_message

# 1. Hook into chat messages (save to SQLite + publish to MQTT broker)
async def handle_new_message(username: str, message: str, message_id: int, timestamp: str):
    # Save to SQLite
    await save_chat_message(message_id, username, message, timestamp)
    # Publish to MQTT topic e.g. "chat/general"
    await publish_mqtt_message(topic="chat/messages", payload={
        "message_id": message_id,
        "username": username,
        "message": message,
        "timestamp": timestamp
    })

manager.register_on_message(handle_new_message)

# 2. Hook into user join / leave events
async def handle_user_join(username: str, timestamp: str):
    await log_user_event(username, "join", timestamp)

async def handle_user_leave(username: str, timestamp: str):
    await log_user_event(username, "leave", timestamp)

manager.register_on_user_join(handle_user_join)
manager.register_on_user_leave(handle_user_leave)
```

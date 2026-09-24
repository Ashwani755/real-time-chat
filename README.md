# Real-Time Chat

Shared repository for the real-time chat application.

## Project structure

- `backend/` contains server-side integrations, including MQTT system events.
- `database/` contains SQLite chat persistence.
- `frontend/` is reserved for the browser client.
- `tests/` contains automated tests.
- `docs/` contains project documentation.

WebSocket remains the browser chat transport. MQTT is used only for join,
leave, and message-sent system events.

## Setup

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Update `.env` with the team's broker settings. The default is an
unauthenticated broker at `localhost:1883`. SQLite creates
`database/chat.db` on first use; database files and `.env` are ignored by Git.

## Usage

```python
from database import get_chat_history, init_db, save_message
from backend.mqtt_client import MQTTEventClient

init_db()
events = MQTTEventClient().connect()

saved = save_message("Alice", "Hello!", "2026-09-22T14:30:00")
events.publish_message_sent(
    saved["username"], saved["message_id"], saved["timestamp"]
)

history_payload = get_chat_history(limit=100)
```

Each database operation opens and closes its own SQLite connection. Invalid
arguments raise `ValueError`; storage failures raise `DatabaseError`; and MQTT
failures raise `MQTTError`.

## FastAPI integration points

1. On startup, call `init_db()`, then create and connect one shared
   `MQTTEventClient`.
2. When a WebSocket user connects, send `get_chat_history(limit=100)` and call
   `publish_user_joined(...)`.
3. For an incoming message, call `save_message(...)`, broadcast the returned
   dictionary, then call `publish_message_sent(...)`.
4. When a user disconnects, call `publish_user_left(...)`.
5. On shutdown, call `disconnect()` on the shared MQTT client.

The database helpers are synchronous. Async FastAPI handlers should run them
with `starlette.concurrency.run_in_threadpool`. MQTT publication is a separate
system-event step: a broker failure should not undo a stored message or stop
WebSocket delivery.

An MQTT callback can be supplied as `MQTTEventClient(on_event=callback)`. It
receives `(topic, payload)`, where `payload` is a decoded JSON dictionary.
Callback failures are logged and contained.

## Tests

```powershell
python -m unittest discover -s tests -v
```

The MQTT tests use a fake client and do not require a running broker.

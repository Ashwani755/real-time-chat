# Real-Time Chat

Shared repository for the real-time chat application.

## Project structure

- `backend/` contains server-side modules.
- `frontend/` is reserved for the browser client.
- `tests/` contains automated backend tests.
- `docs/` contains project documentation.

The current backend modules provide SQLite chat history and MQTT system events.
WebSocket remains the browser chat transport; MQTT is used only for join, leave,
and message-sent events.

## Setup

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Update `.env` with the broker settings agreed by the team. By default the MQTT
client connects to an unauthenticated broker at `localhost:1883`. The SQLite
database is created at `backend/chat.db` on first use and is ignored by Git.

## Backend usage

```python
from backend.database import get_chat_history, init_db, save_message
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

### FastAPI integration points

1. On application startup, call `init_db()`, then create and connect one shared
   `MQTTEventClient`.
2. When a WebSocket user connects, send `get_chat_history(limit=100)` and call
   `publish_user_joined(...)`.
3. For an incoming chat message, call `save_message(...)`, broadcast the
   returned dictionary, then call `publish_message_sent(...)`.
4. When a user disconnects, call `publish_user_left(...)`.
5. On shutdown, call `disconnect()` on the shared MQTT client.

The database helpers are synchronous. Async FastAPI handlers should run them
with `starlette.concurrency.run_in_threadpool`. Treat MQTT publication as a
separate system-event step: a broker failure should not undo a stored message
or stop WebSocket delivery.

An MQTT event callback can be supplied as
`MQTTEventClient(on_event=callback)`. It receives `(topic, payload)`, where the
payload is a decoded JSON dictionary. Callback errors are logged and contained.

## Tests

```powershell
python -m unittest discover -s tests -v
```

The MQTT tests use a fake client and do not need a running broker.

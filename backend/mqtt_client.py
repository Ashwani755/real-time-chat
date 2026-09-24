"""MQTT system-event support for the chat application.

WebSocket remains the browser chat transport. This module only publishes and
subscribes to join, leave, and message-sent system events.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

try:
    import paho.mqtt.client as mqtt
except ImportError:  # Allows database-only use before optional dependencies install.
    mqtt = None  # type: ignore[assignment]


LOGGER = logging.getLogger(__name__)

USER_JOINED_TOPIC = "chat/events/user_joined"
USER_LEFT_TOPIC = "chat/events/user_left"
EVENTS_TOPIC = "chat/events"
EVENT_TOPICS = (USER_JOINED_TOPIC, USER_LEFT_TOPIC, EVENTS_TOPIC)

EventHandler = Callable[[str, dict[str, Any]], None]


class MQTTError(RuntimeError):
    """Raised when an MQTT operation cannot be completed."""


@dataclass(frozen=True)
class MQTTConfig:
    host: str = "localhost"
    port: int = 1883
    keepalive: int = 60
    client_id: str = "chat-backend"
    username: str | None = None
    password: str | None = None
    use_tls: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.host, str) or not self.host.strip():
            raise MQTTError("MQTT broker host must be a non-empty string")
        if (
            not isinstance(self.port, int)
            or isinstance(self.port, bool)
            or not 1 <= self.port <= 65535
        ):
            raise MQTTError("MQTT broker port must be between 1 and 65535")
        if (
            not isinstance(self.keepalive, int)
            or isinstance(self.keepalive, bool)
            or self.keepalive < 1
        ):
            raise MQTTError("MQTT keepalive must be a positive integer")
        if not isinstance(self.client_id, str) or not self.client_id.strip():
            raise MQTTError("MQTT client ID must be a non-empty string")

    @classmethod
    def from_env(cls) -> "MQTTConfig":
        """Build broker configuration from MQTT_* environment variables."""

        try:
            port = int(os.getenv("MQTT_BROKER_PORT", "1883"))
            keepalive = int(os.getenv("MQTT_KEEPALIVE", "60"))
        except ValueError as exc:
            raise MQTTError("MQTT_BROKER_PORT and MQTT_KEEPALIVE must be integers") from exc

        return cls(
            host=os.getenv("MQTT_BROKER_HOST", "localhost"),
            port=port,
            keepalive=keepalive,
            client_id=os.getenv("MQTT_CLIENT_ID", "chat-backend"),
            username=os.getenv("MQTT_USERNAME") or None,
            password=os.getenv("MQTT_PASSWORD") or None,
            use_tls=os.getenv("MQTT_USE_TLS", "false").lower()
            in {"1", "true", "yes"},
        )


def _timestamp_text(timestamp: str | datetime) -> str:
    if isinstance(timestamp, datetime):
        return timestamp.isoformat()
    if isinstance(timestamp, str) and timestamp.strip():
        return timestamp
    raise ValueError("timestamp must be a non-empty ISO 8601 string or datetime")


def _non_empty(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


class MQTTEventClient:
    """Reusable publisher/subscriber for the agreed chat event topics."""

    def __init__(
        self,
        config: MQTTConfig | None = None,
        *,
        on_event: EventHandler | None = None,
        client: Any | None = None,
    ) -> None:
        self.config = config or MQTTConfig.from_env()
        self.on_event = on_event

        if client is None:
            if mqtt is None:
                raise MQTTError("paho-mqtt is not installed; install requirements.txt")
            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=self.config.client_id,
                protocol=mqtt.MQTTv311,
            )

        self.client = client
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

        if self.config.username:
            self.client.username_pw_set(self.config.username, self.config.password)
        if self.config.use_tls:
            self.client.tls_set()

    def connect(self) -> "MQTTEventClient":
        """Connect to the broker and start Paho's background network loop."""

        try:
            result = self.client.connect(
                self.config.host,
                self.config.port,
                self.config.keepalive,
            )
            if int(result) != 0:
                raise MQTTError(f"MQTT connection request failed with code {result}")
            self.client.loop_start()
            return self
        except MQTTError:
            raise
        except Exception as exc:
            raise MQTTError(
                f"Could not connect to MQTT broker {self.config.host}:{self.config.port}"
            ) from exc

    def disconnect(self) -> None:
        """Stop networking and disconnect cleanly."""

        try:
            self.client.disconnect()
        finally:
            self.client.loop_stop()

    def subscribe_to_events(self) -> None:
        """Subscribe to all three agreed event topics with QoS 1."""

        for topic in EVENT_TOPICS:
            try:
                result, _message_id = self.client.subscribe(topic, qos=1)
            except Exception as exc:
                raise MQTTError(f"Could not subscribe to {topic}") from exc
            if int(result) != 0:
                raise MQTTError(f"Could not subscribe to {topic}; MQTT code {result}")

    def publish_event(self, topic: str, payload: dict[str, Any]) -> int:
        """Publish a JSON event to an agreed topic and return its MQTT id."""

        if topic not in EVENT_TOPICS:
            raise ValueError(f"Unsupported MQTT topic: {topic}")
        if not isinstance(payload, dict):
            raise ValueError("payload must be a dictionary")

        try:
            encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("payload must be JSON serialisable") from exc

        try:
            info = self.client.publish(topic, encoded, qos=1, retain=False)
        except Exception as exc:
            raise MQTTError(f"Could not publish to {topic}") from exc
        if int(info.rc) != 0:
            raise MQTTError(f"Could not publish to {topic}; MQTT code {info.rc}")
        return int(info.mid)

    def publish_user_joined(self, username: str, timestamp: str | datetime) -> int:
        return self.publish_event(
            USER_JOINED_TOPIC,
            {
                "event": "user_joined",
                "username": _non_empty(username, "username"),
                "timestamp": _timestamp_text(timestamp),
            },
        )

    def publish_user_left(self, username: str, timestamp: str | datetime) -> int:
        return self.publish_event(
            USER_LEFT_TOPIC,
            {
                "event": "user_left",
                "username": _non_empty(username, "username"),
                "timestamp": _timestamp_text(timestamp),
            },
        )

    def publish_message_sent(
        self,
        username: str,
        message_id: int,
        timestamp: str | datetime,
    ) -> int:
        if (
            not isinstance(message_id, int)
            or isinstance(message_id, bool)
            or message_id < 1
        ):
            raise ValueError("message_id must be a positive integer")
        return self.publish_event(
            EVENTS_TOPIC,
            {
                "event": "message_sent",
                "username": _non_empty(username, "username"),
                "message_id": message_id,
                "timestamp": _timestamp_text(timestamp),
            },
        )

    def _on_connect(
        self,
        _client: Any,
        _userdata: Any,
        _flags: Any,
        reason_code: Any,
        _properties: Any,
    ) -> None:
        # Paho ReasonCode compares with 0 but does not implement int().
        if reason_code == 0:
            try:
                self.subscribe_to_events()
            except MQTTError:
                LOGGER.exception("MQTT event subscription failed")
        else:
            LOGGER.error("MQTT broker rejected connection: %s", reason_code)

    def _on_message(self, _client: Any, _userdata: Any, message: Any) -> None:
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("event payload is not a JSON object")
            if self.on_event is not None:
                try:
                    self.on_event(message.topic, payload)
                except Exception:
                    LOGGER.exception("MQTT event handler failed for %s", message.topic)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            LOGGER.warning("Ignored invalid MQTT JSON event on %s", message.topic)

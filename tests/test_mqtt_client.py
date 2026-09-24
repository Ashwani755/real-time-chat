import json
import unittest

from backend.mqtt_client import (
    EVENTS_TOPIC,
    EVENT_TOPICS,
    MQTTConfig,
    MQTTError,
    MQTTEventClient,
    USER_JOINED_TOPIC,
    USER_LEFT_TOPIC,
)


class PublishInfo:
    rc = 0
    mid = 42


class FakeMQTTClient:
    def __init__(self) -> None:
        self.published = []
        self.subscribed = []
        self.connected = None
        self.loop_started = False
        self.loop_stopped = False

    def username_pw_set(self, *_args):
        pass

    def tls_set(self):
        pass

    def connect(self, host, port, keepalive):
        self.connected = (host, port, keepalive)
        return 0

    def loop_start(self):
        self.loop_started = True

    def loop_stop(self):
        self.loop_stopped = True

    def disconnect(self):
        return 0

    def subscribe(self, topic, qos):
        self.subscribed.append((topic, qos))
        return (0, len(self.subscribed))

    def publish(self, topic, payload, qos, retain):
        self.published.append((topic, json.loads(payload), qos, retain))
        return PublishInfo()


class SuccessReasonCode:
    """Acts like Paho's non-int-convertible ReasonCode."""

    def __eq__(self, other):
        return other == 0


class MQTTClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake = FakeMQTTClient()
        self.events = []
        self.mqtt = MQTTEventClient(
            MQTTConfig(host="broker.test"),
            client=self.fake,
            on_event=lambda topic, payload: self.events.append((topic, payload)),
        )

    def test_connect_starts_network_loop(self) -> None:
        self.mqtt.connect()
        self.assertEqual(self.fake.connected, ("broker.test", 1883, 60))
        self.assertTrue(self.fake.loop_started)

    def test_subscribes_to_all_agreed_topics(self) -> None:
        self.mqtt.subscribe_to_events()
        self.assertEqual(self.fake.subscribed, [(topic, 1) for topic in EVENT_TOPICS])

    def test_successful_connection_callback_subscribes(self) -> None:
        self.mqtt._on_connect(None, None, None, SuccessReasonCode(), None)
        self.assertEqual(self.fake.subscribed, [(topic, 1) for topic in EVENT_TOPICS])

    def test_convenience_publishers_use_expected_json(self) -> None:
        timestamp = "2026-09-22T14:30:00"
        self.mqtt.publish_user_joined("Alice", timestamp)
        self.mqtt.publish_user_left("Alice", timestamp)
        self.mqtt.publish_message_sent("Alice", 101, timestamp)

        self.assertEqual(self.fake.published[0][0], USER_JOINED_TOPIC)
        self.assertEqual(self.fake.published[0][1]["event"], "user_joined")
        self.assertEqual(self.fake.published[1][0], USER_LEFT_TOPIC)
        self.assertEqual(self.fake.published[1][1]["event"], "user_left")
        self.assertEqual(
            self.fake.published[2],
            (
                EVENTS_TOPIC,
                {
                    "event": "message_sent",
                    "username": "Alice",
                    "message_id": 101,
                    "timestamp": timestamp,
                },
                1,
                False,
            ),
        )

    def test_received_json_is_decoded_for_handler(self) -> None:
        message = type(
            "Message",
            (),
            {
                "topic": EVENTS_TOPIC,
                "payload": b'{"event":"message_sent","message_id":101}',
            },
        )()
        self.mqtt._on_message(None, None, message)
        self.assertEqual(self.events[0][1]["message_id"], 101)

    def test_rejects_unagreed_topic(self) -> None:
        with self.assertRaises(ValueError):
            self.mqtt.publish_event("chat/messages", {"event": "wrong_transport"})

    def test_rejects_invalid_broker_configuration(self) -> None:
        with self.assertRaises(MQTTError):
            MQTTConfig(host="", port=1883)
        with self.assertRaises(MQTTError):
            MQTTConfig(port=70000)

    def test_event_handler_failure_does_not_escape_callback(self) -> None:
        def failing_handler(_topic, _payload):
            raise RuntimeError("boom")

        mqtt_client = MQTTEventClient(
            MQTTConfig(),
            client=self.fake,
            on_event=failing_handler,
        )
        message = type(
            "Message",
            (),
            {"topic": EVENTS_TOPIC, "payload": b'{"event":"message_sent"}'},
        )()

        with self.assertLogs("backend.mqtt_client", level="ERROR"):
            mqtt_client._on_message(None, None, message)


if __name__ == "__main__":
    unittest.main()

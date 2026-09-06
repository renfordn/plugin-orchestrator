"""Tests for production telemetry sink hooks (Datadog, New Relic)."""

import json
import socket
import unittest
from unittest.mock import patch, MagicMock

from orchestrator.telemetry import TelemetryPublisher
from orchestrator.telemetry_sinks import DatadogStatsDHook, NewRelicEventHook


class TestDatadogStatsDHook(unittest.TestCase):
    """Test DatadogStatsDHook sends valid DogStatsD packets over UDP."""

    def setUp(self):
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.listener.bind(("localhost", 0))
        self.listener.settimeout(2)
        host, port = self.listener.getsockname()
        self.hook = DatadogStatsDHook(host=host, port=port)

    def tearDown(self):
        self.listener.close()
        self.hook._socket.close()

    def _recv(self) -> str:
        data, _ = self.listener.recvfrom(4096)
        return data.decode("utf-8")

    def test_sends_counter_for_event(self):
        self.hook({"event_type": "availability_check", "plugin": "agent-tdd", "available": True})

        packet = self._recv()
        self.assertEqual(packet, "orchestrator.availability_check:1|c|#plugin:agent-tdd,available:True")

    def test_sends_gauge_for_duration_ms(self):
        self.hook({"event_type": "handoff", "duration_ms": 0.123, "success": True})

        counter_packet = self._recv()
        gauge_packet = self._recv()

        self.assertTrue(counter_packet.startswith("orchestrator.handoff:1|c"))
        self.assertEqual(gauge_packet, "orchestrator.handoff.duration_ms:0.123|g|#success:True")

    def test_no_tags_when_no_taggable_fields_present(self):
        self.hook({"event_type": "routing"})

        packet = self._recv()
        self.assertEqual(packet, "orchestrator.routing:1|c")

    def test_custom_metric_prefix(self):
        host, port = self.listener.getsockname()
        hook = DatadogStatsDHook(host=host, port=port, metric_prefix="my_app")
        self.addCleanup(hook._socket.close)

        hook({"event_type": "routing"})

        packet = self._recv()
        self.assertTrue(packet.startswith("my_app.routing:1|c"))

    def test_integrates_with_telemetry_publisher(self):
        publisher = TelemetryPublisher()
        publisher.register_hook(self.hook)

        publisher.emit("routing", current_plugin="agent-isdd", next_plugin="agent-tdd")

        packet = self._recv()
        self.assertIn("orchestrator.routing:1|c", packet)
        self.assertIn("current_plugin:agent-isdd", packet)
        self.assertIn("next_plugin:agent-tdd", packet)


class TestNewRelicEventHook(unittest.TestCase):
    """Test NewRelicEventHook posts a well-formed request to the Event API."""

    def setUp(self):
        self.hook = NewRelicEventHook(account_id="12345", api_key="NRAK-test-key")

    @patch("orchestrator.telemetry_sinks.urllib.request.urlopen")
    def test_posts_to_correct_url_and_headers(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value = MagicMock()

        self.hook({"event_type": "handoff", "success": True})

        request = mock_urlopen.call_args[0][0]
        self.assertEqual(request.full_url, "https://insights-collector.newrelic.com/v1/accounts/12345/events")
        self.assertEqual(request.get_header("Api-key"), "NRAK-test-key")
        self.assertEqual(request.get_header("Content-type"), "application/json")

    @patch("orchestrator.telemetry_sinks.urllib.request.urlopen")
    def test_payload_includes_event_type_and_fields(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value = MagicMock()

        self.hook({"event_type": "handoff", "source": "agent-isdd", "success": True})

        request = mock_urlopen.call_args[0][0]
        payload = json.loads(request.data)
        self.assertEqual(payload["eventType"], "OrchestratorEvent")
        self.assertEqual(payload["event_type"], "handoff")
        self.assertEqual(payload["source"], "agent-isdd")
        self.assertEqual(payload["success"], True)

    @patch("orchestrator.telemetry_sinks.urllib.request.urlopen")
    def test_nested_metadata_dict_is_json_stringified(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value = MagicMock()

        self.hook({"event_type": "handoff", "metadata": {"payload_size": 4}})

        request = mock_urlopen.call_args[0][0]
        payload = json.loads(request.data)
        self.assertEqual(json.loads(payload["metadata"]), {"payload_size": 4})

    @patch("orchestrator.telemetry_sinks.urllib.request.urlopen")
    def test_none_fields_are_dropped(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value = MagicMock()

        self.hook({"event_type": "handoff", "error": None})

        request = mock_urlopen.call_args[0][0]
        payload = json.loads(request.data)
        self.assertNotIn("error", payload)

    @patch("orchestrator.telemetry_sinks.urllib.request.urlopen")
    def test_custom_event_type_and_region_endpoint(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value = MagicMock()
        hook = NewRelicEventHook(
            account_id="999", api_key="key",
            event_type="CustomEvent",
            region_endpoint="https://insights-collector.eu01.nr-data.net",
        )

        hook({"event_type": "routing"})

        request = mock_urlopen.call_args[0][0]
        payload = json.loads(request.data)
        self.assertEqual(payload["eventType"], "CustomEvent")
        self.assertEqual(
            request.full_url, "https://insights-collector.eu01.nr-data.net/v1/accounts/999/events"
        )

    @patch("orchestrator.telemetry_sinks.urllib.request.urlopen")
    def test_network_failure_propagates_to_caller(self, mock_urlopen):
        """The hook itself doesn't swallow errors; TelemetryPublisher.emit does."""
        mock_urlopen.side_effect = OSError("connection refused")

        with self.assertRaises(OSError):
            self.hook({"event_type": "routing"})

    @patch("orchestrator.telemetry_sinks.urllib.request.urlopen")
    def test_failure_does_not_break_telemetry_publisher(self, mock_urlopen):
        mock_urlopen.side_effect = OSError("connection refused")
        publisher = TelemetryPublisher()
        publisher.register_hook(self.hook)

        # Must not raise.
        publisher.emit("routing", current_plugin="agent-isdd")


if __name__ == "__main__":
    unittest.main()

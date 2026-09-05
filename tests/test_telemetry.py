"""Tests for TelemetryPublisher and its wiring into PluginRouter.

Covers the Priority 1 "production telemetry integration" enhancement: an
extensible hook registry that PluginRouter fires standard-shaped events into
on availability checks, handoff validation, and routing decisions, so an
external sink (Datadog, New Relic, etc.) can subscribe without the router
knowing about it.
"""

import unittest
from pathlib import Path

from orchestrator.telemetry import TelemetryPublisher
from orchestrator.core import PluginRouter
from orchestrator.interop_parser import CapabilityMap


class TestTelemetryPublisher(unittest.TestCase):
    def setUp(self):
        self.publisher = TelemetryPublisher()

    def test_register_and_emit_single_hook(self):
        events = []
        self.publisher.register_hook(events.append)

        self.publisher.emit("routing", plugin="agent-tdd")

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "routing")
        self.assertEqual(events[0]["plugin"], "agent-tdd")
        self.assertIn("timestamp", events[0])

    def test_multiple_hooks_all_receive_event(self):
        hook1_events, hook2_events = [], []
        self.publisher.register_hook(hook1_events.append)
        self.publisher.register_hook(hook2_events.append)

        self.publisher.emit("handoff", source="agent-isdd", target="agent-tdd")

        self.assertEqual(len(hook1_events), 1)
        self.assertEqual(len(hook2_events), 1)

    def test_faulty_hook_does_not_break_emit_or_other_hooks(self):
        good_events = []

        def bad_hook(event):
            raise RuntimeError("sink unavailable")

        self.publisher.register_hook(bad_hook)
        self.publisher.register_hook(good_events.append)

        # Should not raise despite bad_hook failing
        self.publisher.emit("availability_check", plugin="agent-nelly")

        self.assertEqual(len(good_events), 1)

    def test_emit_with_no_hooks_is_a_noop(self):
        # Should not raise
        self.publisher.emit("routing", plugin="agent-tdd")

    def test_unregister_hook_stops_future_events(self):
        events = []
        self.publisher.register_hook(events.append)
        self.publisher.unregister_hook(events.append)

        self.publisher.emit("routing", plugin="agent-tdd")

        self.assertEqual(len(events), 0)


class TestPluginRouterTelemetryIntegration(unittest.TestCase):
    def setUp(self):
        plugin_dir = str(Path(__file__).parent / "fixtures")
        self.capability_map = CapabilityMap(plugin_dir)
        self.publisher = TelemetryPublisher()
        self.events = []
        self.publisher.register_hook(self.events.append)
        self.router = PluginRouter(self.capability_map, telemetry=self.publisher)

    def test_router_works_without_telemetry(self):
        router = PluginRouter(self.capability_map)
        # Should not raise when no telemetry is configured
        router.check_plugin_availability("agent-tdd", "agent-tdd:agent-TDD available")

    def test_availability_check_emits_event(self):
        self.router.check_plugin_availability(
            "agent-tdd", "agent-tdd:agent-TDD available"
        )

        events = [e for e in self.events if e["event_type"] == "availability_check"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["plugin"], "agent-tdd")
        self.assertTrue(events[0]["available"])

    def test_route_to_next_plugin_emits_event(self):
        self.router.route_to_next_plugin(
            "agent-isdd", "design_approved", handoff_valid=True
        )

        events = [e for e in self.events if e["event_type"] == "routing"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["current_plugin"], "agent-isdd")
        self.assertEqual(events[0]["next_plugin"], "agent-tdd")

    def test_validate_handoff_emits_event_with_success_flag(self):
        payload = {
            "requirements_md": "x",
            "design_md": "x",
            "research_cache": {},
            "recap_md": "x",
        }
        self.router.validate_handoff(
            "agent-isdd", "design_spec_handoff",
            "agent-tdd", "design_spec_slicing",
            payload
        )

        events = [e for e in self.events if e["event_type"] == "handoff"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["source"], "agent-isdd")
        self.assertEqual(events[0]["target"], "agent-tdd")
        self.assertIn("success", events[0])
        self.assertIn("duration_ms", events[0])

    def test_validate_handoff_failure_emits_event_with_success_false(self):
        is_valid, _ = self.router.validate_handoff(
            "agent-isdd", "nonexistent_capability",
            "agent-tdd", "design_spec_slicing",
            {}
        )
        self.assertFalse(is_valid)

        events = [e for e in self.events if e["event_type"] == "handoff"]
        self.assertEqual(len(events), 1)
        self.assertFalse(events[0]["success"])


if __name__ == "__main__":
    unittest.main()

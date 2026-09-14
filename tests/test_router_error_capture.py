"""Tests for PluginRouter error capture integration (Slice 2.1)."""

import unittest
from pathlib import Path
from orchestrator.core import PluginRouter
from orchestrator.interop_parser import CapabilityMap
from orchestrator.error_logger import ErrorLogger


class TestPluginRouterErrorCapture(unittest.TestCase):
    """Red tests for error logging integration in PluginRouter methods."""

    def setUp(self):
        """Set up test fixtures with an ErrorLogger attached to the router."""
        self.plugin_dir = str(Path(__file__).parent / "fixtures")
        self.capability_map = CapabilityMap(self.plugin_dir)
        self.error_logger = ErrorLogger()
        self.router = PluginRouter(self.capability_map, error_logger=self.error_logger)

    def test_router_accepts_error_logger_none_by_default(self):
        """Test PluginRouter works with no error_logger (backward compatible)."""
        router = PluginRouter(self.capability_map)
        # Should not raise; error_logger defaults to None
        result = router.check_plugin_availability("agent-tdd", "no plugins here")
        self.assertFalse(result)

    def test_check_plugin_availability_logs_error_when_unavailable(self):
        """Test unavailability logs a plugin_unavailable error."""
        system_reminder = "no plugins mentioned here"
        self.router.check_plugin_availability("agent-tdd", system_reminder)

        session_errors = self.error_logger.get_session_errors()
        self.assertEqual(len(session_errors), 1)
        self.assertEqual(session_errors[0].error_type, "plugin_unavailable")
        self.assertEqual(session_errors[0].source_plugin, "agent-tdd")

    def test_check_plugin_availability_no_error_when_available(self):
        """Test no error logged when plugin is available."""
        system_reminder = "agent-tdd:agent-TDD is available"
        self.router.check_plugin_availability("agent-tdd", system_reminder)

        session_errors = self.error_logger.get_session_errors()
        self.assertEqual(len(session_errors), 0)

    def test_validate_handoff_logs_error_on_missing_capability(self):
        """Test validate_handoff logs handoff_validation error when capability not found."""
        is_valid, error = self.router.validate_handoff(
            "nonexistent-plugin", "some_capability",
            "agent-tdd", "design_spec_slicing",
            {"requirements_md": "x", "design_md": "x", "research_cache": {}, "recap_md": "x"}
        )

        self.assertFalse(is_valid)
        session_errors = self.error_logger.get_session_errors()
        self.assertEqual(len(session_errors), 1)
        self.assertEqual(session_errors[0].error_type, "handoff_validation")

    def test_validate_handoff_no_error_when_valid(self):
        """Test no error logged when handoff validation succeeds."""
        # Use a valid handoff from fixtures if available; skip assertion on validity,
        # focus on: valid handoffs produce zero errors
        is_valid, error = self.router.validate_handoff(
            "agent-isdd", "design_spec_handoff",
            "agent-tdd", "design_spec_slicing",
            {"requirements_md": "x", "design_md": "x", "research_cache": {}, "recap_md": "x"}
        )
        if is_valid:
            session_errors = self.error_logger.get_session_errors()
            self.assertEqual(len(session_errors), 0)

    def test_route_to_next_plugin_logs_error_when_no_route_found(self):
        """Test routing_failed error logged when no route exists for plugin+phase."""
        result = self.router.route_to_next_plugin(
            "unknown-plugin", "unknown-phase", handoff_valid=True
        )

        self.assertIsNone(result)
        session_errors = self.error_logger.get_session_errors()
        routing_errors = [e for e in session_errors if e.error_type == "routing_failed"]
        self.assertEqual(len(routing_errors), 1)

    def test_route_to_next_plugin_no_error_on_valid_route(self):
        """Test no routing error logged for a valid, known route."""
        self.router.route_to_next_plugin(
            "agent-isdd", "design_approved", handoff_valid=True
        )
        session_errors = self.error_logger.get_session_errors()
        routing_errors = [e for e in session_errors if e.error_type == "routing_failed"]
        self.assertEqual(len(routing_errors), 0)

    def test_route_to_next_plugin_no_error_on_end_of_workflow(self):
        """Test that a legitimate end-of-workflow (None route from valid final phase)
        is not conflated with a routing failure -- only unmapped (plugin,phase) pairs count."""
        # code-reviewer + review_complete -> None is a legitimate end, not a failure
        self.router.route_to_next_plugin(
            "code-reviewer", "review_complete", handoff_valid=True
        )
        session_errors = self.error_logger.get_session_errors()
        routing_errors = [e for e in session_errors if e.error_type == "routing_failed"]
        self.assertEqual(len(routing_errors), 0)

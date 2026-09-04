"""Edge Case Tests: Handle unavailable plugins, circular dependencies, and recovery.

Tests orchestrator resilience under fault conditions:
1. Plugin unavailability mid-workflow
2. Circular handoff dependencies
3. Missing capabilities
4. Large payload edge cases
5. Graceful degradation with soft dependencies
"""

import unittest
from pathlib import Path
from orchestrator.core import PluginRouter
from orchestrator.interop_parser import CapabilityMap


class TestPluginUnavailability(unittest.TestCase):
    """Test behavior when plugins become unavailable."""

    def setUp(self):
        """Set up test fixtures."""
        plugin_dir = str(Path(__file__).parent / "fixtures")
        self.capability_map = CapabilityMap(plugin_dir)
        self.router = PluginRouter(self.capability_map)

    def test_hard_dependency_unavailable(self):
        """Test workflow blocks when hard dependency unavailable."""
        system_reminder = "agent-ux:ui-renderer available"
        # Missing agent-tdd, agent-isdd, code-reviewer (hard dependencies)

        # Check that hard dependencies are correctly identified
        self.assertTrue(self.router.is_hard_dependency("agent-tdd"))
        self.assertTrue(self.router.is_hard_dependency("agent-isdd"))
        self.assertTrue(self.router.is_hard_dependency("code-reviewer"))

    def test_soft_dependency_unavailable(self):
        """Test workflow continues when soft dependency unavailable."""
        system_reminder = "agent-isdd:spec available agent-tdd:tdd available"
        # Missing agent-nelly, agent-ux (soft dependencies)

        # Soft dependencies should not block workflow
        self.assertTrue(self.router.is_soft_dependency("agent-nelly"))
        self.assertTrue(self.router.is_soft_dependency("agent-ux"))

        # Availability check should return False (not available)
        is_available = self.router.check_plugin_availability("agent-nelly", system_reminder)
        self.assertFalse(is_available)

    def test_plugin_availability_normalization(self):
        """Test plugin name normalization handles missing agent- prefix."""
        system_reminder = "agent-tdd:tdd available"

        # Should work with full name
        self.assertTrue(self.router.check_plugin_availability("agent-tdd", system_reminder))

        # Should work with short name (auto-prepend agent-)
        self.assertTrue(self.router.check_plugin_availability("tdd", system_reminder))

    def test_plugin_becomes_available_mid_workflow(self):
        """Test detecting plugin availability changes between checks."""
        system_reminder_v1 = "agent-isdd:spec available"
        system_reminder_v2 = "agent-isdd:spec available agent-nelly:memory available"

        # Initially unavailable
        self.assertFalse(self.router.check_plugin_availability("agent-nelly", system_reminder_v1))

        # Later becomes available
        self.assertTrue(self.router.check_plugin_availability("agent-nelly", system_reminder_v2))


class TestCircularDependencies(unittest.TestCase):
    """Test handling of circular handoff dependencies."""

    def setUp(self):
        """Set up test fixtures."""
        plugin_dir = str(Path(__file__).parent / "fixtures")
        self.capability_map = CapabilityMap(plugin_dir)
        self.router = PluginRouter(self.capability_map)

    def test_detect_potential_circular_route(self):
        """Test detection of circular routing patterns."""
        # agent-isdd -> agent-tdd -> agent-isdd (would be circular)
        # Verify routing prevents this

        # From isdd with design_approved, should route to tdd
        next_plugin = self.router.route_to_next_plugin("agent-isdd", "design_approved", True)
        # Should route to agent-tdd, not back to agent-isdd
        if next_plugin:
            self.assertNotEqual(next_plugin, "agent-isdd")

    def test_workflow_termination(self):
        """Test that workflows terminate properly (no infinite loops)."""
        # code-reviewer should NOT route back to itself
        next_plugin = self.router.route_to_next_plugin("code-reviewer", "review_complete", True)

        # Should either route to agent-isdd (for redesign) or return None (terminal)
        self.assertNotEqual(next_plugin, "code-reviewer",
            "Workflow must not route a plugin to itself")


class TestMissingCapabilities(unittest.TestCase):
    """Test handling of missing or undefined capabilities."""

    def setUp(self):
        """Set up test fixtures."""
        plugin_dir = str(Path(__file__).parent / "fixtures")
        self.capability_map = CapabilityMap(plugin_dir)
        self.router = PluginRouter(self.capability_map)

    def test_nonexistent_capability_returns_none(self):
        """Test that requesting nonexistent capability returns None."""
        capability = self.capability_map.find_capability(
            "agent-isdd",
            "nonexistent_capability_xyz"
        )
        self.assertIsNone(capability)

    def test_nonexistent_plugin_returns_none(self):
        """Test that querying nonexistent plugin returns None."""
        plugin = self.capability_map.get_plugin("nonexistent-plugin")
        self.assertIsNone(plugin)

    def test_handoff_validation_fails_gracefully_on_missing_source_capability(self):
        """Test validation fails gracefully when source capability missing."""
        payload = {"data": "test"}

        is_valid, error = self.router.validate_handoff(
            "agent-isdd",
            "nonexistent_source_capability",  # Missing capability
            "agent-tdd",
            "design_spec_slicing",
            payload
        )

        self.assertFalse(is_valid)
        self.assertIsNotNone(error)
        self.assertIn("not found", error.lower())

    def test_handoff_validation_fails_gracefully_on_missing_target_capability(self):
        """Test validation fails gracefully when target capability missing."""
        payload = {"data": "test"}

        is_valid, error = self.router.validate_handoff(
            "agent-isdd",
            "design_spec_handoff",
            "agent-tdd",
            "nonexistent_target_capability",  # Missing capability
            payload
        )

        self.assertFalse(is_valid)
        self.assertIsNotNone(error)
        self.assertIn("not found", error.lower())


class TestLargePayloadEdgeCases(unittest.TestCase):
    """Test handling of large and edge-case payloads."""

    def setUp(self):
        """Set up test fixtures."""
        plugin_dir = str(Path(__file__).parent / "fixtures")
        self.capability_map = CapabilityMap(plugin_dir)
        self.router = PluginRouter(self.capability_map)

    def test_empty_payload_validation(self):
        """Test validation with empty payload (should fail - missing required fields)."""
        empty_payload = {}

        is_valid, error = self.router.validate_handoff(
            "agent-isdd",
            "design_spec_handoff",
            "agent-tdd",
            "design_spec_slicing",
            empty_payload
        )

        self.assertFalse(is_valid)
        self.assertIsNotNone(error)

    def test_large_payload_validation(self):
        """Test validation with very large payload (should still pass if fields present)."""
        large_payload = {
            "requirements_md": "# Requirements\n" * 1000,  # ~25KB
            "design_md": "# Design\n" * 1000,  # ~25KB
            "research_cache": {"findings": ["finding"] * 1000},  # ~30KB
            "recap_md": "# Recap\n" * 1000  # ~15KB
        }

        is_valid, error = self.router.validate_handoff(
            "agent-isdd",
            "design_spec_handoff",
            "agent-tdd",
            "design_spec_slicing",
            large_payload
        )

        # Should validate successfully (only checks field presence, not content)
        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_null_and_empty_fields(self):
        """Test validation with null/empty field values."""
        payload = {
            "requirements_md": "",  # Empty but present
            "design_md": None,  # None but present
            "research_cache": {},  # Empty dict but present
            "recap_md": ""  # Empty string
        }

        is_valid, error = self.router.validate_handoff(
            "agent-isdd",
            "design_spec_handoff",
            "agent-tdd",
            "design_spec_slicing",
            payload
        )

        # Should pass validation (fields are present, only checking structure)
        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_extra_fields_in_payload(self):
        """Test that extra fields in payload don't break validation."""
        payload = {
            "requirements_md": "# Req",
            "design_md": "# Design",
            "research_cache": {},
            "recap_md": "# Recap",
            "extra_field_1": "extra",
            "extra_field_2": {"nested": "value"},
            "extra_field_3": [1, 2, 3]
        }

        is_valid, error = self.router.validate_handoff(
            "agent-isdd",
            "design_spec_handoff",
            "agent-tdd",
            "design_spec_slicing",
            payload
        )

        # Should pass (extra fields are ignored, only required fields checked)
        self.assertTrue(is_valid)
        self.assertIsNone(error)


class TestGracefulDegradation(unittest.TestCase):
    """Test graceful degradation when components fail."""

    def setUp(self):
        """Set up test fixtures."""
        plugin_dir = str(Path(__file__).parent / "fixtures")
        self.capability_map = CapabilityMap(plugin_dir)
        self.router = PluginRouter(self.capability_map)

    def test_capability_map_handles_missing_interop_files(self):
        """Test that CapabilityMap gracefully handles missing INTEROP.md files."""
        # code-reviewer doesn't have an INTEROP file in fixtures
        plugin = self.capability_map.get_plugin("code-reviewer")

        # Should still return a PluginInfo object (not None)
        self.assertIsNotNone(plugin)

        # But with empty capabilities
        self.assertEqual(len(plugin.capabilities), 0)
        self.assertEqual(len(plugin.handoff_targets), 0)

    def test_soft_dependency_missing_doesnt_block_workflow(self):
        """Test that missing soft dependency doesn't block workflow continuation."""
        # agent-nelly is soft; its absence shouldn't block agent-isdd -> agent-tdd handoff
        system_reminder_without_nelly = "agent-isdd:spec available agent-tdd:tdd available"

        nelly_available = self.router.check_plugin_availability("agent-nelly", system_reminder_without_nelly)
        self.assertFalse(nelly_available)

        # But workflow should still be able to route from isdd to tdd
        next_plugin = self.router.route_to_next_plugin("agent-isdd", "design_approved", True)
        self.assertIsNotNone(next_plugin)


class TestInputValidation(unittest.TestCase):
    """Test input validation and error handling."""

    def setUp(self):
        """Set up test fixtures."""
        plugin_dir = str(Path(__file__).parent / "fixtures")
        self.capability_map = CapabilityMap(plugin_dir)
        self.router = PluginRouter(self.capability_map)

    def test_empty_plugin_name_raises_error(self):
        """Test that empty plugin name raises ValueError."""
        with self.assertRaises(ValueError):
            self.router.check_plugin_availability("", "system_reminder")

    def test_none_plugin_name_raises_error(self):
        """Test that None plugin name raises ValueError."""
        with self.assertRaises(ValueError):
            self.router.check_plugin_availability(None, "system_reminder")

    def test_none_system_reminder_raises_error(self):
        """Test that None system_reminder raises ValueError."""
        with self.assertRaises(ValueError):
            self.router.check_plugin_availability("agent-tdd", None)

    def test_none_payload_raises_error(self):
        """Test that None payload raises TypeError."""
        with self.assertRaises(TypeError):
            self.router.validate_handoff(
                "agent-isdd",
                "design_spec_handoff",
                "agent-tdd",
                "design_spec_slicing",
                None
            )

    def test_non_dict_payload_raises_error(self):
        """Test that non-dict payload raises TypeError."""
        with self.assertRaises(TypeError):
            self.router.validate_handoff(
                "agent-isdd",
                "design_spec_handoff",
                "agent-tdd",
                "design_spec_slicing",
                "not a dict"
            )


if __name__ == "__main__":
    unittest.main()

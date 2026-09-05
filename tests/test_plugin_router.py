"""Tests for PluginRouter: availability checks, handoff validation, routing."""

import unittest
from orchestrator.core import PluginRouter
from orchestrator.interop_parser import CapabilityMap
from orchestrator.checkpoint import CheckpointManager


class TestPluginRouterInitialization(unittest.TestCase):
    """Test PluginRouter initialization and edge cases."""

    def test_init_with_valid_capability_map(self):
        """Test PluginRouter initializes with valid CapabilityMap."""
        from pathlib import Path
        plugin_dir = str(Path(__file__).parent / "fixtures")
        capability_map = CapabilityMap(plugin_dir)
        router = PluginRouter(capability_map)

        self.assertIsNotNone(router)
        self.assertEqual(router.capability_map, capability_map)

    def test_init_with_none_capability_map_raises(self):
        """Test PluginRouter raises TypeError when capability_map is None."""
        with self.assertRaises(TypeError) as context:
            PluginRouter(None)
        self.assertIn("capability_map", str(context.exception))


class TestPluginRouterAvailabilityChecks(unittest.TestCase):
    """Test plugin availability detection in system_reminder."""

    def setUp(self):
        """Set up test fixtures."""
        from pathlib import Path
        self.plugin_dir = str(Path(__file__).parent / "fixtures")
        self.capability_map = CapabilityMap(self.plugin_dir)
        self.router = PluginRouter(self.capability_map)

    def test_check_plugin_availability_agent_tdd_found(self):
        """Test detecting agent-tdd in system_reminder."""
        system_reminder = """
Some context...
agent-tdd:agent-TDD is available
More context...
"""
        result = self.router.check_plugin_availability("agent-tdd", system_reminder)
        self.assertTrue(result)

    def test_check_plugin_availability_agent_ux_found(self):
        """Test detecting agent-ux in system_reminder."""
        system_reminder = """
Setup context...
agent-ux:ux-agent is available
End context...
"""
        result = self.router.check_plugin_availability("agent-ux", system_reminder)
        self.assertTrue(result)

    def test_check_plugin_availability_agent_isdd_found(self):
        """Test detecting agent-isdd in system_reminder."""
        system_reminder = """
Context...
agent-isdd:spec-driven-development available
More...
"""
        result = self.router.check_plugin_availability("agent-isdd", system_reminder)
        self.assertTrue(result)

    def test_check_plugin_availability_not_found(self):
        """Test plugin not found returns False."""
        system_reminder = "Some context without agent-tdd"
        result = self.router.check_plugin_availability("agent-tdd", system_reminder)
        self.assertFalse(result)

    def test_check_plugin_availability_code_reviewer_found(self):
        """Test detecting code-reviewer in system_reminder."""
        system_reminder = "agent-context code-reviewer:code-reviewer available"
        result = self.router.check_plugin_availability("code-reviewer", system_reminder)
        self.assertTrue(result)

    def test_check_plugin_availability_without_agent_prefix(self):
        """Test check works with plugin name lacking agent- prefix."""
        system_reminder = "agent-tdd:agent-TDD available"
        result = self.router.check_plugin_availability("tdd", system_reminder)
        self.assertTrue(result)

    def test_check_plugin_availability_empty_string_raises(self):
        """Test empty plugin_name raises ValueError."""
        with self.assertRaises(ValueError) as context:
            self.router.check_plugin_availability("", "system_reminder")
        self.assertIn("plugin_name", str(context.exception))

    def test_check_plugin_availability_none_plugin_name_raises(self):
        """Test None plugin_name raises ValueError."""
        with self.assertRaises(ValueError) as context:
            self.router.check_plugin_availability(None, "system_reminder")
        self.assertIn("plugin_name", str(context.exception))

    def test_check_plugin_availability_none_system_reminder_raises(self):
        """Test None system_reminder raises ValueError."""
        with self.assertRaises(ValueError) as context:
            self.router.check_plugin_availability("agent-tdd", None)
        self.assertIn("system_reminder", str(context.exception))

    def test_is_hard_dependency_agent_tdd(self):
        """Test agent-tdd is hard dependency."""
        result = self.router.is_hard_dependency("agent-tdd")
        self.assertTrue(result)

    def test_is_hard_dependency_agent_isdd(self):
        """Test agent-isdd is hard dependency."""
        result = self.router.is_hard_dependency("agent-isdd")
        self.assertTrue(result)

    def test_is_hard_dependency_code_reviewer(self):
        """Test code-reviewer is hard dependency."""
        result = self.router.is_hard_dependency("code-reviewer")
        self.assertTrue(result)

    def test_is_hard_dependency_agent_nelly_false(self):
        """Test agent-nelly is not hard dependency."""
        result = self.router.is_hard_dependency("agent-nelly")
        self.assertFalse(result)

    def test_is_soft_dependency_agent_nelly(self):
        """Test agent-nelly is soft dependency."""
        result = self.router.is_soft_dependency("agent-nelly")
        self.assertTrue(result)

    def test_is_soft_dependency_agent_ux(self):
        """Test agent-ux is soft dependency."""
        result = self.router.is_soft_dependency("agent-ux")
        self.assertTrue(result)

    def test_is_soft_dependency_agent_tdd_false(self):
        """Test agent-tdd is not soft dependency."""
        result = self.router.is_soft_dependency("agent-tdd")
        self.assertFalse(result)


class TestPluginRouterHandoffValidation(unittest.TestCase):
    """Test handoff contract validation."""

    def setUp(self):
        """Set up test fixtures."""
        from pathlib import Path
        self.plugin_dir = str(Path(__file__).parent / "fixtures")
        self.capability_map = CapabilityMap(self.plugin_dir)
        self.router = PluginRouter(self.capability_map)

    def test_validate_handoff_valid_design_spec(self):
        """Test validating valid design spec handoff from isdd to tdd."""
        payload = {
            "requirements_md": "## Requirements\nContent here",
            "design_md": "## Design\nContent here",
            "research_cache": {"findings": "data"},
            "recap_md": "## Recap\nContent here"
        }

        is_valid, error = self.router.validate_handoff(
            "agent-isdd",
            "design_spec_handoff",
            "agent-tdd",
            "design_spec_slicing",
            payload
        )

        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_validate_handoff_missing_research_cache(self):
        """Test validation fails when research_cache is missing."""
        payload = {
            "requirements_md": "content",
            "design_md": "content",
            # Missing research_cache
            "recap_md": "content"
        }

        is_valid, error = self.router.validate_handoff(
            "agent-isdd",
            "design_spec_handoff",
            "agent-tdd",
            "design_spec_slicing",
            payload
        )

        self.assertFalse(is_valid)
        self.assertIsNotNone(error)
        self.assertIn("research_cache", error)

    def test_validate_handoff_missing_design_md(self):
        """Test validation fails when design_md is missing."""
        payload = {
            "requirements_md": "content",
            # Missing design_md
            "research_cache": {"data": "value"},
            "recap_md": "content"
        }

        is_valid, error = self.router.validate_handoff(
            "agent-isdd",
            "design_spec_handoff",
            "agent-tdd",
            "design_spec_slicing",
            payload
        )

        self.assertFalse(is_valid)
        self.assertIsNotNone(error)

    def test_validate_handoff_capability_not_found_source(self):
        """Test validation handles missing source capability."""
        payload = {"test": "data"}

        is_valid, error = self.router.validate_handoff(
            "agent-isdd",
            "nonexistent_capability",
            "agent-tdd",
            "design_spec_slicing",
            payload
        )

        self.assertFalse(is_valid)
        self.assertIsNotNone(error)

    def test_validate_handoff_capability_not_found_target(self):
        """Test validation handles missing target capability."""
        payload = {"test": "data"}

        is_valid, error = self.router.validate_handoff(
            "agent-isdd",
            "design_spec_handoff",
            "agent-tdd",
            "nonexistent_capability",
            payload
        )

        self.assertFalse(is_valid)
        self.assertIsNotNone(error)

    def test_validate_handoff_none_payload_raises(self):
        """Test None payload raises TypeError."""
        with self.assertRaises(TypeError) as context:
            self.router.validate_handoff(
                "agent-isdd",
                "design_spec_handoff",
                "agent-tdd",
                "design_spec_slicing",
                None
            )
        self.assertIn("payload", str(context.exception))

    def test_validate_handoff_non_dict_payload_raises(self):
        """Test non-dict payload raises TypeError."""
        with self.assertRaises(TypeError) as context:
            self.router.validate_handoff(
                "agent-isdd",
                "design_spec_handoff",
                "agent-tdd",
                "design_spec_slicing",
                "not a dict"
            )
        self.assertIn("payload", str(context.exception))
        self.assertIn("dict", str(context.exception))

    def test_validate_handoff_list_payload_raises(self):
        """Test list payload raises TypeError."""
        with self.assertRaises(TypeError) as context:
            self.router.validate_handoff(
                "agent-isdd",
                "design_spec_handoff",
                "agent-tdd",
                "design_spec_slicing",
                ["item1", "item2"]
            )
        self.assertIn("dict", str(context.exception))


class TestPluginRouterSequencing(unittest.TestCase):
    """Test route_to_next_plugin workflow sequencing."""

    def setUp(self):
        """Set up test fixtures."""
        self.plugin_dir = "/Users/jay.nelson/Codebase/AI/plugins/claude"
        self.capability_map = CapabilityMap(self.plugin_dir)
        self.router = PluginRouter(self.capability_map)

    def test_route_isdd_design_approved_to_tdd(self):
        """Test route from agent-isdd to agent-tdd when design is approved."""
        next_plugin = self.router.route_to_next_plugin(
            "agent-isdd",
            "design_approved",
            handoff_valid=True
        )

        self.assertEqual(next_plugin, "agent-tdd")

    def test_route_tdd_complete_to_code_reviewer(self):
        """Test route from agent-tdd to code-reviewer after red-green-refactor."""
        next_plugin = self.router.route_to_next_plugin(
            "agent-tdd",
            "red_green_refactor_complete",
            handoff_valid=True
        )

        self.assertEqual(next_plugin, "code-reviewer")

    def test_route_code_reviewer_complete_to_none(self):
        """Test route from code-reviewer ends workflow (returns None)."""
        next_plugin = self.router.route_to_next_plugin(
            "code-reviewer",
            "review_complete",
            handoff_valid=True
        )

        self.assertIsNone(next_plugin)

    def test_route_invalid_handoff_returns_none(self):
        """Test invalid handoff halts workflow (returns None)."""
        next_plugin = self.router.route_to_next_plugin(
            "agent-isdd",
            "design_approved",
            handoff_valid=False
        )

        self.assertIsNone(next_plugin)

    def test_route_unknown_plugin_returns_none(self):
        """Test unknown plugin returns None."""
        next_plugin = self.router.route_to_next_plugin(
            "unknown-plugin",
            "some_phase",
            handoff_valid=True
        )

        self.assertIsNone(next_plugin)

    def test_route_unknown_phase_returns_none(self):
        """Test unknown phase returns None."""
        next_plugin = self.router.route_to_next_plugin(
            "agent-isdd",
            "unknown_phase",
            handoff_valid=True
        )

        self.assertIsNone(next_plugin)


class TestPluginRouterCheckpointing(unittest.TestCase):
    """Test route_to_next_plugin auto-checkpointing via CheckpointManager."""

    def setUp(self):
        """Set up test fixtures."""
        plugin_dir = "/Users/jay.nelson/Codebase/AI/plugins/claude"
        self.capability_map = CapabilityMap(plugin_dir)
        self.router = PluginRouter(self.capability_map)
        self.checkpoint_manager = CheckpointManager()
        self.workflow_state = {}

    def test_checkpoint_created_before_valid_handoff_routes(self):
        """A checkpoint is created when routing to a next plugin."""
        next_plugin = self.router.route_to_next_plugin(
            "agent-isdd",
            "design_approved",
            handoff_valid=True,
            workflow_state=self.workflow_state,
            checkpoint_manager=self.checkpoint_manager
        )

        self.assertEqual(next_plugin, "agent-tdd")
        history = self.checkpoint_manager.get_checkpoint_history(self.workflow_state)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["label"], "before_agent-tdd_spawn")

    def test_no_checkpoint_created_when_workflow_ends(self):
        """No checkpoint is created when there is no next plugin to route to."""
        self.router.route_to_next_plugin(
            "code-reviewer",
            "review_complete",
            handoff_valid=True,
            workflow_state=self.workflow_state,
            checkpoint_manager=self.checkpoint_manager
        )

        history = self.checkpoint_manager.get_checkpoint_history(self.workflow_state)
        self.assertEqual(history, [])

    def test_no_checkpoint_created_on_invalid_handoff(self):
        """No checkpoint is created when the handoff itself was invalid."""
        self.router.route_to_next_plugin(
            "agent-isdd",
            "design_approved",
            handoff_valid=False,
            workflow_state=self.workflow_state,
            checkpoint_manager=self.checkpoint_manager
        )

        history = self.checkpoint_manager.get_checkpoint_history(self.workflow_state)
        self.assertEqual(history, [])

    def test_no_checkpoint_manager_is_backward_compatible(self):
        """Omitting workflow_state/checkpoint_manager still routes normally."""
        next_plugin = self.router.route_to_next_plugin(
            "agent-isdd",
            "design_approved",
            handoff_valid=True
        )

        self.assertEqual(next_plugin, "agent-tdd")


if __name__ == "__main__":
    unittest.main()

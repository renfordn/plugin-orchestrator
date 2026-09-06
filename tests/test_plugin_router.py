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

    def test_transform_payload_no_mapping_returns_copy(self):
        """Test transform_payload with nothing registered returns an equal copy."""
        payload = {"a": 1}

        result = self.router.transform_payload(
            "agent-isdd", "design_spec_handoff", "agent-tdd", "design_spec_slicing", payload
        )

        self.assertEqual(result, payload)
        self.assertIsNot(result, payload)

    def test_payload_mapping_renames_fields(self):
        """Test set_payload_mapping renames source fields to target field names."""
        self.router.set_payload_mapping(
            "agent-isdd", "agent-tdd", {"spec_md": "design_md"}
        )

        result = self.router.transform_payload(
            "agent-isdd", "design_spec_handoff", "agent-tdd", "design_spec_slicing",
            {"spec_md": "content"}
        )

        self.assertEqual(result, {"design_md": "content"})

    def test_payload_mapping_enables_handoff_that_would_otherwise_fail(self):
        """Test a registered mapping lets validate_handoff succeed on renamed fields."""
        self.router.set_payload_mapping(
            "agent-isdd", "agent-tdd", {"spec_md": "design_md"}
        )
        payload = {
            "requirements_md": "content",
            "spec_md": "content",  # would fail without mapping to design_md
            "research_cache": {"data": "value"},
            "recap_md": "content"
        }

        is_valid, error = self.router.validate_handoff(
            "agent-isdd", "design_spec_handoff", "agent-tdd", "design_spec_slicing", payload
        )

        self.assertTrue(is_valid)
        self.assertIsNone(error)
        # Original payload dict passed in is untouched.
        self.assertIn("spec_md", payload)
        self.assertNotIn("design_md", payload)

    def test_clear_payload_mapping_restores_default(self):
        """Test clear_payload_mapping removes a previously registered mapping."""
        self.router.set_payload_mapping(
            "agent-isdd", "agent-tdd", {"spec_md": "design_md"}
        )
        self.router.clear_payload_mapping("agent-isdd", "agent-tdd")

        result = self.router.transform_payload(
            "agent-isdd", "design_spec_handoff", "agent-tdd", "design_spec_slicing",
            {"spec_md": "content"}
        )

        self.assertEqual(result, {"spec_md": "content"})

    def test_payload_transformer_runs_after_mapping(self):
        """Test set_payload_transformer applies a custom callable after field mapping."""
        self.router.set_payload_mapping(
            "agent-isdd", "agent-tdd", {"spec_md": "design_md"}
        )
        self.router.set_payload_transformer(
            lambda source, source_cap, target, target_cap, payload: {
                **payload, "design_md": payload["design_md"].upper()
            }
        )

        result = self.router.transform_payload(
            "agent-isdd", "design_spec_handoff", "agent-tdd", "design_spec_slicing",
            {"spec_md": "content"}
        )

        self.assertEqual(result, {"design_md": "CONTENT"})

    def test_clear_payload_transformer(self):
        """Test clear_payload_transformer removes the custom transformer."""
        self.router.set_payload_transformer(
            lambda source, source_cap, target, target_cap, payload: {"replaced": True}
        )
        self.router.clear_payload_transformer()

        result = self.router.transform_payload(
            "agent-isdd", "design_spec_handoff", "agent-tdd", "design_spec_slicing",
            {"a": 1}
        )

        self.assertEqual(result, {"a": 1})


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

    def test_routing_policy_overrides_table(self):
        """Test a custom routing policy takes precedence over ROUTING_TABLE."""
        self.router.set_routing_policy(
            lambda plugin, phase, workflow_state: "agent-ux"
        )

        next_plugin = self.router.route_to_next_plugin(
            "agent-isdd",
            "design_approved",
            handoff_valid=True
        )

        self.assertEqual(next_plugin, "agent-ux")

    def test_routing_policy_receives_workflow_state(self):
        """Test the routing policy is called with plugin, phase, and workflow_state."""
        seen = {}

        def policy(plugin, phase, workflow_state):
            seen["args"] = (plugin, phase, workflow_state)
            return None

        self.router.set_routing_policy(policy)
        state = {"foo": "bar"}

        self.router.route_to_next_plugin(
            "agent-isdd", "design_approved", handoff_valid=True, workflow_state=state
        )

        self.assertEqual(seen["args"], ("agent-isdd", "design_approved", state))

    def test_routing_policy_deferring_falls_back_to_table(self):
        """Test PluginRouter.USE_DEFAULT_ROUTE lets the policy defer to ROUTING_TABLE."""
        from orchestrator.core import PluginRouter

        self.router.set_routing_policy(
            lambda plugin, phase, workflow_state: PluginRouter.USE_DEFAULT_ROUTE
        )

        next_plugin = self.router.route_to_next_plugin(
            "agent-isdd", "design_approved", handoff_valid=True
        )

        self.assertEqual(next_plugin, "agent-tdd")

    def test_routing_policy_none_ends_workflow(self):
        """Test a policy explicitly returning None ends the workflow, no fallback."""
        self.router.set_routing_policy(
            lambda plugin, phase, workflow_state: None
        )

        next_plugin = self.router.route_to_next_plugin(
            "agent-isdd", "design_approved", handoff_valid=True
        )

        self.assertIsNone(next_plugin)

    def test_invalid_handoff_skips_routing_policy(self):
        """Test an invalid handoff still halts the workflow even with a policy set."""
        self.router.set_routing_policy(
            lambda plugin, phase, workflow_state: "agent-ux"
        )

        next_plugin = self.router.route_to_next_plugin(
            "agent-isdd", "design_approved", handoff_valid=False
        )

        self.assertIsNone(next_plugin)

    def test_clear_routing_policy_restores_table_behavior(self):
        """Test clear_routing_policy removes a previously set policy."""
        self.router.set_routing_policy(
            lambda plugin, phase, workflow_state: "agent-ux"
        )
        self.router.clear_routing_policy()

        next_plugin = self.router.route_to_next_plugin(
            "agent-isdd", "design_approved", handoff_valid=True
        )

        self.assertEqual(next_plugin, "agent-tdd")


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

    def test_valid_handoff_recorded_in_handoff_history(self):
        """Routing to a next plugin is recorded in the handoff history log."""
        self.router.route_to_next_plugin(
            "agent-isdd", "design_approved", handoff_valid=True,
            workflow_state=self.workflow_state, checkpoint_manager=self.checkpoint_manager
        )

        history = self.checkpoint_manager.get_handoff_history(self.workflow_state)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["next_plugin"], "agent-tdd")
        self.assertTrue(history[0]["handoff_valid"])

    def test_invalid_handoff_recorded_in_handoff_history(self):
        """An invalid handoff is recorded in history even though no checkpoint is made."""
        self.router.route_to_next_plugin(
            "agent-isdd", "design_approved", handoff_valid=False,
            workflow_state=self.workflow_state, checkpoint_manager=self.checkpoint_manager
        )

        history = self.checkpoint_manager.get_handoff_history(self.workflow_state)
        self.assertEqual(len(history), 1)
        self.assertFalse(history[0]["handoff_valid"])
        self.assertIsNone(history[0]["next_plugin"])

    def test_end_of_workflow_recorded_in_handoff_history(self):
        """Reaching the end of the workflow (no checkpoint) is still recorded."""
        self.router.route_to_next_plugin(
            "code-reviewer", "review_complete", handoff_valid=True,
            workflow_state=self.workflow_state, checkpoint_manager=self.checkpoint_manager
        )

        history = self.checkpoint_manager.get_handoff_history(self.workflow_state)
        self.assertEqual(len(history), 1)
        self.assertIsNone(history[0]["next_plugin"])


if __name__ == "__main__":
    unittest.main()

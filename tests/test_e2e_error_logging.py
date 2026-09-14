"""End-to-end integration test: error occurs -> logged -> persisted -> pattern
detected -> surfaced via nelly integration (both proactive brief and on-demand query).

Slice 2.3 of the Orchestration Error Logging & Nelly Integration feature.
"""

import json
import unittest
import tempfile
import shutil
from pathlib import Path
from orchestrator.core import PluginRouter
from orchestrator.interop_parser import CapabilityMap
from orchestrator.error_logger import ErrorLogger
from orchestrator.nelly_integration import ErrorPatternManager
from orchestrator.hooks.before_continue import handle_agent_spawn


class TestEndToEndErrorLogging(unittest.TestCase):
    """End-to-end: error capture through to nelly surfacing."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.project_slug = "e2e-test-project"
        self.plugin_dir = str(Path(__file__).parent / "fixtures")
        self.capability_map = CapabilityMap(self.plugin_dir)
        self.error_logger = ErrorLogger()
        self.router = PluginRouter(self.capability_map, error_logger=self.error_logger)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_full_workflow_error_to_nelly_proactive_pattern(self):
        """Error occurs twice via PluginRouter -> persisted -> pattern detected -> surfaced in hook context."""
        # Step 1: Trigger the SAME orchestration error twice (recurring pattern threshold)
        for _ in range(2):
            available = self.router.check_plugin_availability(
                "agent-tdd", "no plugins mentioned in this session"
            )
            self.assertFalse(available)

        # Step 2: Persist session errors to the project-wide registry (as agent-isdd would)
        for error in self.error_logger.get_session_errors():
            self.error_logger.persist_error(error, self.temp_dir, self.project_slug)

        registry_path = Path(self.temp_dir) / self.project_slug / "error-registry.json"
        self.assertTrue(registry_path.exists())

        with open(registry_path) as f:
            registry = json.load(f)
        self.assertEqual(len(registry["errors"]), 2)

        # Step 3: Pattern detection recognizes the recurrence
        manager = ErrorPatternManager(registry_path)
        patterns = manager.get_high_severity_pattern_dicts()
        # plugin_unavailable severity is "high" only for hard dependencies;
        # agent-tdd is a hard dependency, so this should be high severity.
        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0]["error_type"], "plugin_unavailable")
        self.assertEqual(patterns[0]["occurrence_frequency"], "2 times in past 7 days")

        # Step 4: before_continue hook surfaces the pattern proactively on next spawn
        workflow_state = {"orchestration": {}, "error_registry_path": str(registry_path)}
        modified_prompt = handle_agent_spawn("agent-tdd", "implement the feature", workflow_state)

        self.assertIn("ERROR PATTERNS", modified_prompt)
        self.assertIn("plugin_unavailable", modified_prompt)
        self.assertIn("implement the feature", modified_prompt)  # original prompt preserved

    def test_full_workflow_on_demand_query(self):
        """Errors persisted -> on-demand nelly query returns ranked history for a specific plugin."""
        # Trigger errors for two different plugins
        self.router.check_plugin_availability("agent-tdd", "nothing here")
        self.router.check_plugin_availability("agent-nelly", "nothing here")

        for error in self.error_logger.get_session_errors():
            self.error_logger.persist_error(error, self.temp_dir, self.project_slug)

        registry_path = Path(self.temp_dir) / self.project_slug / "error-registry.json"
        manager = ErrorPatternManager(registry_path)

        result = manager.query_error_history(plugin="agent-tdd")
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(result["errors"][0]["source_plugin"], "agent-tdd")

    def test_graceful_degradation_missing_registry_does_not_block_workflow(self):
        """Orchestration continues normally when no error registry exists at all."""
        workflow_state = {"orchestration": {}}  # no error_registry_path configured
        modified_prompt = handle_agent_spawn("agent-tdd", "do work", workflow_state)

        self.assertIn("do work", modified_prompt)
        self.assertNotIn("ERROR PATTERNS", modified_prompt)

    def test_graceful_degradation_corrupted_registry_does_not_block_workflow(self):
        """Orchestration continues normally when the error registry file is corrupted."""
        registry_dir = Path(self.temp_dir) / self.project_slug
        registry_dir.mkdir(parents=True)
        registry_path = registry_dir / "error-registry.json"
        with open(registry_path, "w") as f:
            f.write("{ this is not valid json")

        workflow_state = {"orchestration": {}, "error_registry_path": str(registry_path)}
        modified_prompt = handle_agent_spawn("agent-tdd", "do work", workflow_state)

        self.assertIn("do work", modified_prompt)
        self.assertNotIn("ERROR PATTERNS", modified_prompt)

    def test_no_pattern_below_recurrence_threshold(self):
        """A single occurrence of an error type does not surface as a pattern."""
        self.router.check_plugin_availability("agent-tdd", "nothing here")

        for error in self.error_logger.get_session_errors():
            self.error_logger.persist_error(error, self.temp_dir, self.project_slug)

        registry_path = Path(self.temp_dir) / self.project_slug / "error-registry.json"
        manager = ErrorPatternManager(registry_path)
        patterns = manager.get_high_severity_pattern_dicts()

        self.assertEqual(len(patterns), 0)

    def test_routing_and_handoff_errors_also_flow_end_to_end(self):
        """Routing and handoff-validation errors (not just availability) also reach the registry."""
        # Routing failure: unmapped (plugin, phase)
        self.router.route_to_next_plugin("unknown-plugin", "unknown-phase", handoff_valid=True)
        # Handoff validation failure: unknown capability
        self.router.validate_handoff(
            "nonexistent", "cap", "agent-tdd", "design_spec_slicing", {}
        )

        for error in self.error_logger.get_session_errors():
            self.error_logger.persist_error(error, self.temp_dir, self.project_slug)

        registry_path = Path(self.temp_dir) / self.project_slug / "error-registry.json"
        with open(registry_path) as f:
            registry = json.load(f)

        error_types = {e["error_type"] for e in registry["errors"]}
        self.assertIn("routing_failed", error_types)
        self.assertIn("handoff_validation", error_types)

"""Tests for CapabilityMap parser and registry."""

import json
import tempfile
import unittest
from pathlib import Path

from orchestrator.interop_parser import CapabilityMap


class TestCapabilityMapParsing(unittest.TestCase):
    """Test INTEROP.md parsing and capability registry."""

    def setUp(self):
        """Set up test fixtures."""
        self.plugin_dir = Path(__file__).parent / "fixtures"
        self.temp_workflow_state = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        )
        self.temp_workflow_state.close()

    def tearDown(self):
        """Clean up temp files."""
        if Path(self.temp_workflow_state.name).exists():
            Path(self.temp_workflow_state.name).unlink()

    def test_capability_map_initialization(self):
        """Test CapabilityMap can be initialized with plugin directory."""
        cap_map = CapabilityMap(str(self.plugin_dir))
        self.assertIsNotNone(cap_map)

    def test_get_plugin_agent_isdd(self):
        """Test retrieving agent-isdd plugin info."""
        cap_map = CapabilityMap(str(self.plugin_dir))
        plugin = cap_map.get_plugin("agent-isdd")

        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.name, "agent-isdd")
        # agent-isdd should have handoff targets
        self.assertIn("agent-tdd", plugin.handoff_targets)
        self.assertIn("agent-nelly", plugin.handoff_targets)
        self.assertIn("agent-ux", plugin.handoff_targets)

    def test_get_plugin_agent_tdd(self):
        """Test retrieving agent-tdd plugin info."""
        cap_map = CapabilityMap(str(self.plugin_dir))
        plugin = cap_map.get_plugin("agent-tdd")

        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.name, "agent-tdd")

    def test_get_plugin_nonexistent(self):
        """Test getting nonexistent plugin returns None."""
        cap_map = CapabilityMap(str(self.plugin_dir))
        plugin = cap_map.get_plugin("nonexistent-plugin")

        self.assertIsNone(plugin)

    def test_find_capability(self):
        """Test finding specific capability by plugin and ID."""
        cap_map = CapabilityMap(str(self.plugin_dir))

        # agent-isdd should have a capability to hand off to agent-tdd
        capability = cap_map.find_capability("agent-isdd", "design_spec_handoff")

        self.assertIsNotNone(capability)
        self.assertEqual(capability.plugin, "agent-isdd")
        self.assertEqual(capability.id, "design_spec_handoff")

    def test_find_capability_nonexistent(self):
        """Test finding nonexistent capability returns None."""
        cap_map = CapabilityMap(str(self.plugin_dir))
        capability = cap_map.find_capability("agent-isdd", "nonexistent_capability")

        self.assertIsNone(capability)

    def test_validate_input_design_spec_format(self):
        """Test input validation for design spec format."""
        cap_map = CapabilityMap(str(self.plugin_dir))

        # Valid design spec input
        valid_input = {
            "requirements_md": "content",
            "design_md": "content",
            "research_cache": "content",
            "recap_md": "content"
        }

        is_valid, error = cap_map.validate_input(
            "agent-tdd",
            "design_spec_slicing",
            valid_input
        )

        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_validate_input_invalid_format(self):
        """Test input validation rejects invalid format."""
        cap_map = CapabilityMap(str(self.plugin_dir))

        # Missing required fields
        invalid_input = {"foo": "bar"}

        is_valid, error = cap_map.validate_input(
            "agent-tdd",
            "design_spec_slicing",
            invalid_input
        )

        self.assertFalse(is_valid)
        self.assertIsNotNone(error)

    def test_validate_input_schema_valid_types(self):
        """Test schema validation accepts input matching declared JSON types."""
        cap_map = CapabilityMap(str(self.plugin_dir))

        valid_input = {
            "requirements_md": "content",
            "design_md": "content",
            "research_cache": {"key": "value"},
            "recap_md": "content"
        }

        is_valid, error = cap_map.validate_input_schema(
            "agent-tdd",
            "design_spec_slicing",
            valid_input
        )

        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_validate_input_schema_type_mismatch(self):
        """Test schema validation rejects a field whose type doesn't match consumes contract."""
        cap_map = CapabilityMap(str(self.plugin_dir))

        # research_cache is declared "object" but given a string
        invalid_input = {
            "requirements_md": "content",
            "design_md": "content",
            "research_cache": "not-an-object",
            "recap_md": "content"
        }

        is_valid, error = cap_map.validate_input_schema(
            "agent-tdd",
            "design_spec_slicing",
            invalid_input
        )

        self.assertFalse(is_valid)
        self.assertIn("research_cache", error)

    def test_validate_input_schema_missing_field(self):
        """Test schema validation still reports missing required fields."""
        cap_map = CapabilityMap(str(self.plugin_dir))

        is_valid, error = cap_map.validate_input_schema(
            "agent-tdd",
            "design_spec_slicing",
            {"foo": "bar"}
        )

        self.assertFalse(is_valid)
        self.assertIsNotNone(error)

    def test_validate_input_schema_unknown_capability(self):
        """Test schema validation on an unknown capability returns an error."""
        cap_map = CapabilityMap(str(self.plugin_dir))

        is_valid, error = cap_map.validate_input_schema(
            "agent-isdd",
            "nonexistent_capability",
            {}
        )

        self.assertFalse(is_valid)
        self.assertIsNotNone(error)

    def test_is_soft_dependency_agent_nelly(self):
        """Test agent-nelly is recognized as soft dependency."""
        cap_map = CapabilityMap(str(self.plugin_dir))

        is_soft = cap_map.is_soft_dependency("agent-nelly")

        self.assertTrue(is_soft)

    def test_is_soft_dependency_agent_tdd(self):
        """Test agent-tdd is not a soft dependency."""
        cap_map = CapabilityMap(str(self.plugin_dir))

        is_soft = cap_map.is_soft_dependency("agent-tdd")

        self.assertFalse(is_soft)

    def test_route_to_next_plugin_from_isdd(self):
        """Test routing from agent-isdd to next capable plugin."""
        cap_map = CapabilityMap(str(self.plugin_dir))

        # Simulate agent-isdd handoff output
        output = {
            "type": "design_spec",
            "requirements_md": "...",
            "design_md": "...",
        }

        next_plugin = cap_map.route_to_next_plugin("agent-isdd", output)

        # Should route to agent-tdd for implementation
        self.assertIsNotNone(next_plugin)
        self.assertIn(next_plugin, ["agent-tdd", "agent-nelly", "agent-ux"])

    def test_cache_save_and_retrieve(self):
        """Test caching capability map to workflow-state.json."""
        cap_map = CapabilityMap(str(self.plugin_dir))

        # Save to cache
        cap_map.save_to_cache(self.temp_workflow_state.name)

        # Verify file was created and contains expected structure
        with open(self.temp_workflow_state.name, 'r') as f:
            cached = json.load(f)

        self.assertIn("capability_map", cached)
        self.assertIn("interop_hashes", cached)
        self.assertIsNotNone(cached["interop_hashes"])

    def test_cache_retrieval_with_unchanged_hashes(self):
        """Test retrieving cached map when hashes are unchanged."""
        # Create initial cache
        cap_map1 = CapabilityMap(str(self.plugin_dir))
        cap_map1.save_to_cache(self.temp_workflow_state.name)

        # Retrieve cached map
        cap_map2 = CapabilityMap.get_cached_map(self.temp_workflow_state.name, str(self.plugin_dir))

        self.assertIsNotNone(cap_map2)

        # Verify plugin data is same
        plugin1 = cap_map1.get_plugin("agent-isdd")
        plugin2 = cap_map2.get_plugin("agent-isdd")

        self.assertEqual(plugin1.name, plugin2.name)
        self.assertEqual(plugin1.handoff_targets, plugin2.handoff_targets)

    def test_invalidate_on_interop_change(self):
        """Test cache invalidation when INTEROP.md changes."""
        cap_map = CapabilityMap(str(self.plugin_dir))

        # Get current hashes
        current_hashes = cap_map.get_interop_hashes()

        # Fake a changed hash
        changed_hashes = dict(current_hashes)
        if changed_hashes:
            first_key = next(iter(changed_hashes))
            changed_hashes[first_key] = "modified_hash_value"

        # Should detect change
        is_invalid = cap_map.invalidate_on_interop_change(changed_hashes)

        self.assertTrue(is_invalid)

    def test_all_plugins_parsed(self):
        """Test that all 6 plugins are parsed."""
        cap_map = CapabilityMap(str(self.plugin_dir))

        expected_plugins = {
            "agent-isdd",
            "agent-tdd",
            "agent-nelly",
            "agent-ux",
            "code-reviewer",
            "agent-cache-plugin"
        }

        for plugin_name in expected_plugins:
            # All plugins should be queryable, even if some don't have INTEROP.md
            plugin = cap_map.get_plugin(plugin_name)
            # At minimum, plugin object should exist
            self.assertIsNotNone(plugin)
            self.assertEqual(plugin.name, plugin_name)


class TestCapabilityMapRefactoring(unittest.TestCase):
    """Test refactored parsing logic and edge cases."""

    def setUp(self):
        """Set up test fixtures."""
        self.plugin_dir = Path(__file__).parent / "fixtures"
        self.temp_workflow_state = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        )
        self.temp_workflow_state.close()

    def tearDown(self):
        """Clean up temp files."""
        if Path(self.temp_workflow_state.name).exists():
            Path(self.temp_workflow_state.name).unlink()

    def test_cache_deserialization_maintains_data_integrity(self):
        """Test that cached data is correctly deserialized without mutation."""
        cap_map1 = CapabilityMap(str(self.plugin_dir))

        # Save to cache
        cap_map1.save_to_cache(self.temp_workflow_state.name)

        # Load from cache
        cap_map2 = CapabilityMap.get_cached_map(self.temp_workflow_state.name, str(self.plugin_dir))

        # Verify all plugins are preserved
        for plugin_name in ["agent-isdd", "agent-tdd", "agent-nelly", "agent-ux"]:
            plugin1 = cap_map1.get_plugin(plugin_name)
            plugin2 = cap_map2.get_plugin(plugin_name)

            self.assertEqual(plugin1.name, plugin2.name)
            self.assertEqual(plugin1.handoff_targets, plugin2.handoff_targets)
            self.assertEqual(
                len(plugin1.capabilities),
                len(plugin2.capabilities),
                f"Capability count mismatch for {plugin_name}"
            )

            # Verify capabilities are preserved
            for cap1, cap2 in zip(plugin1.capabilities, plugin2.capabilities):
                self.assertEqual(cap1.id, cap2.id)
                self.assertEqual(cap1.plugin, cap2.plugin)
                self.assertEqual(cap1.consumes, cap2.consumes)

    def test_cache_with_empty_workflow_state_file(self):
        """Test cache retrieval when workflow state file doesn't exist."""
        nonexistent_path = "/tmp/nonexistent_workflow_state_" + str(
            Path(self.temp_workflow_state.name).stem
        ) + ".json"

        result = CapabilityMap.get_cached_map(nonexistent_path)

        self.assertIsNone(result)

    def test_hash_detection_catches_changes(self):
        """Test that hash comparison correctly detects changes."""
        cap_map1 = CapabilityMap(str(self.plugin_dir))
        original_hashes = cap_map1.get_interop_hashes()

        # Create modified hashes (simulate INTEROP.md change)
        modified_hashes = dict(original_hashes)
        if "agent-isdd" in modified_hashes:
            modified_hashes["agent-isdd"] = "different_hash_value"

        # Should detect change
        is_invalid = cap_map1.invalidate_on_interop_change(modified_hashes)

        self.assertTrue(is_invalid)

    def test_plugin_without_interop_file_has_no_capabilities(self):
        """Test that plugin without INTEROP.md gets empty capabilities list."""
        cap_map = CapabilityMap(str(self.plugin_dir))

        # code-reviewer doesn't have INTEROP.md
        plugin = cap_map.get_plugin("code-reviewer")

        self.assertIsNotNone(plugin)
        self.assertEqual(len(plugin.capabilities), 0)
        self.assertEqual(len(plugin.handoff_targets), 0)

    def test_soft_dependency_detection(self):
        """Test soft dependency flags are correctly set."""
        cap_map = CapabilityMap(str(self.plugin_dir))

        agent_nelly = cap_map.get_plugin("agent-nelly")
        agent_tdd = cap_map.get_plugin("agent-tdd")

        # agent-nelly should be soft dependency
        self.assertTrue(agent_nelly.is_soft_dependency)

        # agent-tdd should not be soft dependency
        self.assertFalse(agent_tdd.is_soft_dependency)

    def test_handoff_target_extraction(self):
        """Test that handoff targets are correctly extracted."""
        cap_map = CapabilityMap(str(self.plugin_dir))

        agent_isdd = cap_map.get_plugin("agent-isdd")

        # agent-isdd should have handoff targets
        self.assertGreater(len(agent_isdd.handoff_targets), 0)

        # Should include known handoff targets
        expected_targets = {"agent-tdd", "agent-nelly", "agent-ux"}
        actual_targets = set(agent_isdd.handoff_targets)

        self.assertTrue(expected_targets.issubset(actual_targets))

    def test_capability_consumes_contract(self):
        """Test that consumes contract is properly captured."""
        cap_map = CapabilityMap(str(self.plugin_dir))

        design_spec_cap = cap_map.find_capability(
            "agent-tdd",
            "design_spec_slicing"
        )

        self.assertIsNotNone(design_spec_cap)
        self.assertIn("requirements_md", design_spec_cap.consumes)
        self.assertIn("design_md", design_spec_cap.consumes)
        self.assertIn("research_cache", design_spec_cap.consumes)

    def test_multiple_plugin_parsing_consistency(self):
        """Test that multiple CapabilityMap instances produce same results."""
        cap_map1 = CapabilityMap(str(self.plugin_dir))
        cap_map2 = CapabilityMap(str(self.plugin_dir))

        # Both should have same plugin count
        self.assertEqual(len(cap_map1.plugins), len(cap_map2.plugins))

        # All plugin data should match
        for plugin_name in cap_map1.plugins:
            plugin1 = cap_map1.get_plugin(plugin_name)
            plugin2 = cap_map2.get_plugin(plugin_name)

            self.assertEqual(plugin1.name, plugin2.name)
            self.assertEqual(plugin1.handoff_targets, plugin2.handoff_targets)
            self.assertEqual(plugin1.is_soft_dependency, plugin2.is_soft_dependency)


if __name__ == "__main__":
    unittest.main()

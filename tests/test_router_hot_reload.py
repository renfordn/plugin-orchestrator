"""Tests for PluginRouter picking up hot-reloaded capabilities via refresh()."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from orchestrator.core import PluginRouter
from orchestrator.interop_parser import CapabilityMap


class TestRouterHotReload(unittest.TestCase):
    """Test that handoff validation sees capability changes without a new PluginRouter."""

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        fixtures = Path(__file__).parent / "fixtures"
        for plugin in ["agent-isdd", "agent-tdd", "agent-nelly", "agent-ux"]:
            shutil.copytree(fixtures / plugin, self.tmp_dir / plugin)

        self.capability_map = CapabilityMap(str(self.tmp_dir))
        self.router = PluginRouter(self.capability_map)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_validate_handoff_sees_capability_removed_from_disk(self):
        payload = {
            "requirements_md": "reqs",
            "design_md": "design",
            "research_cache": {},
            "recap_md": "recap",
        }
        is_valid, error = self.router.validate_handoff(
            "agent-isdd", "design_spec_handoff",
            "agent-tdd", "design_spec_slicing",
            payload
        )
        self.assertTrue(is_valid, error)

        # Simulate the plugin author renaming/removing the capability's marker
        # text on disk mid-session (no new CapabilityMap/PluginRouter created).
        tdd_interop = self.tmp_dir / "agent-tdd" / "INTEROP.md"
        content = tdd_interop.read_text(encoding="utf-8")
        content = content.replace("Design Spec", "Renamed").replace("Slice Spec", "Renamed")
        tdd_interop.write_text(content, encoding="utf-8")

        is_valid, error = self.router.validate_handoff(
            "agent-isdd", "design_spec_handoff",
            "agent-tdd", "design_spec_slicing",
            payload
        )
        self.assertFalse(is_valid)
        self.assertIn("design_spec_slicing", error)


class TestRoutingTableHotReload(unittest.TestCase):
    """Test PluginRouter picking up routing_table.json edits without a restart."""

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        fixtures = Path(__file__).parent / "fixtures"
        for plugin in ["agent-isdd", "agent-tdd", "agent-nelly", "agent-ux"]:
            shutil.copytree(fixtures / plugin, self.tmp_dir / plugin)

        self.routing_table_path = self.tmp_dir / "routing_table.json"
        self.routing_table_path.write_text(json.dumps({
            "routes": [
                {"plugin": "agent-isdd", "phase": "design_approved", "next": "agent-tdd"},
            ]
        }))

        self.capability_map = CapabilityMap(str(self.tmp_dir))
        self.router = PluginRouter(
            self.capability_map, routing_table_path=str(self.routing_table_path)
        )

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_route_reflects_table_edited_on_disk(self):
        # Before edit: no route defined for this (plugin, phase).
        next_plugin = self.router.route_to_next_plugin(
            "agent-tdd", "red_green_refactor_complete", handoff_valid=True
        )
        self.assertIsNone(next_plugin)

        # Simulate an operator adding a route at runtime, no restart.
        self.routing_table_path.write_text(json.dumps({
            "routes": [
                {"plugin": "agent-isdd", "phase": "design_approved", "next": "agent-tdd"},
                {"plugin": "agent-tdd", "phase": "red_green_refactor_complete", "next": "agent-nelly"},
            ]
        }))

        next_plugin = self.router.route_to_next_plugin(
            "agent-tdd", "red_green_refactor_complete", handoff_valid=True
        )
        self.assertEqual(next_plugin, "agent-nelly")

    def test_refresh_routing_table_returns_whether_it_changed(self):
        self.assertFalse(self.router.refresh_routing_table())

        self.routing_table_path.write_text(json.dumps({
            "routes": [
                {"plugin": "agent-isdd", "phase": "design_approved", "next": "agent-ux"},
            ]
        }))

        self.assertTrue(self.router.refresh_routing_table())
        self.assertFalse(self.router.refresh_routing_table())

    def test_custom_routing_policy_still_overrides_reloaded_table(self):
        self.router.set_routing_policy(
            lambda plugin, phase, workflow_state: "agent-ux"
        )

        self.routing_table_path.write_text(json.dumps({
            "routes": [
                {"plugin": "agent-isdd", "phase": "design_approved", "next": "agent-nelly"},
            ]
        }))

        next_plugin = self.router.route_to_next_plugin(
            "agent-isdd", "design_approved", handoff_valid=True
        )
        self.assertEqual(next_plugin, "agent-ux")


if __name__ == "__main__":
    unittest.main()

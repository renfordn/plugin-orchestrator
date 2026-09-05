"""Tests for PluginRouter picking up hot-reloaded capabilities via refresh()."""

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


if __name__ == "__main__":
    unittest.main()

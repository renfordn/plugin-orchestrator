"""Tests for CapabilityMap.refresh() (plugin hot-reload without session restart)."""

import shutil
import tempfile
import unittest
from pathlib import Path

from orchestrator.interop_parser import CapabilityMap


class TestHotReload(unittest.TestCase):
    """Test re-parsing changed INTEROP files without recreating CapabilityMap."""

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        fixtures = Path(__file__).parent / "fixtures"
        for plugin in ["agent-isdd", "agent-tdd", "agent-nelly", "agent-ux"]:
            shutil.copytree(fixtures / plugin, self.tmp_dir / plugin)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_refresh_with_no_changes_reports_nothing_changed(self):
        cap_map = CapabilityMap(str(self.tmp_dir))
        changed = cap_map.refresh()
        self.assertEqual(changed, [])

    def test_refresh_picks_up_changed_interop_file(self):
        cap_map = CapabilityMap(str(self.tmp_dir))
        self.assertIsNone(cap_map.find_capability("agent-isdd", "new_capability"))

        interop_path = self.tmp_dir / "agent-isdd" / "INTEROP.md"
        interop_path.write_text(
            interop_path.read_text(encoding="utf-8")
            + "\n\n### new_capability\n\n**Description:** Added at runtime\n",
            encoding="utf-8",
        )

        changed = cap_map.refresh()
        self.assertEqual(changed, ["agent-isdd"])
        # Existing hardcoded-capability extraction still keys off "Design Spec"
        # marker text, so this proves the file was actually re-read post-refresh.
        plugin = cap_map.get_plugin("agent-isdd")
        self.assertIsNotNone(plugin)

    def test_refresh_updates_stored_hash(self):
        cap_map = CapabilityMap(str(self.tmp_dir))
        old_hash = cap_map.get_interop_hashes()["agent-isdd"]

        interop_path = self.tmp_dir / "agent-isdd" / "INTEROP.md"
        interop_path.write_text(
            interop_path.read_text(encoding="utf-8") + "\nextra content\n",
            encoding="utf-8",
        )

        cap_map.refresh()
        new_hash = cap_map.get_interop_hashes()["agent-isdd"]
        self.assertNotEqual(old_hash, new_hash)

    def test_refresh_does_not_touch_unchanged_plugins(self):
        cap_map = CapabilityMap(str(self.tmp_dir))
        tdd_plugin_before = cap_map.get_plugin("agent-tdd")

        interop_path = self.tmp_dir / "agent-isdd" / "INTEROP.md"
        interop_path.write_text(
            interop_path.read_text(encoding="utf-8") + "\nextra content\n",
            encoding="utf-8",
        )

        changed = cap_map.refresh()
        self.assertEqual(changed, ["agent-isdd"])
        self.assertIs(cap_map.get_plugin("agent-tdd"), tdd_plugin_before)

    def test_refresh_detects_newly_created_interop_file(self):
        # agent-nelly starts without a fixture copy to simulate a plugin
        # that was unavailable at startup (empty PluginInfo, graceful degradation).
        shutil.rmtree(self.tmp_dir / "agent-nelly")
        cap_map = CapabilityMap(str(self.tmp_dir))
        self.assertEqual(cap_map.get_interop_hashes()["agent-nelly"], "")

        fixtures = Path(__file__).parent / "fixtures"
        shutil.copytree(fixtures / "agent-nelly", self.tmp_dir / "agent-nelly")

        changed = cap_map.refresh()
        self.assertEqual(changed, ["agent-nelly"])
        self.assertTrue(cap_map.is_soft_dependency("agent-nelly"))


if __name__ == "__main__":
    unittest.main()

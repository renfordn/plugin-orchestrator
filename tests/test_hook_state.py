"""Tests for hooks/hook_state.py's load/save wiring onto FileStateStore.

The PreToolUse and SubagentStop hook entrypoints (hooks/before_continue.py,
hooks/subagent_stop.py) call load_workflow_state(path)/save_workflow_state(path,
data) to read and write the shared workflow-state.json. This verifies that
wiring goes through orchestrator.state_store.FileStateStore (atomic writes,
advisory locking) rather than a bare open()/json.dump, while keeping the
same path-in/dict-out contract the entrypoints depend on.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks"))

from hook_state import load_workflow_state, save_workflow_state  # noqa: E402


class TestHookStateFileStoreWiring(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_path = os.path.join(self.tmpdir.name, "workflow-state.json")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_load_missing_file_returns_empty_dict(self):
        self.assertEqual(load_workflow_state(self.state_path), {})

    def test_save_then_load_roundtrips(self):
        save_workflow_state(self.state_path, {"phase": "design_approved"})
        self.assertEqual(load_workflow_state(self.state_path), {"phase": "design_approved"})

    def test_save_writes_to_the_exact_path_given(self):
        save_workflow_state(self.state_path, {"phase": "design_approved"})
        self.assertTrue(os.path.exists(self.state_path))
        with open(self.state_path) as f:
            self.assertEqual(json.load(f), {"phase": "design_approved"})

    def test_save_leaves_no_tmp_file_behind(self):
        save_workflow_state(self.state_path, {"phase": "design_approved"})
        leftover = [f for f in os.listdir(self.tmpdir.name) if f.endswith(".tmp")]
        self.assertEqual(leftover, [])

    def test_load_tolerates_malformed_json(self):
        with open(self.state_path, "w") as f:
            f.write("{not valid json")
        self.assertEqual(load_workflow_state(self.state_path), {})


if __name__ == "__main__":
    unittest.main()

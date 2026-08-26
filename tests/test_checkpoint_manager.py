"""Tests for CheckpointManager: workflow state snapshots and rollback support."""

import copy
import json
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from uuid import UUID

from orchestrator.checkpoint import CheckpointManager


class TestCheckpointManagerCreate(unittest.TestCase):
    """Test create_checkpoint() for workflow state snapshots."""

    def setUp(self):
        """Set up test fixtures."""
        self.manager = CheckpointManager()
        self.workflow_state = {
            "orchestration": {
                "checkpoints": []
            },
            "task": "test_task",
            "phase": "Design"
        }

    def test_create_checkpoint_returns_uuid(self):
        """Test that create_checkpoint returns a valid UUID string."""
        checkpoint_id = self.manager.create_checkpoint(
            self.workflow_state,
            "test_checkpoint"
        )
        # Verify it's a valid UUID string
        UUID(checkpoint_id)
        self.assertIsInstance(checkpoint_id, str)

    def test_create_checkpoint_stores_in_orchestration(self):
        """Test that checkpoint is stored in workflow_state["orchestration"]["checkpoints"]."""
        checkpoint_id = self.manager.create_checkpoint(
            self.workflow_state,
            "before_agent_tdd_spawn"
        )

        self.assertIn("checkpoints", self.workflow_state["orchestration"])
        checkpoints = self.workflow_state["orchestration"]["checkpoints"]
        self.assertEqual(len(checkpoints), 1)

        checkpoint = checkpoints[0]
        self.assertEqual(checkpoint["checkpoint_id"], checkpoint_id)

    def test_checkpoint_includes_label_and_timestamp(self):
        """Test that checkpoint includes label and ISO timestamp."""
        label = "before_agent_tdd_spawn"
        checkpoint_id = self.manager.create_checkpoint(
            self.workflow_state,
            label
        )

        checkpoint = self.workflow_state["orchestration"]["checkpoints"][0]
        self.assertEqual(checkpoint["label"], label)
        self.assertIn("timestamp", checkpoint)

        # Verify timestamp is ISO format
        timestamp = checkpoint["timestamp"]
        datetime.fromisoformat(timestamp.replace('Z', '+00:00'))

    def test_checkpoint_includes_full_state_snapshot(self):
        """Test that checkpoint includes full workflow state copy."""
        checkpoint_id = self.manager.create_checkpoint(
            self.workflow_state,
            "test"
        )

        checkpoint = self.workflow_state["orchestration"]["checkpoints"][0]
        self.assertIn("state_snapshot", checkpoint)
        snapshot = checkpoint["state_snapshot"]

        # Snapshot should contain task and phase from original state
        self.assertEqual(snapshot["task"], "test_task")
        self.assertEqual(snapshot["phase"], "Design")

    def test_snapshot_is_deep_copy(self):
        """Test that snapshot is independent from original state."""
        checkpoint_id = self.manager.create_checkpoint(
            self.workflow_state,
            "test"
        )

        # Modify original state
        self.workflow_state["task"] = "modified_task"

        # Snapshot should still have original value
        snapshot = self.workflow_state["orchestration"]["checkpoints"][0]["state_snapshot"]
        self.assertEqual(snapshot["task"], "test_task")

    def test_multiple_checkpoints_stored_in_order(self):
        """Test that multiple checkpoints are stored in order."""
        id1 = self.manager.create_checkpoint(self.workflow_state, "first")
        id2 = self.manager.create_checkpoint(self.workflow_state, "second")

        checkpoints = self.workflow_state["orchestration"]["checkpoints"]
        self.assertEqual(len(checkpoints), 2)
        self.assertEqual(checkpoints[0]["checkpoint_id"], id1)
        self.assertEqual(checkpoints[1]["checkpoint_id"], id2)


class TestCheckpointManagerRestore(unittest.TestCase):
    """Test restore_checkpoint() for rollback functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.manager = CheckpointManager()
        self.workflow_state = {
            "orchestration": {
                "checkpoints": []
            },
            "task": "original_task",
            "phase": "Design"
        }

    def test_restore_checkpoint_returns_restored_state(self):
        """Test that restore_checkpoint returns restored state dict."""
        # Create a checkpoint
        checkpoint_id = self.manager.create_checkpoint(
            self.workflow_state,
            "test"
        )

        # Modify original state
        self.workflow_state["task"] = "modified_task"
        self.workflow_state["phase"] = "Green"

        # Restore from checkpoint
        restored = self.manager.restore_checkpoint(
            self.workflow_state,
            checkpoint_id
        )

        self.assertIsInstance(restored, dict)
        self.assertEqual(restored["task"], "original_task")
        self.assertEqual(restored["phase"], "Design")

    def test_restore_includes_rollback_pending_marker(self):
        """Test that restored state includes rollback_pending marker."""
        checkpoint_id = self.manager.create_checkpoint(
            self.workflow_state,
            "test"
        )

        self.workflow_state["task"] = "modified_task"

        restored = self.manager.restore_checkpoint(
            self.workflow_state,
            checkpoint_id
        )

        self.assertIn("rollback_pending", restored)
        marker = restored["rollback_pending"]

        self.assertEqual(marker["source"], "orchestrator_checkpoint_restore")
        self.assertEqual(marker["checkpoint_restored"], checkpoint_id)
        self.assertIn("timestamp", marker)
        self.assertIn("action_required", marker)

    def test_restore_without_checkpoint_id_uses_most_recent(self):
        """Test that restore without checkpoint_id uses most recent checkpoint."""
        id1 = self.manager.create_checkpoint(self.workflow_state, "first")

        # Modify and create second checkpoint
        self.workflow_state["task"] = "task_after_first"
        id2 = self.manager.create_checkpoint(self.workflow_state, "second")

        # Modify again
        self.workflow_state["task"] = "current_task"

        # Restore without specifying ID (should restore most recent)
        restored = self.manager.restore_checkpoint(self.workflow_state)

        self.assertEqual(restored["task"], "task_after_first")
        self.assertEqual(restored["rollback_pending"]["checkpoint_restored"], id2)

    def test_restore_specific_checkpoint_by_id(self):
        """Test that restore with checkpoint_id restores specific checkpoint."""
        id1 = self.manager.create_checkpoint(self.workflow_state, "first")
        self.workflow_state["task"] = "task_after_first"
        id2 = self.manager.create_checkpoint(self.workflow_state, "second")

        # Restore first checkpoint specifically
        restored = self.manager.restore_checkpoint(
            self.workflow_state,
            id1
        )

        self.assertEqual(restored["task"], "original_task")
        self.assertEqual(restored["rollback_pending"]["checkpoint_restored"], id1)


class TestCheckpointManagerHistory(unittest.TestCase):
    """Test get_checkpoint_history() for audit trail."""

    def setUp(self):
        """Set up test fixtures."""
        self.manager = CheckpointManager()
        self.workflow_state = {
            "orchestration": {
                "checkpoints": []
            },
            "task": "test_task"
        }

    def test_get_checkpoint_history_returns_list(self):
        """Test that get_checkpoint_history returns a list."""
        history = self.manager.get_checkpoint_history(self.workflow_state)
        self.assertIsInstance(history, list)
        self.assertEqual(len(history), 0)

    def test_get_checkpoint_history_returns_all_checkpoints(self):
        """Test that history contains all checkpoints."""
        id1 = self.manager.create_checkpoint(self.workflow_state, "first")
        id2 = self.manager.create_checkpoint(self.workflow_state, "second")

        history = self.manager.get_checkpoint_history(self.workflow_state)
        self.assertEqual(len(history), 2)

    def test_get_checkpoint_history_most_recent_first(self):
        """Test that history returns checkpoints most recent first."""
        id1 = self.manager.create_checkpoint(self.workflow_state, "first")
        self.workflow_state["task"] = "modified"
        id2 = self.manager.create_checkpoint(self.workflow_state, "second")

        history = self.manager.get_checkpoint_history(self.workflow_state)
        self.assertEqual(history[0]["checkpoint_id"], id2)
        self.assertEqual(history[1]["checkpoint_id"], id1)


class TestCheckpointManagerValidation(unittest.TestCase):
    """Test is_valid_checkpoint() for checkpoint integrity."""

    def setUp(self):
        """Set up test fixtures."""
        self.manager = CheckpointManager()

    def test_is_valid_checkpoint_with_all_required_fields(self):
        """Test validation with all required fields."""
        checkpoint = {
            "checkpoint_id": "test-uuid",
            "label": "test_label",
            "timestamp": "2026-08-25T10:00:00Z",
            "state_snapshot": {"task": "test"}
        }
        self.assertTrue(self.manager.is_valid_checkpoint(checkpoint))

    def test_is_valid_checkpoint_missing_id(self):
        """Test validation fails when id is missing."""
        checkpoint = {
            "label": "test_label",
            "timestamp": "2026-08-25T10:00:00Z",
            "state_snapshot": {"task": "test"}
        }
        self.assertFalse(self.manager.is_valid_checkpoint(checkpoint))

    def test_is_valid_checkpoint_missing_label(self):
        """Test validation fails when label is missing."""
        checkpoint = {
            "checkpoint_id": "test-uuid",
            "timestamp": "2026-08-25T10:00:00Z",
            "state_snapshot": {"task": "test"}
        }
        self.assertFalse(self.manager.is_valid_checkpoint(checkpoint))

    def test_is_valid_checkpoint_missing_timestamp(self):
        """Test validation fails when timestamp is missing."""
        checkpoint = {
            "checkpoint_id": "test-uuid",
            "label": "test_label",
            "state_snapshot": {"task": "test"}
        }
        self.assertFalse(self.manager.is_valid_checkpoint(checkpoint))

    def test_is_valid_checkpoint_missing_snapshot(self):
        """Test validation fails when state_snapshot is missing."""
        checkpoint = {
            "checkpoint_id": "test-uuid",
            "label": "test_label",
            "timestamp": "2026-08-25T10:00:00Z"
        }
        self.assertFalse(self.manager.is_valid_checkpoint(checkpoint))


class TestCheckpointManagerPruning(unittest.TestCase):
    """Test prune_old_checkpoints() for checkpoint lifecycle management."""

    def setUp(self):
        """Set up test fixtures."""
        self.manager = CheckpointManager()
        self.workflow_state = {
            "orchestration": {
                "checkpoints": []
            },
            "task": "test_task"
        }

    def test_prune_old_checkpoints_keeps_recent(self):
        """Test that pruning keeps only N most recent checkpoints."""
        # Create 15 checkpoints
        for i in range(15):
            self.manager.create_checkpoint(
                self.workflow_state,
                f"checkpoint_{i}"
            )

        self.assertEqual(
            len(self.workflow_state["orchestration"]["checkpoints"]),
            15
        )

        # Prune to 10
        self.manager.prune_old_checkpoints(self.workflow_state, max_checkpoints=10)

        self.assertEqual(
            len(self.workflow_state["orchestration"]["checkpoints"]),
            10
        )

    def test_prune_keeps_most_recent_checkpoints(self):
        """Test that pruning keeps the most recent checkpoints (by index)."""
        labels = []
        for i in range(15):
            label = f"checkpoint_{i}"
            labels.append(label)
            self.manager.create_checkpoint(self.workflow_state, label)

        self.manager.prune_old_checkpoints(self.workflow_state, max_checkpoints=10)

        remaining_checkpoints = self.workflow_state["orchestration"]["checkpoints"]
        remaining_labels = [cp["label"] for cp in remaining_checkpoints]

        # Should keep the last 10 checkpoints (indices 5-14)
        expected_labels = labels[5:15]
        self.assertEqual(remaining_labels, expected_labels)

    def test_prune_does_nothing_if_under_limit(self):
        """Test that pruning does nothing if checkpoints are under limit."""
        for i in range(5):
            self.manager.create_checkpoint(self.workflow_state, f"checkpoint_{i}")

        original_count = len(self.workflow_state["orchestration"]["checkpoints"])
        self.manager.prune_old_checkpoints(self.workflow_state, max_checkpoints=10)

        new_count = len(self.workflow_state["orchestration"]["checkpoints"])
        self.assertEqual(original_count, new_count)

    def test_prune_default_max_checkpoints_is_10(self):
        """Test that default max_checkpoints is 10."""
        for i in range(15):
            self.manager.create_checkpoint(self.workflow_state, f"checkpoint_{i}")

        self.manager.prune_old_checkpoints(self.workflow_state)

        self.assertEqual(
            len(self.workflow_state["orchestration"]["checkpoints"]),
            10
        )


if __name__ == '__main__':
    unittest.main()

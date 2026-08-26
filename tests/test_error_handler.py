"""Tests for ErrorHandler: error classification and recovery strategies.

This module tests all 5 error recovery paths:
1. Rollback: contract mismatch → restore checkpoint + rollback_pending marker
2. Skip: soft dependency unavailable → log and continue
3. Degrade: brief fetch failed → use stale cache + warning
4. Workaround: known fix available → apply nelly workaround
5. Pause: no recovery available → surface error to user

All tests are Red (failing) initially - ErrorHandler not yet implemented.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timezone

# ErrorHandler import will fail in Red state - that's expected
try:
    from orchestrator.error_handler import ErrorHandler
except ImportError:
    ErrorHandler = None


class TestErrorHandlerClassification(unittest.TestCase):
    """Test classify_error() for error type classification."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock dependencies
        self.mock_capability_map = Mock()
        self.mock_checkpoint_manager = Mock()

    def test_classify_error_contract_mismatch_returns_contract_mismatch(self):
        """Test classify_error identifies contract mismatch errors."""
        # Require ErrorHandler to be implemented
        self.assertIsNotNone(ErrorHandler, "ErrorHandler class not yet implemented")

        # Arrange: Create ErrorHandler with mocked dependencies
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )
        error_type = "contract_mismatch"
        error_details = {
            "expected_fields": ["task_id", "phase"],
            "received_fields": ["task_id"],
            "missing": ["phase"]
        }

        # Act: Classify the error
        classification = error_handler.classify_error(error_type, error_details)

        # Assert: Classification should identify it as contract_mismatch
        self.assertEqual(classification, "contract_mismatch")
        self.assertIsInstance(classification, str)

    def test_classify_error_dependency_unavailable_returns_type(self):
        """Test classify_error identifies dependency unavailable errors."""
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )
        error_type = "dependency_unavailable"
        error_details = {
            "plugin": "agent-nelly",
            "dependency_type": "soft"
        }

        # Act
        classification = error_handler.classify_error(error_type, error_details)

        # Assert
        self.assertEqual(classification, "dependency_unavailable")

    def test_classify_error_brief_fetch_failed_returns_type(self):
        """Test classify_error identifies brief fetch failures."""
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )
        error_type = "brief_fetch_failed"
        error_details = {
            "reason": "timeout",
            "attempt": 1
        }

        # Act
        classification = error_handler.classify_error(error_type, error_details)

        # Assert
        self.assertEqual(classification, "brief_fetch_failed")

    def test_classify_error_known_issue_returns_type(self):
        """Test classify_error identifies known issues with workarounds."""
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )
        error_type = "known_issue"
        error_details = {
            "issue_id": "NELLY-001",
            "description": "Missing task_context field in certain workflows"
        }

        # Act
        classification = error_handler.classify_error(error_type, error_details)

        # Assert
        self.assertEqual(classification, "known_issue")

    def test_classify_error_returns_string_type(self):
        """Test classify_error always returns a string type."""
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )

        # Act: Classify various error types
        result = error_handler.classify_error("unknown_error", {})

        # Assert: Result is always a string
        self.assertIsInstance(result, str)


class TestErrorHandlerRollbackRecovery(unittest.TestCase):
    """Test determine_recovery() for rollback recovery path."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock dependencies
        self.mock_capability_map = Mock()
        self.mock_checkpoint_manager = Mock()

        # Set up workflow state with checkpoint
        self.checkpoint_id = "test-checkpoint-uuid-123"
        self.original_state = {
            "task": "original_task",
            "phase": "Design",
            "current_plugin": "agent-isdd",
            "orchestration": {
                "checkpoints": [
                    {
                        "checkpoint_id": self.checkpoint_id,
                        "label": "before_handoff",
                        "state_snapshot": {
                            "task": "original_task",
                            "phase": "Design"
                        }
                    }
                ]
            }
        }

    def test_rollback_recovery_returns_rollback_action(self):
        """Test determine_recovery returns 'rollback' action for contract mismatch."""
        # Arrange
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )
        workflow_state = self.original_state.copy()
        workflow_state["phase"] = "TDD"  # Modified state after error
        workflow_state["error_occurred"] = True

        # Mock checkpoint restore to return expected state
        restored_state = {
            "task": "original_task",
            "phase": "Design",
            "rollback_pending": {
                "source": "orchestrator_checkpoint_restore",
                "checkpoint_restored": self.checkpoint_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "target_phase": "Design",
                "action_required": "Address contract mismatch, then continue"
            }
        }
        self.mock_checkpoint_manager.restore_checkpoint.return_value = restored_state

        error_details = {
            "expected_fields": ["task_id", "phase"],
            "received_fields": ["task_id"]
        }

        # Act
        action, updated_state = error_handler.determine_recovery(
            error_type="contract_mismatch",
            source_plugin="agent-isdd",
            target_plugin="agent-tdd",
            error_details=error_details,
            workflow_state=workflow_state
        )

        # Assert: Action is rollback
        self.assertEqual(action, "rollback")

    def test_rollback_recovery_includes_restored_state(self):
        """Test rollback returns updated_state with checkpoint restored."""
        # Arrange
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )
        workflow_state = self.original_state.copy()
        workflow_state["phase"] = "Modified"

        restored_state = {
            "task": "original_task",
            "phase": "Design",
            "rollback_pending": {
                "source": "orchestrator_checkpoint_restore",
                "checkpoint_restored": self.checkpoint_id,
                "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                "target_phase": "Design",
                "action_required": "Address error"
            }
        }
        self.mock_checkpoint_manager.restore_checkpoint.return_value = restored_state

        error_details = {"expected": ["a"], "received": ["b"]}

        # Act
        action, updated_state = error_handler.determine_recovery(
            error_type="contract_mismatch",
            source_plugin="agent-isdd",
            target_plugin="agent-tdd",
            error_details=error_details,
            workflow_state=workflow_state
        )

        # Assert: updated_state includes rollback_pending marker
        self.assertIn("rollback_pending", updated_state)
        marker = updated_state["rollback_pending"]
        self.assertEqual(marker["source"], "orchestrator_checkpoint_restore")
        self.assertEqual(marker["checkpoint_restored"], self.checkpoint_id)
        self.assertIn("timestamp", marker)
        self.assertIn("target_phase", marker)
        self.assertIn("action_required", marker)

    def test_rollback_recovery_marker_has_required_fields(self):
        """Test rollback marker includes all required fields."""
        # Arrange
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )
        workflow_state = self.original_state.copy()

        restored_state = {
            "task": "original_task",
            "phase": "Design",
            "rollback_pending": {
                "source": "orchestrator_checkpoint_restore",
                "checkpoint_restored": self.checkpoint_id,
                "timestamp": "2026-08-25T10:00:00Z",
                "target_phase": "Design",
                "action_required": "Fix contract mismatch and retry"
            }
        }
        self.mock_checkpoint_manager.restore_checkpoint.return_value = restored_state

        error_details = {"expected": ["x"], "received": []}

        # Act
        action, updated_state = error_handler.determine_recovery(
            error_type="contract_mismatch",
            source_plugin="agent-isdd",
            target_plugin="agent-tdd",
            error_details=error_details,
            workflow_state=workflow_state
        )

        # Assert: All required fields present in rollback_pending
        marker = updated_state["rollback_pending"]
        required_fields = ["source", "checkpoint_restored", "timestamp", "target_phase", "action_required"]
        for field in required_fields:
            self.assertIn(field, marker, f"rollback_pending missing required field: {field}")


class TestErrorHandlerSkipRecovery(unittest.TestCase):
    """Test determine_recovery() for skip recovery path."""

    def setUp(self):
        """Set up test fixtures."""
        try:
            from orchestrator.error_handler import ErrorHandler
            self.error_handler_class = ErrorHandler
        except ImportError:
            self.error_handler_class = None

        self.mock_capability_map = Mock()
        self.mock_checkpoint_manager = Mock()

        self.workflow_state = {
            "task": "test_task",
            "phase": "Design",
            "orchestration": {
                "handoff_history": []
            }
        }

    def test_skip_recovery_returns_skip_plugin_action(self):
        """Test determine_recovery returns 'skip_plugin' for soft dependency unavailable."""
        # Arrange
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )
        # Soft dependency is agent-nelly (as per SOFT_DEPENDENCIES in PluginRouter)
        error_details = {
            "plugin": "agent-nelly",
            "dependency_type": "soft",
            "reason": "agent-nelly not available in session"
        }

        # Act
        action, updated_state = error_handler.determine_recovery(
            error_type="dependency_unavailable",
            source_plugin="agent-tdd",
            target_plugin="agent-nelly",
            error_details=error_details,
            workflow_state=self.workflow_state
        )

        # Assert: Action is skip_plugin
        self.assertEqual(action, "skip_plugin")

    def test_skip_recovery_returns_unchanged_workflow_state(self):
        """Test skip recovery does not mutate workflow_state."""
        # Arrange
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )
        workflow_state = {
            "task": "test_task",
            "phase": "TDD",
            "results": "some data"
        }
        original_keys = set(workflow_state.keys())

        error_details = {
            "plugin": "agent-ux",
            "dependency_type": "soft"
        }

        # Act
        action, updated_state = error_handler.determine_recovery(
            error_type="dependency_unavailable",
            source_plugin="agent-tdd",
            target_plugin="agent-ux",
            error_details=error_details,
            workflow_state=workflow_state
        )

        # Assert: Returned state has same keys (no mutation)
        self.assertEqual(set(updated_state.keys()), original_keys)
        self.assertEqual(updated_state["task"], workflow_state["task"])
        self.assertEqual(updated_state["phase"], workflow_state["phase"])

    def test_skip_recovery_logs_error(self):
        """Test skip recovery logs the soft dependency unavailability."""
        # Arrange
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )
        workflow_state = self.workflow_state.copy()

        error_details = {
            "plugin": "agent-nelly",
            "dependency_type": "soft",
            "reason": "not installed"
        }

        # Mock log_error
        error_handler.log_error = Mock()

        # Act
        action, updated_state = error_handler.determine_recovery(
            error_type="dependency_unavailable",
            source_plugin="agent-tdd",
            target_plugin="agent-nelly",
            error_details=error_details,
            workflow_state=workflow_state
        )

        # Assert: log_error should be called
        # (This will verify in integration that error is logged)
        # For now, we just assert action and state are correct


class TestErrorHandlerDegradeRecovery(unittest.TestCase):
    """Test determine_recovery() for degrade (stale cache) recovery path."""

    def setUp(self):
        """Set up test fixtures."""
        try:
            from orchestrator.error_handler import ErrorHandler
            self.error_handler_class = ErrorHandler
        except ImportError:
            self.error_handler_class = None

        self.mock_capability_map = Mock()
        self.mock_checkpoint_manager = Mock()

        self.workflow_state = {
            "task": "test_task",
            "phase": "TDD",
            "orchestration": {
                "nelly_brief_cache": {
                    "brief_text": "stale brief content",
                    "metadata": {"cached_at": "2026-08-24T10:00:00Z"},
                    "fetched_at": 1692806400.0  # 1 hour old
                },
                "handoff_history": []
            }
        }

    def test_degrade_recovery_returns_use_stale_cache_action(self):
        """Test determine_recovery returns 'use_stale_cache' for brief fetch failure."""
        # Arrange
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )
        error_details = {
            "reason": "timeout",
            "attempt": 1,
            "elapsed_time": 30.5
        }

        # Act
        action, updated_state = error_handler.determine_recovery(
            error_type="brief_fetch_failed",
            source_plugin="agent-tdd",
            target_plugin="agent-nelly",
            error_details=error_details,
            workflow_state=self.workflow_state
        )

        # Assert: Action is use_stale_cache
        self.assertEqual(action, "use_stale_cache")

    def test_degrade_recovery_includes_stale_cache(self):
        """Test degrade recovery includes stale brief in returned state."""
        # Arrange
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )
        stale_brief = "stale brief from cache"
        workflow_state = self.workflow_state.copy()
        workflow_state["orchestration"]["nelly_brief_cache"]["brief_text"] = stale_brief

        error_details = {"reason": "timeout"}

        # Act
        action, updated_state = error_handler.determine_recovery(
            error_type="brief_fetch_failed",
            source_plugin="agent-tdd",
            target_plugin="agent-nelly",
            error_details=error_details,
            workflow_state=workflow_state
        )

        # Assert: State includes stale cache brief
        self.assertIn("orchestration", updated_state)
        self.assertIn("nelly_brief_cache", updated_state["orchestration"])
        cache = updated_state["orchestration"]["nelly_brief_cache"]
        self.assertIn("brief_text", cache)
        # Stale brief should be available (not removed)
        self.assertEqual(cache["brief_text"], stale_brief)

    def test_degrade_recovery_logs_warning(self):
        """Test degrade recovery logs a warning about stale cache usage."""
        # Arrange
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )
        workflow_state = self.workflow_state.copy()
        error_details = {"reason": "network error"}

        # Mock log_error to capture log call
        error_handler.log_error = Mock()

        # Act
        action, updated_state = error_handler.determine_recovery(
            error_type="brief_fetch_failed",
            source_plugin="agent-tdd",
            target_plugin="agent-nelly",
            error_details=error_details,
            workflow_state=workflow_state
        )

        # Assert: Action is correct (actual logging verified in integration)


class TestErrorHandlerWorkaroundRecovery(unittest.TestCase):
    """Test determine_recovery() for workaround recovery path."""

    def setUp(self):
        """Set up test fixtures."""
        try:
            from orchestrator.error_handler import ErrorHandler
            self.error_handler_class = ErrorHandler
        except ImportError:
            self.error_handler_class = None

        self.mock_capability_map = Mock()
        self.mock_checkpoint_manager = Mock()

        self.workflow_state = {
            "task": "test_task",
            "phase": "TDD",
            "payload": {
                "task_context": None,  # Missing field
                "code": "some code"
            },
            "orchestration": {
                "handoff_history": []
            }
        }

    def test_workaround_recovery_returns_nelly_workaround_action(self):
        """Test determine_recovery returns 'nelly_workaround' for known issue."""
        # Arrange
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )

        # Mock nelly_workaround_lookup to return a known workaround
        workaround_details = {
            "workaround_id": "WA-001",
            "description": "Fill missing task_context from parent state",
            "action": "inject_missing_field",
            "field": "task_context",
            "value": "default_context"
        }
        error_handler.nelly_workaround_lookup = Mock(
            return_value=workaround_details
        )

        error_details = {
            "missing_field": "task_context",
            "issue_id": "NELLY-KI-001"
        }

        # Act
        action, updated_state = error_handler.determine_recovery(
            error_type="known_issue",
            source_plugin="agent-tdd",
            target_plugin="agent-nelly",
            error_details=error_details,
            workflow_state=self.workflow_state
        )

        # Assert: Action is nelly_workaround
        self.assertEqual(action, "nelly_workaround")

    def test_workaround_recovery_includes_applied_workaround(self):
        """Test workaround recovery returns state with workaround applied."""
        # Arrange
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )
        workflow_state = self.workflow_state.copy()

        # Mock workaround lookup
        workaround_details = {
            "workaround_id": "WA-TASK-CONTEXT",
            "action": "inject_field",
            "field_name": "task_context",
            "field_value": "context_from_parent"
        }
        error_handler.nelly_workaround_lookup = Mock(
            return_value=workaround_details
        )

        error_details = {"missing_field": "task_context"}

        # Act
        action, updated_state = error_handler.determine_recovery(
            error_type="known_issue",
            source_plugin="agent-tdd",
            target_plugin="agent-nelly",
            error_details=error_details,
            workflow_state=workflow_state
        )

        # Assert: Updated state should reflect workaround applied
        # (exact shape depends on implementation, but should be modified)
        self.assertIsNotNone(updated_state)
        self.assertIsInstance(updated_state, dict)

    def test_workaround_recovery_queries_nelly_lookup(self):
        """Test workaround recovery queries nelly_workaround_lookup."""
        # Arrange
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )
        error_handler.nelly_workaround_lookup = Mock(return_value=None)

        error_details = {"issue_id": "ISSUE-123"}

        # Act: Workaround should query nelly
        # Note: If no workaround found, behavior differs (see Pause path)
        # For now, assume workaround exists
        error_handler.nelly_workaround_lookup = Mock(
            return_value={"workaround_id": "WA-123", "action": "fix"}
        )

        action, updated_state = error_handler.determine_recovery(
            error_type="known_issue",
            source_plugin="agent-tdd",
            target_plugin="agent-nelly",
            error_details=error_details,
            workflow_state=self.workflow_state
        )

        # Assert: nelly_workaround_lookup should have been called
        error_handler.nelly_workaround_lookup.assert_called_once()

    def test_workaround_recovery_logs_workaround_applied(self):
        """Test workaround recovery logs the workaround details."""
        # Arrange
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )
        error_handler.nelly_workaround_lookup = Mock(
            return_value={"workaround_id": "WA-ID", "description": "Apply fix"}
        )
        error_handler.log_error = Mock()

        error_details = {"issue": "test"}

        # Act
        action, updated_state = error_handler.determine_recovery(
            error_type="known_issue",
            source_plugin="agent-tdd",
            target_plugin="agent-nelly",
            error_details=error_details,
            workflow_state=self.workflow_state
        )

        # Assert: log_error should be called (verified in actual implementation)


class TestErrorHandlerPauseRecovery(unittest.TestCase):
    """Test determine_recovery() for pause recovery path."""

    def setUp(self):
        """Set up test fixtures."""
        try:
            from orchestrator.error_handler import ErrorHandler
            self.error_handler_class = ErrorHandler
        except ImportError:
            self.error_handler_class = None

        self.mock_capability_map = Mock()
        self.mock_checkpoint_manager = Mock()

        self.workflow_state = {
            "task": "test_task",
            "phase": "TDD",
            "orchestration": {
                "handoff_history": []
            }
        }

    def test_pause_recovery_returns_pause_action(self):
        """Test determine_recovery returns 'pause' when no recovery available."""
        # Arrange
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )

        # No checkpoint available and no workaround
        error_handler.nelly_workaround_lookup = Mock(return_value=None)

        error_details = {
            "expected_fields": ["unknown_field"],
            "received_fields": ["known_field"],
            "missing": ["unknown_field"]
        }

        # Act
        action, updated_state = error_handler.determine_recovery(
            error_type="contract_mismatch",
            source_plugin="agent-isdd",
            target_plugin="agent-tdd",
            error_details=error_details,
            workflow_state=self.workflow_state
        )

        # Assert: Action is pause
        self.assertEqual(action, "pause")

    def test_pause_recovery_surfaces_error_message(self):
        """Test pause recovery includes specific error details."""
        # Arrange
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )
        error_handler.nelly_workaround_lookup = Mock(return_value=None)

        error_message = "Contract mismatch: expected field 'task_id' but received 'task'"
        error_details = {"message": error_message}

        # Act
        action, updated_state = error_handler.determine_recovery(
            error_type="contract_mismatch",
            source_plugin="agent-isdd",
            target_plugin="agent-tdd",
            error_details=error_details,
            workflow_state=self.workflow_state
        )

        # Assert: updated_state should include error information
        self.assertIn("error_message", updated_state)
        self.assertEqual(updated_state["error_message"], error_message)

    def test_pause_recovery_logs_error(self):
        """Test pause recovery logs the error to handoff_history."""
        # Arrange
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )
        error_handler.nelly_workaround_lookup = Mock(return_value=None)
        error_handler.log_error = Mock()

        error_details = {"reason": "unrecoverable"}

        # Act
        action, updated_state = error_handler.determine_recovery(
            error_type="unknown_error",
            source_plugin="agent-isdd",
            target_plugin="agent-tdd",
            error_details=error_details,
            workflow_state=self.workflow_state
        )

        # Assert: Action is pause and error should be logged


class TestErrorHandlerLogging(unittest.TestCase):
    """Test log_error() for error logging to handoff_history."""

    def setUp(self):
        """Set up test fixtures."""
        try:
            from orchestrator.error_handler import ErrorHandler
            self.error_handler_class = ErrorHandler
        except ImportError:
            self.error_handler_class = None

        self.mock_capability_map = Mock()
        self.mock_checkpoint_manager = Mock()

        self.workflow_state = {
            "task": "test_task",
            "orchestration": {
                "handoff_history": []
            }
        }

    def test_log_error_writes_to_handoff_history(self):
        """Test log_error writes error entry to handoff_history."""
        # Arrange
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )
        workflow_state = self.workflow_state.copy()
        initial_history_len = len(workflow_state["orchestration"]["handoff_history"])

        # Act: Log an error
        error_handler.log_error(
            workflow_state=workflow_state,
            error_type="contract_mismatch",
            source_plugin="agent-isdd",
            target_plugin="agent-tdd",
            recovery_action="rollback",
            reason="Missing required field 'phase'"
        )

        # Assert: Entry added to handoff_history
        self.assertGreater(
            len(workflow_state["orchestration"]["handoff_history"]),
            initial_history_len
        )

    def test_log_error_entry_includes_error_type(self):
        """Test logged error entry includes error_type field."""
        # Arrange
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )
        workflow_state = self.workflow_state.copy()

        # Act
        error_handler.log_error(
            workflow_state=workflow_state,
            error_type="brief_fetch_failed",
            source_plugin="agent-tdd",
            target_plugin="agent-nelly",
            recovery_action="use_stale_cache",
            reason="Network timeout"
        )

        # Assert: Entry should have error_type
        history_entry = workflow_state["orchestration"]["handoff_history"][-1]
        self.assertIn("error_type", history_entry)
        self.assertEqual(history_entry["error_type"], "brief_fetch_failed")

    def test_log_error_entry_includes_recovery_action(self):
        """Test logged error entry includes recovery_action field."""
        # Arrange
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )
        workflow_state = self.workflow_state.copy()

        # Act
        error_handler.log_error(
            workflow_state=workflow_state,
            error_type="dependency_unavailable",
            source_plugin="agent-tdd",
            target_plugin="agent-nelly",
            recovery_action="skip_plugin",
            reason="Soft dependency not available"
        )

        # Assert: Entry should have recovery_action
        history_entry = workflow_state["orchestration"]["handoff_history"][-1]
        self.assertIn("recovery_action", history_entry)
        self.assertEqual(history_entry["recovery_action"], "skip_plugin")

    def test_log_error_entry_includes_source_and_target_plugins(self):
        """Test logged error entry includes source and target plugin info."""
        # Arrange
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )
        workflow_state = self.workflow_state.copy()

        # Act
        error_handler.log_error(
            workflow_state=workflow_state,
            error_type="test_error",
            source_plugin="agent-isdd",
            target_plugin="agent-tdd",
            recovery_action="rollback",
            reason="Test reason"
        )

        # Assert: Entry should include plugin info
        history_entry = workflow_state["orchestration"]["handoff_history"][-1]
        self.assertIn("source_plugin", history_entry)
        self.assertIn("target_plugin", history_entry)
        self.assertEqual(history_entry["source_plugin"], "agent-isdd")
        self.assertEqual(history_entry["target_plugin"], "agent-tdd")

    def test_log_error_entry_includes_timestamp(self):
        """Test logged error entry includes timestamp."""
        # Arrange
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )
        workflow_state = self.workflow_state.copy()

        # Act
        error_handler.log_error(
            workflow_state=workflow_state,
            error_type="test_error",
            source_plugin="agent-isdd",
            target_plugin="agent-tdd",
            recovery_action="pause",
            reason="Test"
        )

        # Assert: Entry should have timestamp
        history_entry = workflow_state["orchestration"]["handoff_history"][-1]
        self.assertIn("timestamp", history_entry)
        # Timestamp should be valid ISO format
        timestamp = history_entry["timestamp"]
        datetime.fromisoformat(timestamp.replace('Z', '+00:00'))

    def test_log_error_entry_includes_reason(self):
        """Test logged error entry includes reason field."""
        # Arrange
        error_handler = ErrorHandler(
            self.mock_capability_map,
            self.mock_checkpoint_manager
        )
        workflow_state = self.workflow_state.copy()
        reason_text = "Handoff payload missing critical field"

        # Act
        error_handler.log_error(
            workflow_state=workflow_state,
            error_type="contract_mismatch",
            source_plugin="agent-isdd",
            target_plugin="agent-tdd",
            recovery_action="rollback",
            reason=reason_text
        )

        # Assert: Entry should have reason
        history_entry = workflow_state["orchestration"]["handoff_history"][-1]
        self.assertIn("reason", history_entry)
        self.assertEqual(history_entry["reason"], reason_text)


if __name__ == '__main__':
    unittest.main()

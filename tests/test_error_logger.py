"""Tests for ErrorLogger dual-tier logging (session + persistent)."""

import json
import unittest
import tempfile
from pathlib import Path
from orchestrator.error import OrchestrationError
from orchestrator.error_logger import ErrorLogger


class TestErrorLoggerRed(unittest.TestCase):
    """Red tests for ErrorLogger session and persistent logging."""

    def setUp(self):
        """Set up test fixtures."""
        self.logger = ErrorLogger()
        self.temp_dir = tempfile.mkdtemp()
        self.workflow_state_path = Path(self.temp_dir) / "workflow-state.json"
        self.project_slug = "test-project"

    def test_log_error_to_memory(self):
        """Test log_error appends error to in-memory session errors."""
        error = OrchestrationError(
            timestamp="2026-09-14T12:30:45.123Z",
            error_type="handoff_validation",
            source_plugin="agent-isdd",
            root_cause="missing_field",
            severity="high",
            suggested_fix="add field"
        )
        self.logger.log_error(error)

        session_errors = self.logger.get_session_errors()
        self.assertEqual(len(session_errors), 1)
        self.assertEqual(session_errors[0].error_type, "handoff_validation")

    def test_log_error_multiple(self):
        """Test logging multiple errors maintains order."""
        errors = []
        for i in range(3):
            error = OrchestrationError(
                timestamp=f"2026-09-14T12:30:{45+i}.123Z",
                error_type="handoff_validation",
                source_plugin="agent-isdd",
                root_cause="test",
                severity="high",
                suggested_fix="fix"
            )
            errors.append(error)
            self.logger.log_error(error)

        session_errors = self.logger.get_session_errors()
        self.assertEqual(len(session_errors), 3)

    def test_persist_error_writes_to_file(self):
        """Test persist_error writes to persistent registry file."""
        error = OrchestrationError(
            timestamp="2026-09-14T12:30:45.123Z",
            error_type="plugin_unavailable",
            source_plugin="agent-isdd",
            root_cause="not_found",
            severity="high",
            suggested_fix="install"
        )

        registry_path = Path(self.temp_dir) / self.project_slug / "error-registry.json"
        self.logger.persist_error(error, self.temp_dir, self.project_slug)

        self.assertTrue(registry_path.exists())

        with open(registry_path) as f:
            data = json.load(f)

        self.assertIn("errors", data)
        self.assertEqual(len(data["errors"]), 1)
        self.assertEqual(data["errors"][0]["error_type"], "plugin_unavailable")

    def test_persist_multiple_errors_appends(self):
        """Test persisting multiple errors appends to registry."""
        errors = []
        for i in range(2):
            error = OrchestrationError(
                timestamp=f"2026-09-14T12:30:{45+i}.123Z",
                error_type="routing_failed",
                source_plugin="agent-isdd",
                root_cause="test",
                severity="medium",
                suggested_fix="fix"
            )
            errors.append(error)
            self.logger.persist_error(error, self.temp_dir, self.project_slug)

        registry_path = Path(self.temp_dir) / self.project_slug / "error-registry.json"
        with open(registry_path) as f:
            data = json.load(f)

        self.assertEqual(len(data["errors"]), 2)

    def test_graceful_degradation_on_missing_registry_dir(self):
        """Test that logging continues even if registry dir doesn't exist."""
        error = OrchestrationError(
            timestamp="2026-09-14T12:30:45.123Z",
            error_type="handoff_validation",
            source_plugin="agent-isdd",
            root_cause="test",
            severity="high",
            suggested_fix="fix"
        )

        # Non-existent directory
        self.logger.persist_error(error, "/nonexistent/path", "project")

        # Error should still be in memory
        session_errors = self.logger.get_session_errors()
        self.assertEqual(len(session_errors), 1)

    def test_session_errors_cleared(self):
        """Test clear_session_errors removes in-memory errors."""
        error = OrchestrationError(
            timestamp="2026-09-14T12:30:45.123Z",
            error_type="handoff_validation",
            source_plugin="agent-isdd",
            root_cause="test",
            severity="high",
            suggested_fix="fix"
        )
        self.logger.log_error(error)
        self.assertEqual(len(self.logger.get_session_errors()), 1)

        self.logger.clear_session_errors()
        self.assertEqual(len(self.logger.get_session_errors()), 0)

    def test_error_dict_round_trip_in_registry(self):
        """Test errors in registry can be reconstructed from dicts."""
        error = OrchestrationError(
            timestamp="2026-09-14T12:30:45.123Z",
            error_type="nelly_fetch_failed",
            source_plugin="agent-isdd",
            root_cause="intent_mismatch",
            severity="low",
            suggested_fix="refetch",
            context={"intent_hash": "abc123"}
        )

        registry_path = Path(self.temp_dir) / self.project_slug / "error-registry.json"
        self.logger.persist_error(error, self.temp_dir, self.project_slug)

        with open(registry_path) as f:
            data = json.load(f)

        reconstructed = OrchestrationError.from_dict(data["errors"][0])
        self.assertEqual(reconstructed.error_type, "nelly_fetch_failed")
        self.assertEqual(reconstructed.context, {"intent_hash": "abc123"})

    def test_non_blocking_on_write_failure(self):
        """Test logging doesn't raise even if file write fails."""
        error = OrchestrationError(
            timestamp="2026-09-14T12:30:45.123Z",
            error_type="handoff_validation",
            source_plugin="agent-isdd",
            root_cause="test",
            severity="high",
            suggested_fix="fix"
        )

        # Try to persist to read-only location
        # Should not raise, just log to memory
        self.logger.persist_error(error, "/root/forbidden", "project")

        session_errors = self.logger.get_session_errors()
        self.assertEqual(len(session_errors), 1)

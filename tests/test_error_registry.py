"""Tests for ErrorRegistry pattern detection and querying."""

import json
import unittest
import tempfile
from pathlib import Path
from orchestrator.error import OrchestrationError
from orchestrator.error_registry import ErrorRegistry, ErrorPattern


class TestErrorRegistryRed(unittest.TestCase):
    """Red tests for ErrorRegistry querying and pattern detection."""

    def setUp(self):
        """Set up test fixtures with a populated registry file."""
        self.temp_dir = tempfile.mkdtemp()
        self.registry_path = Path(self.temp_dir) / "error-registry.json"
        self.registry = ErrorRegistry(self.registry_path)

    def _write_registry(self, errors):
        """Helper: write a list of error dicts to the registry file."""
        with open(self.registry_path, "w") as f:
            json.dump({"errors": errors, "patterns": []}, f)

    def test_query_errors_empty_registry_returns_empty(self):
        """Test querying a missing registry file returns empty list."""
        results = self.registry.query_errors()
        self.assertEqual(results, [])

    def test_query_errors_no_filters_returns_all(self):
        """Test querying with no filters returns all errors within window."""
        from datetime import datetime
        now = datetime.utcnow().isoformat() + "Z"
        self._write_registry([
            {
                "timestamp": now, "error_type": "handoff_validation",
                "source_plugin": "agent-isdd", "target_plugin": "agent-tdd",
                "root_cause": "missing_field", "severity": "high",
                "suggested_fix": "fix", "context": {}
            }
        ])
        results = self.registry.query_errors()
        self.assertEqual(len(results), 1)

    def test_query_errors_filters_by_plugin(self):
        """Test filtering by plugin name matches source or target."""
        from datetime import datetime
        now = datetime.utcnow().isoformat() + "Z"
        self._write_registry([
            {
                "timestamp": now, "error_type": "handoff_validation",
                "source_plugin": "agent-isdd", "target_plugin": "agent-tdd",
                "root_cause": "test", "severity": "high",
                "suggested_fix": "fix", "context": {}
            },
            {
                "timestamp": now, "error_type": "routing_failed",
                "source_plugin": "code-reviewer", "target_plugin": None,
                "root_cause": "test", "severity": "low",
                "suggested_fix": "fix", "context": {}
            }
        ])
        results = self.registry.query_errors(plugin="agent-tdd")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].target_plugin, "agent-tdd")

    def test_query_errors_filters_by_error_type(self):
        """Test filtering by error_type."""
        from datetime import datetime
        now = datetime.utcnow().isoformat() + "Z"
        self._write_registry([
            {
                "timestamp": now, "error_type": "handoff_validation",
                "source_plugin": "agent-isdd", "target_plugin": None,
                "root_cause": "test", "severity": "high",
                "suggested_fix": "fix", "context": {}
            },
            {
                "timestamp": now, "error_type": "plugin_unavailable",
                "source_plugin": "agent-isdd", "target_plugin": None,
                "root_cause": "test", "severity": "medium",
                "suggested_fix": "fix", "context": {}
            }
        ])
        results = self.registry.query_errors(error_type="plugin_unavailable")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].error_type, "plugin_unavailable")

    def test_query_errors_excludes_old_errors(self):
        """Test that errors older than days_back are excluded."""
        old_timestamp = "2020-01-01T00:00:00.000Z"
        self._write_registry([
            {
                "timestamp": old_timestamp, "error_type": "handoff_validation",
                "source_plugin": "agent-isdd", "target_plugin": None,
                "root_cause": "test", "severity": "high",
                "suggested_fix": "fix", "context": {}
            }
        ])
        results = self.registry.query_errors(days_back=30)
        self.assertEqual(len(results), 0)

    def test_detect_patterns_identifies_recurring_errors(self):
        """Test detect_patterns flags 2+ same-type errors as a pattern."""
        from datetime import datetime
        now = datetime.utcnow().isoformat() + "Z"
        self._write_registry([
            {
                "timestamp": now, "error_type": "handoff_validation",
                "source_plugin": "agent-isdd", "target_plugin": "agent-tdd",
                "root_cause": "missing_field", "severity": "high",
                "suggested_fix": "fix", "context": {}
            },
            {
                "timestamp": now, "error_type": "handoff_validation",
                "source_plugin": "agent-isdd", "target_plugin": "agent-tdd",
                "root_cause": "missing_field", "severity": "high",
                "suggested_fix": "fix", "context": {}
            }
        ])
        patterns = self.registry.detect_patterns()
        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0].error_type, "handoff_validation")
        self.assertEqual(patterns[0].occurrence_count, 2)

    def test_detect_patterns_ignores_single_occurrence(self):
        """Test that a single error doesn't count as a pattern."""
        from datetime import datetime
        now = datetime.utcnow().isoformat() + "Z"
        self._write_registry([
            {
                "timestamp": now, "error_type": "handoff_validation",
                "source_plugin": "agent-isdd", "target_plugin": None,
                "root_cause": "test", "severity": "high",
                "suggested_fix": "fix", "context": {}
            }
        ])
        patterns = self.registry.detect_patterns()
        self.assertEqual(len(patterns), 0)

    def test_get_high_severity_patterns_filters_correctly(self):
        """Test get_high_severity_patterns only returns high-severity patterns."""
        from datetime import datetime
        now = datetime.utcnow().isoformat() + "Z"
        self._write_registry([
            {
                "timestamp": now, "error_type": "handoff_validation",
                "source_plugin": "agent-isdd", "target_plugin": None,
                "root_cause": "test", "severity": "low",
                "suggested_fix": "fix", "context": {}
            },
            {
                "timestamp": now, "error_type": "handoff_validation",
                "source_plugin": "agent-isdd", "target_plugin": None,
                "root_cause": "test", "severity": "low",
                "suggested_fix": "fix", "context": {}
            }
        ])
        high_patterns = self.registry.get_high_severity_patterns()
        self.assertEqual(len(high_patterns), 0)  # low severity excluded

    def test_graceful_degradation_on_corrupted_registry(self):
        """Test that corrupted JSON doesn't raise, returns empty."""
        with open(self.registry_path, "w") as f:
            f.write("{ invalid json ]")

        results = self.registry.query_errors()
        self.assertEqual(results, [])

        patterns = self.registry.detect_patterns()
        self.assertEqual(patterns, [])

    def test_performance_1000_errors_under_100ms(self):
        """Test query performance with 1000-error registry stays under 100ms."""
        import time
        from datetime import datetime
        now = datetime.utcnow().isoformat() + "Z"
        errors = [
            {
                "timestamp": now, "error_type": "handoff_validation",
                "source_plugin": "agent-isdd", "target_plugin": None,
                "root_cause": "test", "severity": "medium",
                "suggested_fix": "fix", "context": {}
            }
            for _ in range(1000)
        ]
        self._write_registry(errors)

        start = time.perf_counter()
        results = self.registry.query_errors()
        elapsed_ms = (time.perf_counter() - start) * 1000

        self.assertEqual(len(results), 1000)
        self.assertLess(elapsed_ms, 100, f"Query took {elapsed_ms}ms, expected <100ms")

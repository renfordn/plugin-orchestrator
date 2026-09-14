"""Tests for ErrorPatternManager nelly integration."""

import json
import unittest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from orchestrator.nelly_integration import ErrorPatternManager


class TestErrorPatternManagerRed(unittest.TestCase):
    """Red tests for ErrorPatternManager brief augmentation and error querying."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.registry_path = Path(self.temp_dir) / "error-registry.json"
        self.manager = ErrorPatternManager(self.registry_path)

    def _write_registry(self, errors):
        with open(self.registry_path, "w") as f:
            json.dump({"errors": errors, "patterns": []}, f)

    def test_augment_brief_adds_error_patterns_section(self):
        """Test augment_nelly_brief adds error_patterns when high-severity recurring errors exist."""
        now = datetime.utcnow().isoformat() + "Z"
        self._write_registry([
            {
                "timestamp": now, "error_type": "handoff_validation",
                "source_plugin": "agent-isdd", "target_plugin": "agent-tdd",
                "root_cause": "missing_field", "severity": "high",
                "suggested_fix": "add field", "context": {}
            },
            {
                "timestamp": now, "error_type": "handoff_validation",
                "source_plugin": "agent-isdd", "target_plugin": "agent-tdd",
                "root_cause": "missing_field", "severity": "high",
                "suggested_fix": "add field", "context": {}
            }
        ])

        brief = {"intent": "test project"}
        augmented = self.manager.augment_nelly_brief(brief)

        self.assertIn("error_patterns", augmented)
        self.assertEqual(len(augmented["error_patterns"]), 1)
        self.assertEqual(augmented["error_patterns"][0]["error_type"], "handoff_validation")

    def test_augment_brief_no_patterns_when_no_recurring_errors(self):
        """Test brief is unmodified when no high-severity recurring patterns exist."""
        brief = {"intent": "test project"}
        augmented = self.manager.augment_nelly_brief(brief)

        self.assertNotIn("error_patterns", augmented)
        self.assertEqual(augmented["intent"], "test project")

    def test_augment_brief_graceful_degradation_missing_registry(self):
        """Test augment_nelly_brief doesn't raise when registry file is missing."""
        manager = ErrorPatternManager(Path("/nonexistent/error-registry.json"))
        brief = {"intent": "test"}

        # Should not raise
        augmented = manager.augment_nelly_brief(brief)
        self.assertEqual(augmented["intent"], "test")

    def test_query_error_history_returns_ranked_results(self):
        """Test query_error_history ranks by severity (high first)."""
        now = datetime.utcnow().isoformat() + "Z"
        self._write_registry([
            {
                "timestamp": now, "error_type": "routing_failed",
                "source_plugin": "agent-isdd", "target_plugin": None,
                "root_cause": "test", "severity": "low",
                "suggested_fix": "fix", "context": {}
            },
            {
                "timestamp": now, "error_type": "handoff_validation",
                "source_plugin": "agent-isdd", "target_plugin": None,
                "root_cause": "test", "severity": "high",
                "suggested_fix": "fix", "context": {}
            }
        ])

        result = self.manager.query_error_history()

        self.assertEqual(result["error_count"], 2)
        # High severity should be first
        self.assertEqual(result["errors"][0]["severity"], "high")

    def test_query_error_history_recency_ranking(self):
        """Test that within same severity, more recent errors rank first."""
        older = (datetime.utcnow() - timedelta(days=2)).isoformat() + "Z"
        newer = datetime.utcnow().isoformat() + "Z"
        self._write_registry([
            {
                "timestamp": older, "error_type": "handoff_validation",
                "source_plugin": "agent-isdd", "target_plugin": None,
                "root_cause": "test", "severity": "high",
                "suggested_fix": "fix", "context": {}
            },
            {
                "timestamp": newer, "error_type": "routing_failed",
                "source_plugin": "agent-isdd", "target_plugin": None,
                "root_cause": "test", "severity": "high",
                "suggested_fix": "fix", "context": {}
            }
        ])

        result = self.manager.query_error_history()

        # Both high severity; newer timestamp should rank first
        self.assertEqual(result["errors"][0]["timestamp"], newer)

    def test_query_error_history_actionability_ranking(self):
        """Test that errors with a suggested_fix rank before those without, within same severity/time."""
        now = datetime.utcnow().isoformat() + "Z"
        self._write_registry([
            {
                "timestamp": now, "error_type": "handoff_validation",
                "source_plugin": "agent-isdd", "target_plugin": None,
                "root_cause": "test", "severity": "high",
                "suggested_fix": "", "context": {}
            },
            {
                "timestamp": now, "error_type": "routing_failed",
                "source_plugin": "agent-isdd", "target_plugin": None,
                "root_cause": "test", "severity": "high",
                "suggested_fix": "has a fix", "context": {}
            }
        ])

        result = self.manager.query_error_history()
        # Error with a suggested_fix should rank first among equal severity/timestamp
        self.assertTrue(result["errors"][0]["suggested_fix"])

    def test_query_error_history_filters_by_plugin(self):
        """Test query_error_history respects plugin filter."""
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

        result = self.manager.query_error_history(plugin="code-reviewer")
        self.assertEqual(result["error_count"], 1)

    def test_query_error_history_graceful_degradation(self):
        """Test query_error_history returns empty result on missing registry, doesn't raise."""
        manager = ErrorPatternManager(Path("/nonexistent/error-registry.json"))
        result = manager.query_error_history()

        self.assertEqual(result["error_count"], 0)
        self.assertEqual(result["errors"], [])

    def test_get_high_severity_patterns_direct_returns_pattern_dicts(self):
        """Test a direct patterns accessor (no throwaway-brief indirection) returns pattern dicts."""
        now = datetime.utcnow().isoformat() + "Z"
        self._write_registry([
            {
                "timestamp": now, "error_type": "handoff_validation",
                "source_plugin": "agent-isdd", "target_plugin": "agent-tdd",
                "root_cause": "missing_field", "severity": "high",
                "suggested_fix": "add field", "context": {}
            },
            {
                "timestamp": now, "error_type": "handoff_validation",
                "source_plugin": "agent-isdd", "target_plugin": "agent-tdd",
                "root_cause": "missing_field", "severity": "high",
                "suggested_fix": "add field", "context": {}
            }
        ])

        patterns = self.manager.get_high_severity_pattern_dicts()

        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0]["error_type"], "handoff_validation")
        self.assertIn("severity", patterns[0])
        self.assertIn("suggested_fix", patterns[0])
        self.assertIn("affected_plugins", patterns[0])

    def test_get_high_severity_patterns_direct_empty_when_none(self):
        """Test direct accessor returns empty list, not raise, when no patterns exist."""
        patterns = self.manager.get_high_severity_pattern_dicts()
        self.assertEqual(patterns, [])

    def test_get_high_severity_patterns_direct_graceful_degradation(self):
        """Test direct accessor doesn't raise on missing registry."""
        manager = ErrorPatternManager(Path("/nonexistent/error-registry.json"))
        patterns = manager.get_high_severity_pattern_dicts()
        self.assertEqual(patterns, [])

    def test_query_error_history_empty_for_plugin_with_no_errors(self):
        """Test querying a plugin with no errors returns empty, not error."""
        now = datetime.utcnow().isoformat() + "Z"
        self._write_registry([
            {
                "timestamp": now, "error_type": "handoff_validation",
                "source_plugin": "agent-isdd", "target_plugin": None,
                "root_cause": "test", "severity": "high",
                "suggested_fix": "fix", "context": {}
            }
        ])

        result = self.manager.query_error_history(plugin="nonexistent-plugin")
        self.assertEqual(result["error_count"], 0)

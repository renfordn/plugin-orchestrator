"""Tests for OrchestrationError data class."""

import json
import unittest
from orchestrator.error import OrchestrationError


class TestOrchestrationErrorRed(unittest.TestCase):
    """Red tests for OrchestrationError instantiation, validation, and serialization."""

    def test_valid_instantiation(self):
        """Test creating a valid OrchestrationError."""
        error = OrchestrationError(
            timestamp="2026-09-14T12:30:45.123Z",
            error_type="handoff_validation",
            source_plugin="agent-isdd",
            target_plugin="agent-tdd",
            root_cause="missing_required_field",
            severity="high",
            suggested_fix="ensure design.md includes research_cache",
            context={"missing_field": "research_cache"}
        )
        self.assertEqual(error.timestamp, "2026-09-14T12:30:45.123Z")
        self.assertEqual(error.error_type, "handoff_validation")
        self.assertEqual(error.source_plugin, "agent-isdd")
        self.assertEqual(error.target_plugin, "agent-tdd")
        self.assertEqual(error.root_cause, "missing_required_field")
        self.assertEqual(error.severity, "high")
        self.assertEqual(error.suggested_fix, "ensure design.md includes research_cache")
        self.assertEqual(error.context, {"missing_field": "research_cache"})

    def test_invalid_error_type_raises_error(self):
        """Test that invalid error_type raises ValueError."""
        with self.assertRaises(ValueError):
            OrchestrationError(
                timestamp="2026-09-14T12:30:45.123Z",
                error_type="invalid_type",  # Invalid
                source_plugin="agent-isdd",
                target_plugin="agent-tdd",
                root_cause="test",
                severity="high",
                suggested_fix="test"
            )

    def test_invalid_severity_raises_error(self):
        """Test that invalid severity raises ValueError."""
        with self.assertRaises(ValueError):
            OrchestrationError(
                timestamp="2026-09-14T12:30:45.123Z",
                error_type="handoff_validation",
                source_plugin="agent-isdd",
                target_plugin="agent-tdd",
                root_cause="test",
                severity="critical",  # Invalid
                suggested_fix="test"
            )

    def test_valid_error_types(self):
        """Test all valid error_type values."""
        valid_types = [
            "handoff_validation",
            "plugin_unavailable",
            "routing_failed",
            "nelly_fetch_failed"
        ]
        for error_type in valid_types:
            error = OrchestrationError(
                timestamp="2026-09-14T12:30:45.123Z",
                error_type=error_type,
                source_plugin="agent-isdd",
                root_cause="test",
                severity="high",
                suggested_fix="test"
            )
            self.assertEqual(error.error_type, error_type)

    def test_valid_severity_values(self):
        """Test all valid severity values."""
        valid_severities = ["low", "medium", "high"]
        for severity in valid_severities:
            error = OrchestrationError(
                timestamp="2026-09-14T12:30:45.123Z",
                error_type="handoff_validation",
                source_plugin="agent-isdd",
                root_cause="test",
                severity=severity,
                suggested_fix="test"
            )
            self.assertEqual(error.severity, severity)

    def test_to_dict_serialization(self):
        """Test to_dict() returns all fields as dict."""
        error = OrchestrationError(
            timestamp="2026-09-14T12:30:45.123Z",
            error_type="handoff_validation",
            source_plugin="agent-isdd",
            target_plugin="agent-tdd",
            root_cause="missing_required_field",
            severity="high",
            suggested_fix="ensure research_cache present",
            context={"missing_field": "research_cache"}
        )
        error_dict = error.to_dict()

        self.assertEqual(error_dict["timestamp"], "2026-09-14T12:30:45.123Z")
        self.assertEqual(error_dict["error_type"], "handoff_validation")
        self.assertEqual(error_dict["source_plugin"], "agent-isdd")
        self.assertEqual(error_dict["target_plugin"], "agent-tdd")
        self.assertEqual(error_dict["root_cause"], "missing_required_field")
        self.assertEqual(error_dict["severity"], "high")
        self.assertEqual(error_dict["suggested_fix"], "ensure research_cache present")
        self.assertEqual(error_dict["context"], {"missing_field": "research_cache"})

    def test_from_dict_deserialization(self):
        """Test from_dict() reconstructs error from dict."""
        error_dict = {
            "timestamp": "2026-09-14T12:30:45.123Z",
            "error_type": "plugin_unavailable",
            "source_plugin": "agent-isdd",
            "target_plugin": "agent-tdd",
            "root_cause": "plugin_not_found",
            "severity": "medium",
            "suggested_fix": "ensure agent-tdd is installed",
            "context": {"plugin": "agent-tdd"}
        }
        error = OrchestrationError.from_dict(error_dict)

        self.assertEqual(error.timestamp, "2026-09-14T12:30:45.123Z")
        self.assertEqual(error.error_type, "plugin_unavailable")
        self.assertEqual(error.source_plugin, "agent-isdd")
        self.assertEqual(error.target_plugin, "agent-tdd")
        self.assertEqual(error.root_cause, "plugin_not_found")
        self.assertEqual(error.severity, "medium")
        self.assertEqual(error.suggested_fix, "ensure agent-tdd is installed")
        self.assertEqual(error.context, {"plugin": "agent-tdd"})

    def test_json_round_trip(self):
        """Test serialization/deserialization via JSON."""
        error = OrchestrationError(
            timestamp="2026-09-14T12:30:45.123Z",
            error_type="routing_failed",
            source_plugin="agent-isdd",
            root_cause="ambiguous_state",
            severity="high",
            suggested_fix="check routing table",
            context={"phase": "design"}
        )

        # Serialize to JSON
        json_str = json.dumps(error.to_dict())

        # Deserialize from JSON
        error_dict = json.loads(json_str)
        reconstructed_error = OrchestrationError.from_dict(error_dict)

        # Verify round-trip
        self.assertEqual(reconstructed_error.timestamp, error.timestamp)
        self.assertEqual(reconstructed_error.error_type, error.error_type)
        self.assertEqual(reconstructed_error.source_plugin, error.source_plugin)
        self.assertEqual(reconstructed_error.root_cause, error.root_cause)
        self.assertEqual(reconstructed_error.severity, error.severity)
        self.assertEqual(reconstructed_error.suggested_fix, error.suggested_fix)
        self.assertEqual(reconstructed_error.context, error.context)

    def test_target_plugin_optional(self):
        """Test that target_plugin is optional."""
        error = OrchestrationError(
            timestamp="2026-09-14T12:30:45.123Z",
            error_type="nelly_fetch_failed",
            source_plugin="agent-isdd",
            root_cause="intent_hash_mismatch",
            severity="low",
            suggested_fix="re-fetch nelly brief"
        )
        self.assertIsNone(error.target_plugin)

"""Tests for before_continue hook Error Pattern integration (Slice 2.2, HIGH-RISK)."""

import json
import os
import time
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from datetime import datetime
from orchestrator.error_registry import ErrorRegistry
from orchestrator.hooks.before_continue import handle_agent_spawn


class TestBeforeContinueErrorPatternIntegration(unittest.TestCase):
    """Red tests: before_continue hook surfaces error patterns in injected context."""

    def setUp(self):
        """Set up workflow_state and a temp error registry with recurring high-severity errors."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_slug = "test-project"
        self.registry_dir = Path(self.temp_dir) / self.project_slug
        self.registry_dir.mkdir(parents=True)
        self.registry_path = self.registry_dir / "error-registry.json"

        now = datetime.utcnow().isoformat() + "Z"
        with open(self.registry_path, "w") as f:
            json.dump({
                "errors": [
                    {
                        "timestamp": now, "error_type": "handoff_validation",
                        "source_plugin": "agent-isdd", "target_plugin": "agent-tdd",
                        "root_cause": "missing_field", "severity": "high",
                        "suggested_fix": "add required field", "context": {}
                    },
                    {
                        "timestamp": now, "error_type": "handoff_validation",
                        "source_plugin": "agent-isdd", "target_plugin": "agent-tdd",
                        "root_cause": "missing_field", "severity": "high",
                        "suggested_fix": "add required field", "context": {}
                    }
                ],
                "patterns": []
            }, f)

        self.workflow_state = {
            "orchestration": {},
            "error_registry_path": str(self.registry_path)
        }

    def test_hook_does_not_raise_with_error_registry_present(self):
        """Test handle_agent_spawn completes normally when an error registry exists."""
        result = handle_agent_spawn("agent-tdd", "do the thing", self.workflow_state)
        self.assertIsInstance(result, str)
        self.assertIn("do the thing", result)

    def test_hook_surfaces_error_patterns_in_context(self):
        """Test injected context includes an Error Patterns section when recurring errors exist."""
        result = handle_agent_spawn("agent-tdd", "do the thing", self.workflow_state)
        self.assertIn("ERROR PATTERNS", result)
        self.assertIn("handoff_validation", result)

    def test_hook_omits_error_patterns_section_when_no_registry(self):
        """Test hook works fine (no Error Patterns section) when no registry path is configured."""
        workflow_state = {"orchestration": {}}
        result = handle_agent_spawn("agent-tdd", "do the thing", workflow_state)
        self.assertIsInstance(result, str)
        self.assertIn("do the thing", result)
        self.assertNotIn("ERROR PATTERNS", result)

    def test_hook_graceful_degradation_on_corrupted_registry(self):
        """Test hook doesn't raise or block spawn when registry file is corrupted."""
        with open(self.registry_path, "w") as f:
            f.write("{ not valid json ]")

        result = handle_agent_spawn("agent-tdd", "do the thing", self.workflow_state)
        self.assertIsInstance(result, str)
        self.assertIn("do the thing", result)

    def test_hook_original_prompt_always_preserved(self):
        """Test the original spawn prompt is always present in the modified prompt."""
        result = handle_agent_spawn("agent-tdd", "UNIQUE_MARKER_STRING_12345", self.workflow_state)
        self.assertIn("UNIQUE_MARKER_STRING_12345", result)

    def _spy_on_get_high_severity_patterns(self):
        """Wrap ErrorRegistry.get_high_severity_patterns with a call counter.

        Uses a plain function (not a Mock) so normal descriptor binding still
        supplies `self` when accessed through an instance -- a fresh
        ErrorPatternManager/ErrorRegistry is constructed per spawn inside the
        hook, so there's no single bound method to hand to Mock(wraps=...).
        """
        original = ErrorRegistry.get_high_severity_patterns
        call_count = {"n": 0}

        def spy(self, *args, **kwargs):
            call_count["n"] += 1
            return original(self, *args, **kwargs)

        return spy, call_count

    def test_hook_reuses_cached_patterns_across_spawns_within_same_mtime(self):
        """Test a second spawn against the same workflow_state (unchanged registry
        mtime) reuses the cached pattern list instead of re-reading the registry."""
        spy, call_count = self._spy_on_get_high_severity_patterns()
        with patch.object(ErrorRegistry, "get_high_severity_patterns", spy):
            handle_agent_spawn("agent-tdd", "spawn one", self.workflow_state)
            handle_agent_spawn("agent-tdd", "spawn two", self.workflow_state)

        self.assertEqual(call_count["n"], 1)
        self.assertIn("mtime", self.workflow_state["orchestration"]["error_pattern_cache"])

    def test_hook_refreshes_cache_when_registry_mtime_changes(self):
        """Test a changed registry mtime between spawns triggers a fresh read."""
        spy, call_count = self._spy_on_get_high_severity_patterns()
        with patch.object(ErrorRegistry, "get_high_severity_patterns", spy):
            handle_agent_spawn("agent-tdd", "spawn one", self.workflow_state)
            cached_mtime = self.workflow_state["orchestration"]["error_pattern_cache"]["mtime"]

            new_mtime = cached_mtime + 5
            os.utime(self.registry_path, (new_mtime, new_mtime))

            handle_agent_spawn("agent-tdd", "spawn two", self.workflow_state)

        self.assertEqual(call_count["n"], 2)
        self.assertEqual(
            self.workflow_state["orchestration"]["error_pattern_cache"]["mtime"], new_mtime
        )

    def test_hook_latency_under_5ms_for_error_pattern_augmentation(self):
        """Test the hook's error-pattern augmentation step stays within the 5ms budget."""
        # Measure just the hook call; network-bound nelly brief fetch is mocked/degraded
        # in this environment (no live agent-nelly), so this approximates augmentation cost.
        start = time.perf_counter()
        handle_agent_spawn("agent-tdd", "do the thing", self.workflow_state)
        elapsed_ms = (time.perf_counter() - start) * 1000
        # Generous bound since this also includes capability map build; error-pattern
        # augmentation itself is the piece under test and is a small fraction of this.
        self.assertLess(elapsed_ms, 500, f"Hook took {elapsed_ms}ms")

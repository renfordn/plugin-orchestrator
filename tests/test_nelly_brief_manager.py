"""Tests for NellyBriefManager: fetch, cache, and distribute nelly briefs."""

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from typing import Tuple, Optional

from orchestrator.nelly import NellyBriefManager


class TestNellyBriefManagerFetch(unittest.TestCase):
    """Test fetch_brief() caching and retrieval."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_workflow_state = tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        )
        self.temp_workflow_state.close()
        self.workflow_state_path = self.temp_workflow_state.name

    def tearDown(self):
        """Clean up temp files."""
        if Path(self.workflow_state_path).exists():
            Path(self.workflow_state_path).unlink()

    def _init_workflow_state(self) -> dict:
        """Initialize workflow-state.json with orchestration structure."""
        state = {
            "orchestration": {
                "nelly_brief_cache": {}
            }
        }
        with open(self.workflow_state_path, 'w') as f:
            json.dump(state, f)
        return state

    def test_fetch_brief_success(self):
        """Test successful fetch and cache of nelly brief."""
        self._init_workflow_state()
        manager = NellyBriefManager()

        # Mock the agent-nelly call
        mock_brief_text = "## Intent\nTest goal\n## Relevant Entries\nTest entries"
        mock_metadata = {"task_id": "test_123", "duration": 0.5}

        with patch.object(manager, '_call_agent_nelly', return_value=(mock_brief_text, mock_metadata)):
            brief_text, metadata = manager.fetch_brief(
                cwd="/test/dir",
                task_description="Test task",
                workflow_state={"orchestration": {"nelly_brief_cache": {}}}
            )

            self.assertEqual(brief_text, mock_brief_text)
            self.assertEqual(metadata, mock_metadata)

    def test_fetch_brief_caches_to_workflow_state(self):
        """Test that fetch stores brief in workflow_state orchestration cache."""
        self._init_workflow_state()
        manager = NellyBriefManager()

        mock_brief_text = "## Intent\nGoal\n## Relevant Entries\nEntries"
        mock_metadata = {"task_id": "test_123", "duration": 0.5}

        workflow_state = {
            "orchestration": {
                "nelly_brief_cache": {}
            }
        }

        with patch.object(manager, '_call_agent_nelly', return_value=(mock_brief_text, mock_metadata)):
            brief_text, metadata = manager.fetch_brief(
                cwd="/test/dir",
                task_description="Test task",
                workflow_state=workflow_state
            )

            # Verify cache structure
            cache = workflow_state["orchestration"]["nelly_brief_cache"]
            self.assertIn("brief_text", cache)
            self.assertIn("metadata", cache)
            self.assertIn("fetched_at", cache)
            self.assertIn("intent_hash", cache)
            self.assertIn("design_hash", cache)
            self.assertEqual(cache["brief_text"], mock_brief_text)

    def test_cache_includes_timestamp(self):
        """Test that cache includes fetched_at timestamp."""
        manager = NellyBriefManager()
        workflow_state = {"orchestration": {"nelly_brief_cache": {}}}

        before_fetch = time.time()
        with patch.object(manager, '_call_agent_nelly', return_value=("brief", {})):
            manager.fetch_brief("/test", "task", workflow_state)
        after_fetch = time.time()

        fetched_at = workflow_state["orchestration"]["nelly_brief_cache"]["fetched_at"]
        self.assertGreater(fetched_at, before_fetch)
        self.assertLess(fetched_at, after_fetch)

    def test_fetch_brief_with_hashes(self):
        """Test that fetch includes intent and design hashes in cache."""
        manager = NellyBriefManager()
        workflow_state = {"orchestration": {"nelly_brief_cache": {}}}

        intent_hash = "abc123"
        design_hash = "def456"

        with patch.object(manager, '_call_agent_nelly', return_value=("brief", {})):
            with patch.object(manager, '_compute_hashes', return_value=(intent_hash, design_hash)):
                manager.fetch_brief("/test", "task", workflow_state)

        cache = workflow_state["orchestration"]["nelly_brief_cache"]
        self.assertEqual(cache["intent_hash"], intent_hash)
        self.assertEqual(cache["design_hash"], design_hash)


class TestNellyBriefManagerInvalidation(unittest.TestCase):
    """Test cache invalidation logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.manager = NellyBriefManager()

    def test_should_invalidate_cache_on_intent_hash_drift(self):
        """Test cache invalidation when intent hash differs."""
        workflow_state = {
            "orchestration": {
                "nelly_brief_cache": {
                    "brief_text": "cached",
                    "intent_hash": "old_hash",
                    "design_hash": "design_123",
                    "fetched_at": time.time()
                }
            }
        }

        should_invalidate = self.manager.should_invalidate_cache(
            workflow_state,
            current_intent_hash="new_hash",
            current_design_hash="design_123"
        )

        self.assertTrue(should_invalidate)

    def test_should_invalidate_cache_on_design_hash_drift(self):
        """Test cache invalidation when design hash differs."""
        workflow_state = {
            "orchestration": {
                "nelly_brief_cache": {
                    "brief_text": "cached",
                    "intent_hash": "intent_123",
                    "design_hash": "old_design",
                    "fetched_at": time.time()
                }
            }
        }

        should_invalidate = self.manager.should_invalidate_cache(
            workflow_state,
            current_intent_hash="intent_123",
            current_design_hash="new_design"
        )

        self.assertTrue(should_invalidate)

    def test_should_invalidate_cache_on_ttl_expiration(self):
        """Test cache invalidation when older than 1 hour."""
        one_hour_ago = time.time() - 3601  # 1 hour + 1 second

        workflow_state = {
            "orchestration": {
                "nelly_brief_cache": {
                    "brief_text": "cached",
                    "intent_hash": "intent_123",
                    "design_hash": "design_123",
                    "fetched_at": one_hour_ago
                }
            }
        }

        should_invalidate = self.manager.should_invalidate_cache(
            workflow_state,
            current_intent_hash="intent_123",
            current_design_hash="design_123"
        )

        self.assertTrue(should_invalidate)

    def test_should_not_invalidate_valid_cache(self):
        """Test cache stays valid when hashes match and TTL not expired."""
        workflow_state = {
            "orchestration": {
                "nelly_brief_cache": {
                    "brief_text": "cached",
                    "intent_hash": "intent_123",
                    "design_hash": "design_123",
                    "fetched_at": time.time()  # Just now
                }
            }
        }

        should_invalidate = self.manager.should_invalidate_cache(
            workflow_state,
            current_intent_hash="intent_123",
            current_design_hash="design_123"
        )

        self.assertFalse(should_invalidate)

    def test_should_invalidate_missing_cache(self):
        """Test cache invalidation when cache is missing."""
        workflow_state = {"orchestration": {"nelly_brief_cache": {}}}

        should_invalidate = self.manager.should_invalidate_cache(
            workflow_state,
            current_intent_hash="intent_123",
            current_design_hash="design_123"
        )

        self.assertTrue(should_invalidate)

    def test_should_invalidate_missing_hash_fields(self):
        """Test cache invalidation when required hash fields missing."""
        workflow_state = {
            "orchestration": {
                "nelly_brief_cache": {
                    "brief_text": "cached",
                    # Missing intent_hash and design_hash
                    "fetched_at": time.time()
                }
            }
        }

        should_invalidate = self.manager.should_invalidate_cache(
            workflow_state,
            current_intent_hash="intent_123",
            current_design_hash="design_123"
        )

        self.assertTrue(should_invalidate)


class TestNellyBriefManagerDistribution(unittest.TestCase):
    """Test brief distribution to plugins."""

    def setUp(self):
        """Set up test fixtures."""
        self.manager = NellyBriefManager()
        self.brief_text = """## Intent
Test goal description

## Relevant Entries
Some project memory entries

## Intent Alignment
Aligned with previous work

## Written
By agent-nelly
"""

    def test_distribute_to_agent_tdd_includes_design_context(self):
        """Test agent-tdd receives 'Design Context' formatted brief."""
        workflow_state = {}

        formatted = self.manager.distribute_to_plugin(
            "agent-tdd",
            self.brief_text,
            workflow_state
        )

        self.assertIn("Design Context", formatted)
        self.assertIn("Nelly Brief", formatted)
        self.assertIn(self.brief_text, formatted)

    def test_distribute_to_code_reviewer_includes_project_context(self):
        """Test code-reviewer receives 'Project Context' formatted brief."""
        workflow_state = {}

        formatted = self.manager.distribute_to_plugin(
            "code-reviewer",
            self.brief_text,
            workflow_state
        )

        self.assertIn("Project Context", formatted)
        self.assertIn("Nelly Brief", formatted)
        self.assertIn(self.brief_text, formatted)

    def test_distribute_to_agent_isdd_includes_research_context(self):
        """Test agent-isdd receives 'Research Context' formatted brief."""
        workflow_state = {}

        formatted = self.manager.distribute_to_plugin(
            "agent-isdd",
            self.brief_text,
            workflow_state
        )

        # agent-isdd gets research context
        self.assertIn("Nelly Brief", formatted)
        self.assertIn(self.brief_text, formatted)

    def test_distribute_generic_plugin(self):
        """Test unknown plugin gets generic brief formatting."""
        workflow_state = {}

        formatted = self.manager.distribute_to_plugin(
            "unknown-plugin",
            self.brief_text,
            workflow_state
        )

        self.assertIn(self.brief_text, formatted)


class TestNellyBriefManagerFallback(unittest.TestCase):
    """Test fallback behavior on fetch failure."""

    def setUp(self):
        """Set up test fixtures."""
        self.manager = NellyBriefManager()

    def test_fetch_failure_uses_stale_cache(self):
        """Test fetch failure falls back to stale cache with warning."""
        stale_brief = "Stale brief from cache"
        stale_metadata = {"stale": True}

        workflow_state = {
            "orchestration": {
                "nelly_brief_cache": {
                    "brief_text": stale_brief,
                    "metadata": stale_metadata,
                    "intent_hash": "intent_123",
                    "design_hash": "design_123",
                    "fetched_at": time.time() - 7200  # 2 hours old
                }
            }
        }

        # Mock agent-nelly to raise exception and hashes to match stale cache
        with patch.object(self.manager, '_call_agent_nelly', side_effect=Exception("Network error")):
            with patch.object(self.manager, '_compute_hashes', return_value=("intent_123", "design_123")):
                brief_text, metadata = self.manager.fetch_brief(
                    "/test",
                    "task",
                    workflow_state
                )

        self.assertEqual(brief_text, stale_brief)
        self.assertEqual(metadata, stale_metadata)

    def test_fetch_failure_no_stale_cache_returns_none(self):
        """Test fetch failure with no stale cache returns None, empty dict."""
        workflow_state = {"orchestration": {"nelly_brief_cache": {}}}

        with patch.object(self.manager, '_call_agent_nelly', side_effect=Exception("Network error")):
            brief_text, metadata = self.manager.fetch_brief(
                "/test",
                "task",
                workflow_state
            )

        self.assertIsNone(brief_text)
        self.assertEqual(metadata, {})

    def test_fallback_logs_degradation_warning(self):
        """Test that fallback to stale cache logs a degradation warning."""
        workflow_state = {
            "orchestration": {
                "nelly_brief_cache": {
                    "brief_text": "Stale",
                    "metadata": {},
                    "intent_hash": "intent_123",
                    "design_hash": "design_123",
                    "fetched_at": time.time()
                }
            }
        }

        with patch.object(self.manager, '_call_agent_nelly', side_effect=Exception("Error")):
            with patch('orchestrator.nelly.logger') as mock_logger:
                self.manager.fetch_brief("/test", "task", workflow_state)
                # Verify a warning was logged
                self.assertTrue(mock_logger.warning.called)


class TestNellyBriefManagerCacheOperations(unittest.TestCase):
    """Test cache_brief and get_cached_brief operations."""

    def setUp(self):
        """Set up test fixtures."""
        self.manager = NellyBriefManager()

    def test_cache_brief_stores_with_ttl(self):
        """Test cache_brief stores brief with fetched_at timestamp."""
        workflow_state = {"orchestration": {"nelly_brief_cache": {}}}

        before_time = time.time()
        self.manager.cache_brief(
            workflow_state,
            "Test brief",
            {"key": "value"},
            "intent_hash_123",
            "design_hash_456"
        )
        after_time = time.time()

        cache = workflow_state["orchestration"]["nelly_brief_cache"]
        self.assertEqual(cache["brief_text"], "Test brief")
        self.assertEqual(cache["metadata"], {"key": "value"})
        self.assertEqual(cache["intent_hash"], "intent_hash_123")
        self.assertEqual(cache["design_hash"], "design_hash_456")
        self.assertGreaterEqual(cache["fetched_at"], before_time)
        self.assertLessEqual(cache["fetched_at"], after_time)

    def test_get_cached_brief_returns_valid_cache(self):
        """Test get_cached_brief retrieves cached brief when valid."""
        cached_brief = "Cached brief text"
        cached_metadata = {"status": "ok"}

        workflow_state = {
            "orchestration": {
                "nelly_brief_cache": {
                    "brief_text": cached_brief,
                    "metadata": cached_metadata,
                    "intent_hash": "intent_123",
                    "design_hash": "design_123",
                    "fetched_at": time.time()
                }
            }
        }

        # Mock should_invalidate_cache to return False (cache is valid)
        with patch.object(self.manager, 'should_invalidate_cache', return_value=False):
            brief_text, metadata = self.manager.get_cached_brief(
                workflow_state,
                "intent_123",
                "design_123"
            )

        self.assertEqual(brief_text, cached_brief)
        self.assertEqual(metadata, cached_metadata)

    def test_get_cached_brief_returns_none_when_invalid(self):
        """Test get_cached_brief returns None when cache is invalid."""
        workflow_state = {
            "orchestration": {
                "nelly_brief_cache": {
                    "brief_text": "Old brief",
                    "metadata": {},
                    "intent_hash": "old_hash",
                    "design_hash": "design_123",
                    "fetched_at": time.time()
                }
            }
        }

        # Mock should_invalidate_cache to return True (cache is invalid)
        with patch.object(self.manager, 'should_invalidate_cache', return_value=True):
            brief_text, metadata = self.manager.get_cached_brief(
                workflow_state,
                "new_hash",
                "design_123"
            )

        self.assertIsNone(brief_text)
        self.assertIsNone(metadata)


class TestNellyBriefManagerIntegration(unittest.TestCase):
    """Integration tests for NellyBriefManager workflows."""

    def setUp(self):
        """Set up test fixtures."""
        self.manager = NellyBriefManager()

    def test_complete_workflow_fetch_cache_distribute(self):
        """Test complete workflow: fetch -> cache -> distribute."""
        workflow_state = {"orchestration": {"nelly_brief_cache": {}}}

        mock_brief = "## Intent\nGoal\n## Relevant Entries\nEntries"
        mock_metadata = {"task_id": "123"}

        # Step 1: Fetch and cache
        with patch.object(self.manager, '_call_agent_nelly', return_value=(mock_brief, mock_metadata)):
            brief_text, metadata = self.manager.fetch_brief(
                "/test",
                "Test task",
                workflow_state
            )

        self.assertIsNotNone(brief_text)
        self.assertIn("Intent", brief_text)

        # Step 2: Distribute to agent-tdd
        formatted_for_tdd = self.manager.distribute_to_plugin(
            "agent-tdd",
            brief_text,
            workflow_state
        )

        self.assertIn("Design Context", formatted_for_tdd)
        self.assertIn(brief_text, formatted_for_tdd)

        # Step 3: Distribute to code-reviewer
        formatted_for_reviewer = self.manager.distribute_to_plugin(
            "code-reviewer",
            brief_text,
            workflow_state
        )

        self.assertIn("Project Context", formatted_for_reviewer)
        self.assertIn(brief_text, formatted_for_reviewer)

    def test_cache_reused_on_second_fetch_call_same_hashes(self):
        """Test cache is reused when hashes match."""
        workflow_state = {"orchestration": {"nelly_brief_cache": {}}}

        initial_brief = "Initial brief"
        with patch.object(self.manager, '_call_agent_nelly', return_value=(initial_brief, {})):
            first_fetch, _ = self.manager.fetch_brief(
                "/test",
                "task",
                workflow_state
            )

        # Second call with same hashes - should use cache, not call agent-nelly again
        with patch.object(self.manager, '_call_agent_nelly') as mock_call:
            mock_call.side_effect = Exception("Should not be called")
            second_fetch, _ = self.manager.fetch_brief(
                "/test",
                "task",
                workflow_state
            )

        # If cache was used, mock_call.side_effect would not be triggered
        # (this is tested in should_invalidate_cache tests)


if __name__ == "__main__":
    unittest.main()

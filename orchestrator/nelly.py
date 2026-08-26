"""NellyBriefManager: Fetch, cache, and distribute nelly briefs to plugins.

This module provides centralized brief management to avoid redundant nelly
calls from multiple consuming plugins (agent-tdd, code-reviewer, agent-isdd).

Cache Schema:
    workflow_state["orchestration"]["nelly_brief_cache"] = {
        "brief_text": str,           # Full brief from agent-nelly
        "metadata": dict,            # Brief metadata (task_id, duration, etc.)
        "intent_hash": str,          # MD5 hash of current intent.md
        "design_hash": str,          # MD5 hash of current design.md
        "fetched_at": float,         # Unix timestamp when brief was fetched
    }

Invalidation Triggers:
    - intent_hash differs (goal changed)
    - design_hash differs (design/files changed)
    - fetched_at > 1 hour old (TTL expiration)
    - Cache missing entirely

Fallback:
    - On fetch failure: use stale cache with degradation warning
    - On complete failure: return None, {} (graceful degradation)
"""

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Optional, Tuple, Dict

logger = logging.getLogger(__name__)

# TTL for cached brief in seconds (1 hour = 3600 seconds)
NELLY_BRIEF_CACHE_TTL = 3600


class NellyBriefManager:
    """
    Centralized nelly brief manager: fetch once, cache, distribute to plugins.

    Eliminates redundant nelly calls by caching brief with hash-based and
    time-based invalidation. Distributes formatted brief to consuming plugins
    (agent-tdd, code-reviewer, agent-isdd).
    """

    def __init__(self):
        """Initialize NellyBriefManager."""
        pass

    def fetch_brief(
        self,
        cwd: str,
        task_description: str,
        workflow_state: dict
    ) -> Tuple[Optional[str], dict]:
        """
        Fetch nelly brief once at workflow start.

        Calls agent-nelly:nelly-orchestrator (mocked in tests).
        Caches: brief_text, metadata, intent_hash, design_hash, fetched_at
        in workflow_state["orchestration"]["nelly_brief_cache"].

        On success: cached brief + metadata
        On failure: returns stale cache if available, else (None, {})

        Args:
            cwd: Current working directory
            task_description: Description of the task
            workflow_state: Workflow state dict

        Returns:
            Tuple of (brief_text, metadata) or (None, {}) on total failure
        """
        # Compute current hashes
        intent_hash, design_hash = self._compute_hashes(cwd)

        # Check if cache is still valid
        if not self.should_invalidate_cache(
            workflow_state,
            intent_hash,
            design_hash
        ):
            # Cache is valid, return it
            cached = workflow_state["orchestration"]["nelly_brief_cache"]
            return cached.get("brief_text"), cached.get("metadata", {})

        # Try to fetch new brief
        try:
            brief_text, metadata = self._call_agent_nelly(cwd, task_description)

            # Cache the new brief
            self.cache_brief(
                workflow_state,
                brief_text,
                metadata,
                intent_hash,
                design_hash
            )

            return brief_text, metadata

        except Exception as e:
            # Fetch failed, try fallback to stale cache (even if expired)
            logger.warning(
                f"Failed to fetch nelly brief: {e}. "
                "Attempting fallback to stale cache."
            )

            # Retrieve stale cache without validation (for graceful degradation)
            stale_brief, stale_metadata = self._get_stale_cache(workflow_state)

            if stale_brief is not None:
                logger.warning(
                    "Using stale nelly brief cache due to fetch failure. "
                    "Brief may be out of date."
                )
                return stale_brief, stale_metadata

            # No stale cache available
            return None, {}

    def should_invalidate_cache(
        self,
        workflow_state: dict,
        current_intent_hash: str,
        current_design_hash: str
    ) -> bool:
        """
        Check if cached brief should be re-fetched.

        Invalidate when:
        1. Intent hash differs (goal changed)
        2. Design hash differs (design changed)
        3. Cache older than 1h (TTL expired)
        4. Cache missing or incomplete

        Args:
            workflow_state: Workflow state dict
            current_intent_hash: Current intent hash
            current_design_hash: Current design hash

        Returns:
            True if should re-fetch, False if cache valid
        """
        cache = self._get_cache_dict(workflow_state)

        # No cache exists or is incomplete
        if not self._cache_has_required_fields(cache):
            return True

        # Check hashes: if either differs, goal or design has changed
        if cache["intent_hash"] != current_intent_hash:
            return True

        if cache["design_hash"] != current_design_hash:
            return True

        # Check TTL: cache too old if older than 1 hour
        if self._cache_is_expired(cache):
            return True

        # Cache is valid
        return False

    def cache_brief(
        self,
        workflow_state: dict,
        brief_text: str,
        metadata: dict,
        intent_hash: str,
        design_hash: str
    ) -> None:
        """
        Save brief to workflow_state orchestration.nelly_brief_cache with TTL.

        Stores all required cache fields: brief_text, metadata, hashes, and fetched_at.

        Args:
            workflow_state: Workflow state dict
            brief_text: Brief text from agent-nelly
            metadata: Brief metadata (task_id, duration, etc.)
            intent_hash: Hash of current intent (for invalidation)
            design_hash: Hash of current design (for invalidation)
        """
        # Ensure orchestration structure exists
        if "orchestration" not in workflow_state:
            workflow_state["orchestration"] = {}

        if "nelly_brief_cache" not in workflow_state["orchestration"]:
            workflow_state["orchestration"]["nelly_brief_cache"] = {}

        # Store all cache fields
        cache = workflow_state["orchestration"]["nelly_brief_cache"]
        cache["brief_text"] = brief_text
        cache["metadata"] = metadata
        cache["intent_hash"] = intent_hash
        cache["design_hash"] = design_hash
        cache["fetched_at"] = time.time()

    def get_cached_brief(
        self,
        workflow_state: dict,
        current_intent_hash: str,
        current_design_hash: str
    ) -> Tuple[Optional[str], Optional[dict]]:
        """
        Retrieve cached brief if valid (TTL + hashes match).

        Args:
            workflow_state: Workflow state dict
            current_intent_hash: Current intent hash
            current_design_hash: Current design hash

        Returns:
            Tuple of (brief_text, metadata) or (None, None) if invalid/missing
        """
        # Check if cache should be invalidated
        if self.should_invalidate_cache(
            workflow_state,
            current_intent_hash,
            current_design_hash
        ):
            return None, None

        cache = workflow_state.get("orchestration", {}).get("nelly_brief_cache", {})
        brief_text = cache.get("brief_text")
        metadata = cache.get("metadata")

        if brief_text is not None:
            return brief_text, metadata

        return None, None

    def distribute_to_plugin(
        self,
        plugin_name: str,
        brief_text: str,
        workflow_state: dict
    ) -> str:
        """
        Prepare brief for handoff to specific plugin.

        Returns formatted brief chunk (plugin-specific prep):
        - agent-tdd: "## Design Context — Nelly Brief (fetched at workflow start)"
        - code-reviewer: "## Project Context — Nelly Brief"
        - agent-isdd: Research context
        - Others: generic distribution

        Args:
            plugin_name: Name of the consuming plugin
            brief_text: Brief text to distribute
            workflow_state: Workflow state dict

        Returns:
            Formatted brief string for the plugin
        """
        if plugin_name == "agent-tdd":
            return f"""## Design Context — Nelly Brief (fetched at workflow start)

{brief_text}
"""

        elif plugin_name == "code-reviewer":
            return f"""## Project Context — Nelly Brief

{brief_text}
"""

        elif plugin_name == "agent-isdd":
            return f"""## Research Context — Nelly Brief

{brief_text}
"""

        else:
            # Generic distribution for unknown plugins
            return f"""## Nelly Brief

{brief_text}
"""

    def _call_agent_nelly(
        self,
        cwd: str,
        task_description: str
    ) -> Tuple[str, dict]:
        """
        Call agent-nelly:nelly-orchestrator to fetch brief.

        In production, this calls the actual agent-nelly plugin.
        In tests, this is mocked.

        Args:
            cwd: Current working directory
            task_description: Description of the task

        Returns:
            Tuple of (brief_text, metadata)

        Raises:
            Exception: If agent-nelly call fails
        """
        # This would call the actual agent-nelly in production.
        # For now, this is a placeholder that will be mocked in tests.
        raise NotImplementedError(
            "agent-nelly call must be mocked in tests"
        )

    def _compute_hashes(self, cwd: str) -> Tuple[str, str]:
        """
        Compute hashes for current intent and design state.

        This is used to detect when the goal or design has changed,
        triggering cache invalidation.

        Args:
            cwd: Current working directory

        Returns:
            Tuple of (intent_hash, design_hash)
        """
        # In practice, these would be computed from intent.md and design.md
        # For now, return placeholder hashes that can be mocked in tests
        intent_path = Path(cwd) / "intent.md"
        design_path = Path(cwd) / "design.md"

        intent_hash = self._hash_file(intent_path)
        design_hash = self._hash_file(design_path)

        return intent_hash, design_hash

    def _hash_file(self, file_path: Path) -> str:
        """
        Compute MD5 hash of a file, or return empty string if file doesn't exist.

        Args:
            file_path: Path to file

        Returns:
            MD5 hash hex string or empty string
        """
        try:
            if file_path.exists():
                content = file_path.read_text(encoding='utf-8')
                return hashlib.md5(content.encode()).hexdigest()
        except Exception:
            pass

        return ""

    def _get_stale_cache(self, workflow_state: dict) -> Tuple[Optional[str], Optional[dict]]:
        """
        Retrieve cached brief without validation (for fallback/degradation).

        Used when fetch fails and we want to return whatever cache we have,
        even if it's expired or hashes don't match.

        Args:
            workflow_state: Workflow state dict

        Returns:
            Tuple of (brief_text, metadata) or (None, None) if no cache exists
        """
        cache = self._get_cache_dict(workflow_state)

        brief_text = cache.get("brief_text")
        metadata = cache.get("metadata")

        if brief_text is not None:
            return brief_text, metadata

        return None, None

    def _get_cache_dict(self, workflow_state: dict) -> dict:
        """
        Safely retrieve nelly_brief_cache dict from workflow_state.

        Args:
            workflow_state: Workflow state dict

        Returns:
            Cache dict (empty dict if path doesn't exist)
        """
        return workflow_state.get("orchestration", {}).get("nelly_brief_cache", {})

    def _cache_has_required_fields(self, cache: dict) -> bool:
        """
        Check if cache has all required fields for validity.

        Required fields: brief_text, fetched_at, intent_hash, design_hash
        Optional fields: metadata

        Args:
            cache: Cache dict

        Returns:
            True if all required fields present
        """
        required_fields = ["brief_text", "fetched_at", "intent_hash", "design_hash"]
        return all(field in cache for field in required_fields)

    def _cache_is_expired(self, cache: dict) -> bool:
        """
        Check if cache is older than TTL.

        Args:
            cache: Cache dict with fetched_at timestamp

        Returns:
            True if cache older than NELLY_BRIEF_CACHE_TTL
        """
        fetched_at = cache.get("fetched_at", 0)
        age = time.time() - fetched_at
        return age > NELLY_BRIEF_CACHE_TTL

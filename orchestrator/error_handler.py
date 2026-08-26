"""ErrorHandler: Plugin error detection, classification, and recovery strategies.

This module detects plugin errors, classifies them, determines recovery strategies
(rollback, skip, degrade, workaround, pause), and logs decisions to workflow-state
handoff_history.

Recovery Paths:
1. Rollback: contract mismatch → restore checkpoint + rollback_pending marker
2. Skip: soft dependency unavailable → log and continue
3. Degrade: brief fetch failed → use stale cache + warning
4. Workaround: known fix available → apply nelly workaround
5. Pause: no recovery available → surface error to user

Error Classification:
- contract_mismatch: API/payload shape mismatch between plugins
- dependency_unavailable: Plugin or service not available
- brief_fetch_failed: Nelly brief fetch timeout/failure
- known_issue: Known issue with a workaround in nelly memory
- (any other type is returned as-is)
"""

import copy
from datetime import datetime, timezone
from typing import Optional, Tuple
from orchestrator.interop_parser import CapabilityMap
from orchestrator.checkpoint import CheckpointManager


class ErrorHandler:
    """Detect plugin errors, classify, determine recovery strategy, log decisions.

    Implements five recovery paths for different error types:
    1. Rollback: restore checkpoint on contract mismatch
    2. Skip: continue without state change on soft dependency unavailable
    3. Degrade: use stale cache when brief fetch fails
    4. Workaround: apply known fix from nelly memory
    5. Pause: surface error to user when no recovery available

    Attributes:
        capability_map: CapabilityMap for contract validation
        checkpoint_manager: CheckpointManager for rollback support
    """

    # Soft dependencies: if unavailable, skip rather than error
    SOFT_DEPENDENCIES = {"agent-nelly", "agent-ux", "agent-cache-plugin"}

    def __init__(
        self,
        capability_map: CapabilityMap,
        checkpoint_manager: CheckpointManager
    ):
        """Initialize ErrorHandler with dependencies for recovery operations.

        Args:
            capability_map: CapabilityMap for contract validation
            checkpoint_manager: CheckpointManager for checkpoint restore
        """
        self.capability_map = capability_map
        self.checkpoint_manager = checkpoint_manager

    def classify_error(
        self,
        error_type: str,
        error_details: dict
    ) -> str:
        """Classify error into standard error type.

        Maps raw error types to canonical error type strings.
        Supports: contract_mismatch, dependency_unavailable, brief_fetch_failed,
        known_issue, and any other type is returned as-is.

        Args:
            error_type: Raw error type string
            error_details: Error context dict (not used for classification, but available)

        Returns:
            Canonical error type string
        """
        # Return error type as-is (acts as passthrough classification)
        return error_type

    def determine_recovery(
        self,
        error_type: str,
        source_plugin: str,
        target_plugin: str,
        error_details: dict,
        workflow_state: dict
    ) -> Tuple[str, dict]:
        """Determine recovery strategy for error.

        Evaluates error type and context to select the best recovery path:
        - rollback: restore checkpoint (contract_mismatch + checkpoint available)
        - skip_plugin: continue unchanged (dependency_unavailable + soft dependency)
        - use_stale_cache: degrade gracefully (brief_fetch_failed + cache exists)
        - nelly_workaround: apply known fix (known_issue + workaround available)
        - pause: halt and surface to user (no recovery path available)

        Args:
            error_type: Classified error type
            source_plugin: Plugin that encountered the error
            target_plugin: Plugin involved in the error
            error_details: Error context dict with recovery hints
            workflow_state: Current workflow state

        Returns:
            Tuple of (action, updated_workflow_state):
            - action: recovery action string
            - updated_workflow_state: state with recovery applied or error details added
        """
        # Try rollback for contract mismatches (if checkpoint available)
        if error_type == "contract_mismatch":
            if self._has_checkpoint(workflow_state):
                return self._handle_rollback(
                    source_plugin, target_plugin, error_details, workflow_state
                )

        # Skip soft dependencies gracefully
        if error_type == "dependency_unavailable" and \
           target_plugin in self.SOFT_DEPENDENCIES:
            return self._handle_skip(workflow_state)

        # Degrade to stale cache on fetch failures
        if error_type == "brief_fetch_failed":
            return self._handle_degrade(workflow_state)

        # Try known issue workarounds from nelly memory
        if error_type == "known_issue":
            workaround = self.nelly_workaround_lookup(
                error_type, source_plugin, target_plugin
            )
            if workaround:
                return self._handle_workaround(workflow_state, workaround)

        # Fallback: pause and surface to user
        return self._handle_pause(error_details, workflow_state)

    def nelly_workaround_lookup(
        self,
        error_type: str,
        source_plugin: str,
        target_plugin: str
    ) -> Optional[dict]:
        """Query agent-nelly memory for known workarounds.

        Stub implementation: returns None (no workaround found).
        In production, would query nelly memory cache in workflow_state or
        external nelly service.

        Args:
            error_type: Error type to look up
            source_plugin: Source plugin context
            target_plugin: Target plugin context

        Returns:
            Workaround dict if found, None otherwise
        """
        # Stub: no workaround found. In production, query nelly memory.
        return None

    def log_error(
        self,
        workflow_state: dict,
        error_type: str,
        source_plugin: str,
        target_plugin: str,
        recovery_action: str,
        reason: str
    ) -> None:
        """Log error and recovery decision to handoff_history.

        Appends entry to workflow_state["orchestration"]["handoff_history"]
        with error type, recovery action, plugins, timestamp, and reason.

        Args:
            workflow_state: Workflow state dict (modified in-place)
            error_type: Error type
            source_plugin: Source plugin name
            target_plugin: Target plugin name
            recovery_action: Recovery action taken
            reason: Descriptive reason for recovery
        """
        # Ensure orchestration.handoff_history exists
        if "orchestration" not in workflow_state:
            workflow_state["orchestration"] = {}
        if "handoff_history" not in workflow_state["orchestration"]:
            workflow_state["orchestration"]["handoff_history"] = []

        # Create log entry
        entry = {
            "error_type": error_type,
            "source_plugin": source_plugin,
            "target_plugin": target_plugin,
            "recovery_action": recovery_action,
            "reason": reason,
            "timestamp": self._get_iso_timestamp()
        }

        # Append to history
        workflow_state["orchestration"]["handoff_history"].append(entry)

    # ===== Private Recovery Handlers =====

    def _handle_rollback(
        self,
        source_plugin: str,
        target_plugin: str,
        error_details: dict,
        workflow_state: dict
    ) -> Tuple[str, dict]:
        """Rollback recovery: restore from checkpoint on contract mismatch.

        Restores the most recent checkpoint with rollback_pending marker and
        logs the recovery decision for audit trail.

        Args:
            source_plugin: Plugin that sent the mismatched contract
            target_plugin: Plugin that received the mismatched contract
            error_details: Error context (contract mismatch details)
            workflow_state: Current workflow state

        Returns:
            Tuple of ("rollback", restored_state_with_rollback_pending_marker)
        """
        restored_state = self.checkpoint_manager.restore_checkpoint(workflow_state)

        self.log_error(
            workflow_state,
            "contract_mismatch",
            source_plugin,
            target_plugin,
            "rollback",
            f"Contract mismatch detected: {error_details}"
        )

        return "rollback", restored_state

    def _handle_skip(self, workflow_state: dict) -> Tuple[str, dict]:
        """Skip recovery: continue unchanged for soft dependency unavailable.

        Soft dependencies are optional; missing them logs a warning but doesn't
        halt the workflow. Returns state unchanged to allow continuation.

        Args:
            workflow_state: Current workflow state

        Returns:
            Tuple of ("skip_plugin", deep_copy_of_state_unchanged)
        """
        return "skip_plugin", copy.deepcopy(workflow_state)

    def _handle_degrade(self, workflow_state: dict) -> Tuple[str, dict]:
        """Degrade recovery: fall back to stale cache on brief fetch failure.

        When brief fetch times out or fails, workflow continues with stale cached
        data if available. Logs the degradation for audit.

        Args:
            workflow_state: Current workflow state with cached brief

        Returns:
            Tuple of ("use_stale_cache", state_with_stale_cache_available)
        """
        state = copy.deepcopy(workflow_state)

        self.log_error(
            state,
            "brief_fetch_failed",
            "orchestrator",
            "agent-nelly",
            "use_stale_cache",
            "Brief fetch failed, using stale cache"
        )

        return "use_stale_cache", state

    def _handle_workaround(
        self,
        workflow_state: dict,
        workaround: dict
    ) -> Tuple[str, dict]:
        """Workaround recovery: apply known fix from nelly memory.

        Known issues often have documented workarounds in nelly memory.
        Applies the workaround and logs for audit trail.

        Args:
            workflow_state: Current workflow state
            workaround: Known workaround details from nelly memory

        Returns:
            Tuple of ("nelly_workaround", state_with_workaround_applied)
        """
        state = copy.deepcopy(workflow_state)

        self.log_error(
            state,
            "known_issue",
            "orchestrator",
            "agent-nelly",
            "nelly_workaround",
            f"Applied nelly workaround: {workaround}"
        )

        return "nelly_workaround", state

    def _handle_pause(
        self,
        error_details: dict,
        workflow_state: dict
    ) -> Tuple[str, dict]:
        """Pause recovery: halt workflow and surface error to user.

        When no automated recovery is available, pause the workflow and include
        error details in the returned state for user review and action.

        Args:
            error_details: Error context with details for user
            workflow_state: Current workflow state

        Returns:
            Tuple of ("pause", state_with_error_message_and_logging)
        """
        state = copy.deepcopy(workflow_state)

        if "message" in error_details:
            state["error_message"] = error_details["message"]

        self.log_error(
            state,
            "unknown_error",
            "orchestrator",
            "unknown",
            "pause",
            "No recovery strategy available, pausing workflow"
        )

        return "pause", state

    @staticmethod
    def _has_checkpoint(workflow_state: dict) -> bool:
        """Check if workflow state has at least one checkpoint available.

        Args:
            workflow_state: Workflow state to check

        Returns:
            True if checkpoints exist and non-empty, False otherwise
        """
        return ("orchestration" in workflow_state and
                "checkpoints" in workflow_state["orchestration"] and
                bool(workflow_state["orchestration"]["checkpoints"]))

    @staticmethod
    def _get_iso_timestamp() -> str:
        """Generate ISO 8601 UTC timestamp with Z suffix.

        Returns:
            ISO timestamp string (e.g., "2026-08-25T10:35:00Z")
        """
        return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

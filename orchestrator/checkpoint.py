"""CheckpointManager: Workflow state snapshots and rollback support.

This module provides checkpoint management for creating workflow-state snapshots
before major handoffs (e.g., before agent-tdd spawn) and restoring state on error
detection for rollback recovery.

Checkpoint Schema:
    workflow_state["orchestration"]["checkpoints"] = [
        {
            "checkpoint_id": "uuid",
            "label": "before_agent_tdd_spawn",
            "timestamp": "2026-08-25T10:35:00Z",
            "state_snapshot": { /* full workflow_state copy */ }
        }
    ]

Rollback Marker (in restored state):
    {
        "rollback_pending": {
            "source": "orchestrator_checkpoint_restore",
            "checkpoint_restored": "checkpoint_id",
            "timestamp": "2026-08-25T10:40:00Z",
            "target_phase": "Design",
            "action_required": "Address the error that triggered rollback, then continue"
        }
    }
"""

import copy
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4


class CheckpointManager:
    """
    Workflow state checkpoint manager: snapshot, restore, and audit.

    Manages creation of workflow-state snapshots before major handoffs (e.g.,
    before spawning agent-tdd) and supports deterministic state restoration
    for rollback recovery. Each checkpoint includes a full state snapshot and
    audit trail (timestamp, label).

    Example usage:
        manager = CheckpointManager()

        # Create checkpoint before major handoff
        checkpoint_id = manager.create_checkpoint(workflow_state, "before_agent_tdd_spawn")

        # On error detection, restore to prior state
        restored = manager.restore_checkpoint(workflow_state, checkpoint_id)

        # Check audit history
        history = manager.get_checkpoint_history(workflow_state)
    """

    def __init__(self):
        """Initialize CheckpointManager (stateless)."""
        pass

    def _get_iso_timestamp(self) -> str:
        """
        Generate ISO 8601 UTC timestamp with Z suffix.

        Returns:
            ISO timestamp string (e.g., "2026-08-25T10:35:00Z")
        """
        return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    def _ensure_checkpoints_initialized(self, workflow_state: dict) -> None:
        """
        Ensure orchestration.checkpoints structure exists.

        Modifies workflow_state in-place to ensure nested dict structure for
        storing checkpoints. Safe to call multiple times.

        Args:
            workflow_state: Workflow state dict to initialize
        """
        if "orchestration" not in workflow_state:
            workflow_state["orchestration"] = {}
        if "checkpoints" not in workflow_state["orchestration"]:
            workflow_state["orchestration"]["checkpoints"] = []

    def _find_checkpoint(
        self,
        checkpoints: List[dict],
        checkpoint_id: Optional[str] = None
    ) -> Optional[dict]:
        """
        Find checkpoint by id or return most recent.

        Args:
            checkpoints: List of checkpoint dicts
            checkpoint_id: Specific checkpoint id to find. If None, returns most recent.

        Returns:
            Matching checkpoint dict, or None if not found
        """
        if not checkpoints:
            return None

        if checkpoint_id is None:
            return checkpoints[-1]

        for cp in checkpoints:
            if cp["checkpoint_id"] == checkpoint_id:
                return cp

        return None

    def _build_rollback_marker(self, checkpoint_id: str) -> dict:
        """
        Build rollback_pending marker for restored state.

        Args:
            checkpoint_id: ID of the checkpoint being restored from

        Returns:
            Rollback marker dict with source, checkpoint_restored, timestamp, target_phase, action_required
        """
        return {
            "source": "orchestrator_checkpoint_restore",
            "checkpoint_restored": checkpoint_id,
            "timestamp": self._get_iso_timestamp(),
            "target_phase": "Design",
            "action_required": "Address the error that triggered rollback, then continue"
        }

    def create_checkpoint(
        self,
        workflow_state: dict,
        checkpoint_label: str
    ) -> str:
        """
        Save snapshot of workflow state before major handoff.

        Creates a checkpoint with full state snapshot, label, and audit timestamp.
        Stored in workflow_state["orchestration"]["checkpoints"] array. Snapshots
        are deep copies, so modifications to original state after checkpoint
        creation do not affect the stored snapshot.

        Args:
            workflow_state: The workflow state dict to snapshot
            checkpoint_label: Label describing the checkpoint
                (e.g., "before_agent_tdd_spawn", "before_agent_isdd_spawn")

        Returns:
            checkpoint_id (string UUID) for later restoration or audit

        Example:
            >>> checkpoint_id = manager.create_checkpoint(
            ...     workflow_state, "before_agent_tdd_spawn"
            ... )
            >>> assert isinstance(checkpoint_id, str)  # Valid UUID
        """
        self._ensure_checkpoints_initialized(workflow_state)

        checkpoint_id = str(uuid4())
        timestamp = self._get_iso_timestamp()

        checkpoint = {
            "checkpoint_id": checkpoint_id,
            "label": checkpoint_label,
            "timestamp": timestamp,
            "state_snapshot": copy.deepcopy(workflow_state)
        }

        workflow_state["orchestration"]["checkpoints"].append(checkpoint)
        return checkpoint_id

    def restore_checkpoint(
        self,
        workflow_state: dict,
        checkpoint_id: Optional[str] = None
    ) -> dict:
        """
        Restore workflow state from checkpoint.

        Retrieves a checkpoint by id, or the most recent if id is None. Returns
        a deep copy of the checkpoint's state snapshot with rollback_pending
        marker added. The marker includes source, checkpoint_restored id,
        timestamp, target_phase (default "Design"), and action_required message.

        Args:
            workflow_state: Current workflow state dict (used to find checkpoint)
            checkpoint_id: Specific checkpoint to restore. If None, restores most recent.

        Returns:
            restored_state dict (deep copy of snapshot) with rollback_pending marker

        Raises:
            ValueError: If checkpoint not found or no checkpoints available

        Example:
            >>> restored = manager.restore_checkpoint(workflow_state, checkpoint_id)
            >>> assert restored["rollback_pending"]["checkpoint_restored"] == checkpoint_id
        """
        if "orchestration" not in workflow_state or \
           "checkpoints" not in workflow_state["orchestration"]:
            raise ValueError("No checkpoints available in workflow state")

        checkpoints = workflow_state["orchestration"]["checkpoints"]
        checkpoint = self._find_checkpoint(checkpoints, checkpoint_id)

        if checkpoint is None:
            if checkpoint_id:
                raise ValueError(f"Checkpoint not found: {checkpoint_id}")
            else:
                raise ValueError("No checkpoints available in workflow state")

        # Deep copy the snapshot
        restored_state = copy.deepcopy(checkpoint["state_snapshot"])

        # Add rollback_pending marker
        restored_state["rollback_pending"] = self._build_rollback_marker(
            checkpoint["checkpoint_id"]
        )

        return restored_state

    def get_checkpoint_history(self, workflow_state: dict) -> List[dict]:
        """
        Retrieve checkpoint history for audit trail.

        Returns full list of checkpoints in reverse order (most recent first).
        Useful for auditing checkpoint activity and validating rollback history.

        Args:
            workflow_state: Workflow state dict

        Returns:
            List of checkpoint dicts (most recent first). Empty list if no checkpoints.

        Example:
            >>> history = manager.get_checkpoint_history(workflow_state)
            >>> if history:
            ...     most_recent = history[0]  # Most recent checkpoint
        """
        if "orchestration" not in workflow_state or \
           "checkpoints" not in workflow_state["orchestration"]:
            return []

        checkpoints = workflow_state["orchestration"]["checkpoints"]
        return list(reversed(checkpoints))

    def is_valid_checkpoint(self, checkpoint: dict) -> bool:
        """
        Validate checkpoint has all required fields.

        Checks that checkpoint dict contains all required keys:
        checkpoint_id, label, timestamp, state_snapshot. Used for integrity
        checks when iterating checkpoints or before restore operations.

        Args:
            checkpoint: Checkpoint dict to validate

        Returns:
            True if checkpoint has all required fields, False otherwise

        Example:
            >>> cp = manager.get_checkpoint_history(workflow_state)[0]
            >>> assert manager.is_valid_checkpoint(cp)
        """
        required_fields = ["checkpoint_id", "label", "timestamp", "state_snapshot"]
        return all(field in checkpoint for field in required_fields)

    def prune_old_checkpoints(
        self,
        workflow_state: dict,
        max_checkpoints: int = 10
    ) -> None:
        """
        Keep only N most recent checkpoints.

        Modifies workflow_state in-place, removing older checkpoints to prevent
        unbounded growth of the checkpoints array. Safe to call when checkpoints
        array is below max_checkpoints (operation is a no-op). Recommended to
        call periodically (e.g., after each major orchestration phase) to bound
        memory consumption.

        Args:
            workflow_state: Workflow state dict to prune (modified in-place)
            max_checkpoints: Maximum number of checkpoints to keep (default 10)

        Example:
            >>> manager.prune_old_checkpoints(workflow_state, max_checkpoints=5)
            >>> assert len(workflow_state["orchestration"]["checkpoints"]) <= 5
        """
        if "orchestration" not in workflow_state or \
           "checkpoints" not in workflow_state["orchestration"]:
            return

        checkpoints = workflow_state["orchestration"]["checkpoints"]
        if len(checkpoints) <= max_checkpoints:
            return

        workflow_state["orchestration"]["checkpoints"] = checkpoints[-max_checkpoints:]

"""PluginRouter: Plugin availability checks, handoff validation, workflow routing.

This module orchestrates plugin workflows by:
1. Detecting plugin availability from system_reminder context
2. Validating handoff contracts between plugins
3. Routing execution to the next plugin in the workflow sequence

The router distinguishes between hard dependencies (workflow-blocking) and soft
dependencies (optional, logged if unavailable). It enforces strict handoff validation
using CapabilityMap contracts, ensuring payload shape matches target plugin's consumes
requirements before routing.

Example workflow sequence:
    agent-isdd (design approved) → agent-tdd (red-green-refactor complete)
    → code-reviewer (review complete) → None (end workflow)

If any handoff fails validation, the workflow pauses (returns None).
"""

import json
import time
import warnings
from pathlib import Path
from typing import Optional, Tuple
from orchestrator.interop_parser import CapabilityMap
from orchestrator.checkpoint import CheckpointManager
from orchestrator.telemetry import TelemetryPublisher

DEFAULT_ROUTING_TABLE_PATH = Path(__file__).parent / "routing_table.json"


class PluginRouter:
    """Route plugins through workflow, validate availability and handoffs.

    Attributes:
        HARD_DEPENDENCIES: Set of plugins required for workflow continuation.
            Unavailability blocks the workflow.
        SOFT_DEPENDENCIES: Set of optional plugins. Unavailability logs a warning
            but does not block the workflow.
        ROUTING_TABLE: Deterministic routing by (plugin, phase) tuple, loaded from
            routing_table.json (see routing_table_path on __init__) rather than
            hardcoded, so new workflow sequences don't require editing this module.
    """

    # Hard dependencies: required for workflow continuation
    HARD_DEPENDENCIES = {"agent-isdd", "agent-tdd", "code-reviewer"}

    # Soft dependencies: optional (log if unavailable, continue)
    SOFT_DEPENDENCIES = {"agent-nelly", "agent-ux", "agent-cache-plugin"}

    def __init__(
        self,
        capability_map: CapabilityMap,
        routing_table_path: Optional[str] = None,
        telemetry: Optional[TelemetryPublisher] = None
    ):
        """Initialize PluginRouter with CapabilityMap for contract queries.

        Args:
            capability_map: CapabilityMap instance providing plugin metadata
                and capability contracts (consumes/produces shapes).
            routing_table_path: Optional path to a routing table JSON file
                (see orchestrator/routing_table.json for the schema). Defaults
                to the bundled routing_table.json next to this module.
            telemetry: Optional TelemetryPublisher. When provided, availability
                checks, handoff validation, and routing decisions emit events
                to it for external monitoring. Router works identically with
                no telemetry configured.

        Raises:
            TypeError: If capability_map is None or not a CapabilityMap instance.
        """
        if capability_map is None:
            raise TypeError("capability_map cannot be None")
        self.capability_map = capability_map
        self.telemetry = telemetry
        self.ROUTING_TABLE = self._load_routing_table(
            routing_table_path or DEFAULT_ROUTING_TABLE_PATH
        )

    def _load_routing_table(self, path) -> dict:
        """Load (plugin, phase) -> next_plugin routes from a JSON config file.

        Cross-checks each route's next_plugin against the source plugin's
        INTEROP.md-derived handoff_targets and warns (does not fail) on a
        mismatch, since phase-specific routes don't always show up as a
        distinct '## → <plugin>' section.
        """
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            warnings.warn(f"Failed to load routing table from {path}: {e}")
            return {}

        table = {}
        for route in data.get("routes", []):
            plugin, phase, next_plugin = route["plugin"], route["phase"], route["next"]
            table[(plugin, phase)] = next_plugin

            if next_plugin is not None:
                source = self.capability_map.get_plugin(plugin)
                if source and source.handoff_targets and next_plugin not in source.handoff_targets:
                    warnings.warn(
                        f"routing_table.json route ({plugin}, {phase}) -> {next_plugin} "
                        f"not found in {plugin}'s INTEROP.md handoff targets "
                        f"{source.handoff_targets}"
                    )

        return table

    def check_plugin_availability(
        self,
        plugin_name: str,
        system_reminder: str
    ) -> bool:
        """Check if plugin is installed and available in this session.

        Scans system_reminder for the pattern "agent-<name>:<subagent-type>" or
        "code-reviewer:<type>" to detect plugin availability. Handles special case
        for code-reviewer which does not follow the "agent-" prefix convention.

        Args:
            plugin_name: Name of plugin to check (e.g., "agent-tdd", "agent-ux",
                or "code-reviewer"). May omit "agent-" prefix; will be added
                automatically.
            system_reminder: Session context string (typically from Claude's
                system_reminder). Searched for plugin availability patterns.

        Returns:
            True if plugin pattern found in system_reminder, False otherwise.

        Raises:
            ValueError: If plugin_name or system_reminder is empty/None.

        Example:
            >>> router.check_plugin_availability("agent-tdd",
            ...     "Setup: agent-tdd:agent-TDD available. Continue.")
            True

            >>> router.check_plugin_availability("agent-ux",
            ...     "Setup: agent-tdd:agent-TDD available. Continue.")
            False
        """
        if not plugin_name:
            raise ValueError("plugin_name cannot be empty or None")
        if system_reminder is None:
            raise ValueError("system_reminder cannot be None")

        # Normalize plugin name: add "agent-" prefix if missing
        normalized_name = self._normalize_plugin_name(plugin_name)

        # Handle code-reviewer special case (no "agent-" prefix in INTEROP)
        if normalized_name == "code-reviewer":
            available = "code-reviewer:" in system_reminder
        else:
            # Standard pattern: agent-<name>:
            pattern = f"{normalized_name}:"
            available = pattern in system_reminder

        if self.telemetry:
            self.telemetry.emit(
                "availability_check", plugin=normalized_name, available=available
            )

        return available

    def is_hard_dependency(self, plugin_name: str) -> bool:
        """Check if plugin is a hard dependency (blocks workflow if unavailable).

        Hard dependencies must be available for workflow to continue. Examples:
        agent-isdd (design), agent-tdd (implementation), code-reviewer (review).

        Args:
            plugin_name: Name of plugin to check.

        Returns:
            True if plugin is a hard dependency, False otherwise.

        Example:
            >>> router.is_hard_dependency("agent-tdd")
            True
            >>> router.is_hard_dependency("agent-nelly")
            False
        """
        return plugin_name in self.HARD_DEPENDENCIES

    def is_soft_dependency(self, plugin_name: str) -> bool:
        """Check if plugin is a soft dependency (optional, logs if unavailable).

        Soft dependencies enhance workflow but are not required. If unavailable,
        the workflow logs a warning and continues. Examples: agent-nelly (memory),
        agent-ux (UI), agent-cache-plugin (caching).

        Args:
            plugin_name: Name of plugin to check.

        Returns:
            True if plugin is a soft dependency, False otherwise.

        Example:
            >>> router.is_soft_dependency("agent-nelly")
            True
            >>> router.is_soft_dependency("agent-tdd")
            False
        """
        return plugin_name in self.SOFT_DEPENDENCIES

    def validate_handoff(
        self,
        source_plugin: str,
        source_capability_id: str,
        target_plugin: str,
        target_capability_id: str,
        payload: dict
    ) -> Tuple[bool, Optional[str]]:
        """Validate handoff contract between source and target plugin.

        Validates that:
        1. Source plugin declares the source_capability_id
        2. Target plugin declares the target_capability_id
        3. Payload contains all required fields from target's consumes contract

        This ensures plugin-to-plugin handoffs match contractual expectations
        defined in INTEROP.md files (parsed by CapabilityMap).

        Args:
            source_plugin: Name of sending plugin (e.g., "agent-isdd").
            source_capability_id: Capability ID from source (e.g., "design_spec_handoff").
            target_plugin: Name of receiving plugin (e.g., "agent-tdd").
            target_capability_id: Capability ID expected by target
                (e.g., "design_spec_slicing").
            payload: Handoff data (dict). Must contain all fields in target's
                consumes contract.

        Returns:
            Tuple of (is_valid, error_reason):
            - On success: (True, None)
            - On failure: (False, "<descriptive error message>")

        Raises:
            TypeError: If payload is not a dict or is None.

        Example:
            >>> payload = {
            ...     "requirements_md": "content",
            ...     "design_md": "content",
            ...     "research_cache": {"data": "..."},
            ...     "recap_md": "content"
            ... }
            >>> is_valid, error = router.validate_handoff(
            ...     "agent-isdd", "design_spec_handoff",
            ...     "agent-tdd", "design_spec_slicing",
            ...     payload
            ... )
            >>> is_valid
            True
        """
        if payload is None:
            raise TypeError("payload cannot be None")
        if not isinstance(payload, dict):
            raise TypeError(f"payload must be dict, got {type(payload).__name__}")

        start = time.perf_counter()
        result = self._validate_handoff_uncounted(
            source_plugin, source_capability_id,
            target_plugin, target_capability_id,
            payload
        )
        duration_ms = (time.perf_counter() - start) * 1000
        is_valid, error = result

        if self.telemetry:
            self.telemetry.emit(
                "handoff",
                source=source_plugin,
                target=target_plugin,
                success=is_valid,
                error=error,
                duration_ms=duration_ms,
                metadata={
                    "source_capability": source_capability_id,
                    "target_capability": target_capability_id,
                    "payload_size": len(payload),
                }
            )

        return result

    def _validate_handoff_uncounted(
        self,
        source_plugin: str,
        source_capability_id: str,
        target_plugin: str,
        target_capability_id: str,
        payload: dict
    ) -> Tuple[bool, Optional[str]]:
        """Core handoff validation logic, without telemetry timing wrapper."""
        # Pick up any INTEROP.md changes since the last handoff (hot-reload)
        # so validation always runs against each plugin's current contract.
        self.capability_map.refresh()

        # Validate source capability exists
        source_cap = self.capability_map.find_capability(
            source_plugin,
            source_capability_id
        )
        if not source_cap:
            return (
                False,
                f"Source capability '{source_capability_id}' not found in {source_plugin}"
            )

        # Validate target capability exists
        target_cap = self.capability_map.find_capability(
            target_plugin,
            target_capability_id
        )
        if not target_cap:
            return (
                False,
                f"Target capability '{target_capability_id}' not found in {target_plugin}"
            )

        # Validate payload matches target's consumes contract
        is_valid, error = self._validate_payload_contract(target_cap, payload)
        if not is_valid:
            return False, error

        return True, None

    def route_to_next_plugin(
        self,
        current_plugin: str,
        current_phase: str,
        handoff_valid: bool,
        workflow_state: Optional[dict] = None,
        checkpoint_manager: Optional[CheckpointManager] = None
    ) -> Optional[str]:
        """Determine next plugin in workflow sequence.

        Routes execution based on current plugin and phase. If the preceding
        handoff was invalid, returns None to halt the workflow.

        Defined routes (from ROUTING_TABLE):
        - agent-isdd + design_approved → agent-tdd
        - agent-tdd + red_green_refactor_complete → code-reviewer
        - code-reviewer + review_complete → None (end workflow)

        Args:
            current_plugin: Name of currently executing plugin.
            current_phase: Execution phase/result status (e.g., "design_approved",
                "red_green_refactor_complete").
            handoff_valid: Whether the preceding handoff (if any) was valid.
                If False, workflow is paused and None is returned.
            workflow_state: Optional workflow state dict. When provided together
                with checkpoint_manager, a checkpoint is recorded before routing
                to a next plugin (enabling rollback via CheckpointManager).
            checkpoint_manager: Optional CheckpointManager instance used to
                create the pre-handoff checkpoint. Ignored if workflow_state
                is not also provided.

        Returns:
            Name of next plugin to route to, or None to pause/end workflow.

        Example:
            >>> router.route_to_next_plugin(
            ...     "agent-isdd", "design_approved", handoff_valid=True
            ... )
            'agent-tdd'

            >>> router.route_to_next_plugin(
            ...     "agent-isdd", "design_approved", handoff_valid=False
            ... )
            None
        """
        # Invalid handoff halts workflow
        if not handoff_valid:
            return None

        # Look up routing table: (plugin, phase) -> next_plugin
        route_key = (current_plugin, current_phase)
        next_plugin = self.ROUTING_TABLE.get(route_key)

        if next_plugin is not None and workflow_state is not None and checkpoint_manager is not None:
            checkpoint_manager.create_checkpoint(workflow_state, f"before_{next_plugin}_spawn")

        if self.telemetry:
            self.telemetry.emit(
                "routing",
                current_plugin=current_plugin,
                current_phase=current_phase,
                next_plugin=next_plugin,
            )

        return next_plugin

    # ===== Private Helpers =====

    @staticmethod
    def _normalize_plugin_name(plugin_name: str) -> str:
        """Normalize plugin name to standard form.

        Adds "agent-" prefix if missing, except for "code-reviewer" which
        already follows the correct naming convention.

        Args:
            plugin_name: Raw plugin name (e.g., "tdd", "agent-tdd", "code-reviewer").

        Returns:
            Normalized plugin name (e.g., "agent-tdd", "code-reviewer").
        """
        if plugin_name == "code-reviewer":
            return "code-reviewer"

        if not plugin_name.startswith("agent-"):
            return f"agent-{plugin_name}"

        return plugin_name

    @staticmethod
    def _validate_payload_contract(capability, payload: dict) -> Tuple[bool, Optional[str]]:
        """Validate payload against capability's consumes contract.

        Checks that all required fields from capability.consumes are present
        in the payload.

        Args:
            capability: Capability object with consumes contract.
            payload: Handoff payload dict to validate.

        Returns:
            Tuple of (is_valid, error_reason):
            - On success: (True, None)
            - On failure: (False, "<error message>")
        """
        if not capability.consumes:
            # No consumes contract; accept any payload
            return True, None

        # Check all required fields present
        for field_name in capability.consumes:
            if field_name not in payload:
                return (
                    False,
                    f"Missing required field in payload: {field_name}"
                )

        return True, None

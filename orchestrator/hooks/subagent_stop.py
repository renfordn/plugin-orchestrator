"""SubagentStop hook: Capture agent completion, validate output, and log handoff.

Implements the subagent_stop hook that intercepts agent completion and:
1. Parses phase markers from agent report (e.g., RED_GREEN_REFACTOR_COMPLETE)
2. Detects escalation markers (<!--AGENT-TDD-RESEARCH-VALIDATION-FAILED:...-->)
3. Validates output against capability contract (from INTEROP.md "produces" field)
4. Logs handoff to workflow-state["orchestration"]["handoff_history"]
5. Triggers error handler on contract violations (for rollback/degrade/pause)
6. Handles soft dependency unavailability gracefully

Error Handling:
- Regex errors in marker parsing: log warning, continue with None marker
- Contract validation failures: log to handoff_history, trigger error handler
- Escalation markers: set rollback_pending for orchestrator to handle
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Tuple
from orchestrator.error_handler import ErrorHandler
from orchestrator.checkpoint import CheckpointManager
from orchestrator.interop_parser import CapabilityMap

logger = logging.getLogger(__name__)


def handle_agent_completion(
    agent_type: str,
    report: str,
    workflow_state: dict
) -> Dict:
    """
    Capture agent completion, validate output, and log handoff.

    Parses agent report for phase markers, validates against capability contract,
    logs handoff to workflow-state, and triggers error handler if contract violated.

    Args:
        agent_type: Name of completed agent (e.g., "agent-tdd")
        report: Agent output report
        workflow_state: Current workflow state dict (modified in-place)

    Returns:
        Summary dict the calling hook entrypoint can use to surface a
        systemMessage to the user:
        {
            "success": bool,
            "validation_result": "contract_valid" | "contract_invalid",
            "error_details": {...},
            "escalation_marker": str | None,
            "recovery_action": str | None  # set only when contract_invalid
        }
    """
    # Ensure orchestration structure exists
    _ensure_orchestration_structure(workflow_state)

    # Extract phase marker from report
    phase_marker = _extract_phase_marker(report)

    # Check for escalation markers
    escalation_marker = _detect_escalation_marker(report)
    if escalation_marker:
        _set_rollback_pending(workflow_state, escalation_marker)

    # Validate output against capability contract
    capability_map = workflow_state.get("orchestration", {}).get("capability_map", {})
    validation_result, error_details = _validate_output_contract(
        agent_type, report, capability_map
    )

    # Determine success based on validation
    success = validation_result == "contract_valid"

    # Log handoff to history
    _log_handoff(
        workflow_state,
        agent_type,
        phase_marker,
        validation_result,
        error_details,
        success
    )

    # Trigger error handler on contract mismatch
    recovery_action = None
    if validation_result == "contract_invalid":
        recovery_action = _trigger_error_handler(
            workflow_state,
            agent_type,
            error_details
        )

    return {
        "success": success,
        "validation_result": validation_result,
        "error_details": error_details,
        "escalation_marker": escalation_marker,
        "recovery_action": recovery_action,
    }


def _ensure_orchestration_structure(workflow_state: dict) -> None:
    """Ensure workflow_state has required orchestration structure.

    Creates orchestration and handoff_history if missing.

    Args:
        workflow_state: Workflow state dict (modified in-place)
    """
    if "orchestration" not in workflow_state:
        workflow_state["orchestration"] = {}

    if "handoff_history" not in workflow_state["orchestration"]:
        workflow_state["orchestration"]["handoff_history"] = []


def _extract_phase_marker(report: str) -> Optional[str]:
    """Extract phase marker from agent report.

    Searches for phase markers in two formats:
    1. Markdown heading: "### Phase Marker: RED_GREEN_REFACTOR_COMPLETE"
    2. HTML comment: "<!--AGENT-TDD-PHASE:RED_GREEN_REFACTOR_COMPLETE-->"

    Handles regex errors gracefully (logs warning, returns None).

    Args:
        report: Agent report text

    Returns:
        Phase marker string (e.g., "RED_GREEN_REFACTOR_COMPLETE") or None if not found
    """
    try:
        # Pattern 1: Markdown heading "### Phase Marker: <MARKER>"
        match = re.search(r"###\s+Phase Marker:\s+([A-Z_]+)", report, re.IGNORECASE)
        if match:
            marker = match.group(1)
            logger.debug(f"Extracted phase marker (markdown): {marker}")
            return marker

        # Pattern 2: HTML comment "<!--..PHASE..-->"
        match = re.search(r"<!--.*?PHASE[:\-_]+(\w+).*?-->", report, re.IGNORECASE)
        if match:
            marker = match.group(1)
            logger.debug(f"Extracted phase marker (HTML comment): {marker}")
            return marker

        logger.debug("No phase marker found in report")
        return None
    except re.error as e:
        logger.warning(f"Regex error parsing phase marker: {e}. Continuing without marker.")
        return None


def _detect_escalation_marker(report: str) -> Optional[str]:
    """Detect escalation markers in agent report.

    Escalation markers signal that an agent encountered a condition requiring
    orchestrator intervention (research gap, design conflict, etc.). Supported formats:
    - <!--AGENT-TDD-RESEARCH-VALIDATION-FAILED:reason-->
    - <!--AGENT-TDD-PLAN-FLAG:reason-->
    - <!--AGENT-*-FAILED:reason-->

    Handles regex errors gracefully (logs warning, returns None).

    Args:
        report: Agent report text

    Returns:
        Full escalation marker string (e.g., "<!--AGENT-TDD-RESEARCH-VALIDATION-FAILED:...-->")
        or None if no escalation detected
    """
    try:
        # Pattern 1: FAILED markers (highest priority)
        match = re.search(r"(<!--AGENT-[A-Z]+-[A-Z]+-FAILED:[^>]*-->)", report)
        if match:
            marker = match.group(1)
            logger.info(f"Detected escalation marker (FAILED): {marker}")
            return marker

        # Pattern 2: PLAN-FLAG markers (design/validity conflicts)
        match = re.search(r"(<!--AGENT-[A-Z]+-PLAN-FLAG:[^>]*-->)", report)
        if match:
            marker = match.group(1)
            logger.info(f"Detected escalation marker (PLAN-FLAG): {marker}")
            return marker

        logger.debug("No escalation markers found in report")
        return None
    except re.error as e:
        logger.warning(f"Regex error parsing escalation markers: {e}. Continuing without marker.")
        return None


def _validate_output_contract(
    agent_type: str,
    report: str,
    capability_map: Dict
) -> Tuple[str, Dict]:
    """Validate agent output against capability contract.

    Checks that all required output fields (from agent's INTEROP.md "produces" contract)
    are present in the agent report. Validation uses case-insensitive text search.

    Contract structure (from INTEROP.md):
        produces: {
            "field_name": "required" | "optional"
        }

    Args:
        agent_type: Name of agent (e.g., "agent-tdd")
        report: Agent output report text
        capability_map: Capability map dict (from workflow_state["orchestration"]["capability_map"])

    Returns:
        Tuple of (validation_result, error_details):
        - validation_result: "contract_valid" | "contract_invalid"
        - error_details: {} if valid, or dict with:
            - reason: "contract_mismatch"
            - missing_fields: [list of missing required fields]
            - expected_contract: {full produces dict from contract}
    """
    # Look up contract for this agent in capability map
    agent_contract = capability_map.get(agent_type, {})
    produces_contract = agent_contract.get("produces", {})

    # No contract defined for this agent; treat as valid (lenient)
    if not produces_contract:
        logger.debug(f"No contract defined for {agent_type}; validation lenient")
        return "contract_valid", {}

    # Check each required field in the contract
    missing_required_fields = []
    for field_name, requirement_level in produces_contract.items():
        # Only validate "required" fields; "optional" fields are not enforced
        if requirement_level == "required":
            # Use case-insensitive text search (field names in reports are often lowercased)
            if field_name.lower() not in report.lower():
                missing_required_fields.append(field_name)
                logger.debug(f"Missing required field: {field_name}")

    # If any required fields are missing, validation fails
    if missing_required_fields:
        error_details = {
            "reason": "contract_mismatch",
            "missing_fields": missing_required_fields,
            "expected_contract": produces_contract
        }
        logger.warning(
            f"Contract validation failed for {agent_type}: missing {missing_required_fields}"
        )
        return "contract_invalid", error_details

    logger.debug(f"Contract validation passed for {agent_type}")
    return "contract_valid", {}


def _set_rollback_pending(workflow_state: dict, escalation_marker: str) -> None:
    """Set rollback_pending marker when escalation detected.

    Stores rollback_pending marker in workflow_state to signal orchestrator that
    agent encountered a condition requiring intervention (research gap, design conflict, etc.).

    Rollback marker structure:
    {
        "source": "escalation_marker_detected",
        "escalation_type": "research_validation_failed" | "plan_validity_conflict" | "unknown_escalation",
        "marker_found": "full HTML comment marker",
        "timestamp": "ISO 8601 timestamp",
        "action_required": "Guidance for orchestrator"
    }

    Args:
        workflow_state: Workflow state dict (modified in-place)
        escalation_marker: Full escalation marker string (e.g., "<!--AGENT-TDD-RESEARCH-VALIDATION-FAILED:...-->")
    """
    # Classify escalation type based on marker content
    escalation_type = _classify_escalation_type(escalation_marker)

    rollback_marker = {
        "source": "escalation_marker_detected",
        "escalation_type": escalation_type,
        "marker_found": escalation_marker,
        "timestamp": _get_iso_timestamp(),
        "action_required": "Review escalation trigger and retry or rollback"
    }

    workflow_state["rollback_pending"] = rollback_marker
    logger.info(f"Rollback pending: escalation_type={escalation_type}, marker={escalation_marker}")


def _classify_escalation_type(escalation_marker: str) -> str:
    """Classify escalation type from marker content.

    Maps marker keywords to canonical escalation type strings.

    Args:
        escalation_marker: Full escalation marker string

    Returns:
        Escalation type: "research_validation_failed" | "plan_validity_conflict" | "unknown_escalation"
    """
    if "RESEARCH-VALIDATION-FAILED" in escalation_marker:
        return "research_validation_failed"
    elif "PLAN-FLAG" in escalation_marker:
        return "plan_validity_conflict"
    else:
        return "unknown_escalation"


def _log_handoff(
    workflow_state: dict,
    agent_type: str,
    phase_marker: Optional[str],
    validation_result: str,
    error_details: Dict,
    success: bool
) -> None:
    """Log handoff to workflow-state handoff_history.

    Appends entry to handoff_history with audit trail information:
    timestamp, source agent, phase marker, validation result, success status, error details.

    Handoff entry structure:
    {
        "timestamp": "ISO 8601 timestamp",
        "source": "agent-tdd" (or other agent type),
        "success": true | false,
        "validation_result": "contract_valid" | "contract_invalid",
        "phase_marker": "RED_GREEN_REFACTOR_COMPLETE" (if present),
        "error_details": {...} (if validation failed)
    }

    Args:
        workflow_state: Workflow state dict (modified in-place)
        agent_type: Name of completing agent (e.g., "agent-tdd")
        phase_marker: Extracted phase marker from report, or None if not found
        validation_result: "contract_valid" or "contract_invalid"
        error_details: Dict with error details (empty if validation passed)
        success: Boolean indicating overall success (True if contract valid)
    """
    # Build base handoff entry (always include these fields)
    handoff_entry = {
        "timestamp": _get_iso_timestamp(),
        "source": agent_type,
        "success": success,
        "validation_result": validation_result
    }

    # Add optional fields only if present
    if phase_marker:
        handoff_entry["phase_marker"] = phase_marker

    if error_details:
        handoff_entry["error_details"] = error_details

    # Append to handoff history for audit trail
    workflow_state["orchestration"]["handoff_history"].append(handoff_entry)

    logger.info(
        f"Handoff logged: {agent_type} → validation={validation_result}, "
        f"success={success}, phase={phase_marker}"
    )


def _trigger_error_handler(
    workflow_state: dict,
    agent_type: str,
    error_details: Dict
) -> Optional[str]:
    """Trigger error handler on contract violation.

    Instantiates ErrorHandler to classify and handle the contract mismatch error.
    Recovery paths: rollback (restore checkpoint), skip (soft deps), degrade (stale cache),
    workaround (nelly memory), or pause (surface to user).

    Errors during error handling are caught and logged (non-fatal).

    Args:
        workflow_state: Workflow state dict (may be modified by error handler)
        agent_type: Agent that violated contract
        error_details: Dict with validation failure details (reason, missing_fields, etc.)

    Returns:
        The recovery action taken (e.g. "rollback", "pause"), or None if the
        error handler itself failed.
    """
    try:
        # Instantiate error handler with dependencies
        capability_map = CapabilityMap()
        checkpoint_manager = CheckpointManager()
        error_handler = ErrorHandler(capability_map, checkpoint_manager)

        # Determine recovery strategy and handle the error
        error_type = error_details.get("reason", "contract_mismatch")
        recovery_action, updated_state = error_handler.determine_recovery(
            error_type=error_type,
            source_plugin=agent_type,
            target_plugin="orchestrator",
            error_details=error_details,
            workflow_state=workflow_state
        )

        logger.warning(
            f"Contract violation from {agent_type}: "
            f"error_type={error_type}, recovery_action={recovery_action}"
        )

        return recovery_action

    except (IOError, OSError) as e:
        # File I/O error (e.g., checkpoint file not accessible)
        logger.error(
            f"Error handler file I/O error: {e.__class__.__name__}: {e}. "
            "Proceeding without recovery."
        )
        return None
    except Exception as e:
        # Any other error in error handler (parsing, instantiation, etc.)
        logger.error(
            f"Error handler failed: {e.__class__.__name__}: {e}. "
            "Proceeding without error recovery."
        )
        return None


def _get_iso_timestamp() -> str:
    """Generate ISO 8601 UTC timestamp with Z suffix.

    Returns:
        ISO timestamp string (e.g., "2026-08-25T10:35:00Z")
    """
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def check_plugin_availability(plugin_name: str) -> bool:
    """Check if a plugin is available/installed.

    Stub implementation: always returns True.
    In production, would check plugin registry or system.

    Args:
        plugin_name: Name of plugin to check

    Returns:
        True if plugin available, False otherwise
    """
    # Stub for tests; can be mocked
    return True

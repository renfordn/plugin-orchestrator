"""OrchestrationError: Structured error representation for logging and nelly integration."""

from typing import Optional, Dict, Any


class OrchestrationError:
    """Represents an orchestration error with metadata for logging and analysis.

    Attributes:
        timestamp: ISO 8601 timestamp when error occurred
        error_type: handoff_validation | plugin_unavailable | routing_failed | nelly_fetch_failed
        source_plugin: Name of the plugin where error occurred
        target_plugin: Optional; name of the target plugin (if applicable)
        root_cause: Root cause description (e.g., "missing_required_field", "plugin_not_found")
        severity: low | medium | high
        suggested_fix: Recommended remediation step
        context: Additional metadata (dict) for error context
    """

    VALID_ERROR_TYPES = {
        "handoff_validation",
        "plugin_unavailable",
        "routing_failed",
        "nelly_fetch_failed"
    }

    VALID_SEVERITIES = {"low", "medium", "high"}

    def __init__(
        self,
        timestamp: str,
        error_type: str,
        source_plugin: str,
        root_cause: str,
        severity: str,
        suggested_fix: str,
        target_plugin: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        """Initialize OrchestrationError.

        Args:
            timestamp: ISO 8601 timestamp
            error_type: One of VALID_ERROR_TYPES
            source_plugin: Name of source plugin
            root_cause: Root cause description
            severity: One of VALID_SEVERITIES
            suggested_fix: Recommended fix
            target_plugin: Optional target plugin name
            context: Optional metadata dict

        Raises:
            ValueError: If error_type or severity is invalid
        """
        if error_type not in self.VALID_ERROR_TYPES:
            raise ValueError(f"invalid error_type: {error_type}")
        if severity not in self.VALID_SEVERITIES:
            raise ValueError(f"invalid severity: {severity}")

        self.timestamp = timestamp
        self.error_type = error_type
        self.source_plugin = source_plugin
        self.target_plugin = target_plugin
        self.root_cause = root_cause
        self.severity = severity
        self.suggested_fix = suggested_fix
        self.context = context or {}

    def to_dict(self) -> Dict[str, Any]:
        """Serialize error to dict for JSON storage."""
        return {
            "timestamp": self.timestamp,
            "error_type": self.error_type,
            "source_plugin": self.source_plugin,
            "target_plugin": self.target_plugin,
            "root_cause": self.root_cause,
            "severity": self.severity,
            "suggested_fix": self.suggested_fix,
            "context": self.context
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "OrchestrationError":
        """Deserialize error from dict."""
        return OrchestrationError(
            timestamp=data["timestamp"],
            error_type=data["error_type"],
            source_plugin=data["source_plugin"],
            root_cause=data["root_cause"],
            severity=data["severity"],
            suggested_fix=data["suggested_fix"],
            target_plugin=data.get("target_plugin"),
            context=data.get("context", {})
        )

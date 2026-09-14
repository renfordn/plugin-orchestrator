"""ErrorLogger: Dual-tier logging for session and persistent error storage."""

import json
from pathlib import Path
from typing import List
from orchestrator.error import OrchestrationError


class ErrorLogger:
    """Logs orchestration errors to both session (memory) and persistent (file) storage.

    Session-scoped errors are immediately accessible within the workflow.
    Persistent errors enable cross-session pattern detection.
    """

    def __init__(self):
        """Initialize ErrorLogger with empty session error list."""
        self._session_errors: List[OrchestrationError] = []

    def log_error(self, error: OrchestrationError) -> None:
        """Log error to session-scoped storage (in-memory).

        Args:
            error: OrchestrationError to log
        """
        self._session_errors.append(error)

    def persist_error(self, error: OrchestrationError, base_path: str, project_slug: str) -> None:
        """Persist error to project-wide error registry (file).

        Creates error-registry.json in ~/.claude/sdd-memory/<project_slug>/ if it doesn't exist.
        Appends error to errors[] array.

        Non-blocking; errors logged to session even if file persistence fails.

        Args:
            error: OrchestrationError to persist
            base_path: Base directory path (e.g., ~/.claude/sdd-memory)
            project_slug: Project identifier
        """
        # Always log to session first (non-blocking)
        self.log_error(error)

        try:
            registry_dir = Path(base_path) / project_slug
            registry_dir.mkdir(parents=True, exist_ok=True)

            registry_path = registry_dir / "error-registry.json"

            # Load existing registry or create new
            if registry_path.exists():
                with open(registry_path) as f:
                    registry = json.load(f)
            else:
                registry = {"errors": [], "patterns": []}

            # Append error
            registry["errors"].append(error.to_dict())

            # Write back
            with open(registry_path, "w") as f:
                json.dump(registry, f, indent=2)

        except Exception:
            # Non-blocking: error already logged to session even if persistence fails
            pass

    def get_session_errors(self) -> List[OrchestrationError]:
        """Return all session-scoped errors logged so far.

        Returns:
            List of OrchestrationError objects
        """
        return self._session_errors.copy()

    def clear_session_errors(self) -> None:
        """Clear all session-scoped errors from memory."""
        self._session_errors = []

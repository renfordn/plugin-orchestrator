"""ErrorPatternManager: Nelly integration for error pattern surfacing."""

import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime as dt
from orchestrator.error_registry import ErrorRegistry, ErrorPattern

logger = logging.getLogger(__name__)


class ErrorPatternManager:
    """Integrates error logs with agent-nelly via handoff contract."""

    def __init__(self, registry_path: Optional[Path] = None):
        """Initialize ErrorPatternManager.

        Args:
            registry_path: Path to error-registry.json
        """
        self.registry = ErrorRegistry(registry_path)

    def augment_nelly_brief(
        self,
        brief: Dict[str, Any],
        registry_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """Add Error Patterns section to nelly brief if high-severity recurring errors exist.

        Modifies brief in-place with error_patterns section.

        Args:
            brief: Nelly brief dict to augment
            registry_path: Path to error-registry.json (optional, uses initialized path if not provided)

        Returns:
            Augmented brief dict
        """
        pattern_dicts = self.get_high_severity_pattern_dicts(registry_path)
        if pattern_dicts:
            brief["error_patterns"] = pattern_dicts

        return brief

    def get_high_severity_pattern_dicts(
        self,
        registry_path: Optional[Path] = None
    ) -> List[Dict[str, Any]]:
        """Return high-severity recurring error patterns as plain dicts.

        Direct accessor for callers (e.g. the before_continue hook) that want
        pattern data without going through augment_nelly_brief's brief-mutation
        contract -- avoids passing a throwaway empty brief dict just to read
        the result back out.

        Args:
            registry_path: Path to error-registry.json (optional, uses initialized path if not provided)

        Returns:
            List of pattern dicts (pattern_id, error_type, occurrence_frequency,
            first_seen, last_seen, affected_plugins, suggested_fix, severity).
            Empty list on missing registry or when no high-severity patterns exist.
        """
        try:
            patterns = self.registry.get_high_severity_patterns(registry_path)
            return [
                {
                    "pattern_id": pattern.pattern_id,
                    "error_type": pattern.error_type,
                    "occurrence_frequency": f"{pattern.occurrence_count} times in past 7 days",
                    "first_seen": pattern.first_seen,
                    "last_seen": pattern.last_seen,
                    "affected_plugins": pattern.affected_plugins,
                    "suggested_fix": self._suggest_fix_for_pattern(pattern),
                    "severity": pattern.severity
                }
                for pattern in patterns
            ]
        except Exception as e:
            # Graceful degradation: if error registry unavailable, return no patterns
            logger.warning(f"Failed to retrieve error patterns: {e}")
            return []

    def query_error_history(
        self,
        plugin: Optional[str] = None,
        error_type: Optional[str] = None,
        days_back: int = 30,
        registry_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """Respond to nelly on-demand queries for error context.

        Returns ranked error history by severity, recency, actionability.

        Args:
            plugin: Filter by plugin name (optional)
            error_type: Filter by error type (optional)
            days_back: Look back N days (default: 30)
            registry_path: Path to error-registry.json

        Returns:
            Dict with ranked error history
        """
        try:
            errors = self.registry.query_errors(registry_path, plugin, error_type, days_back)

            # Rank by: severity (high first), recency (recent first), actionability (has fix)
            sorted_errors = sorted(
                errors,
                key=lambda e: (
                    {"high": 0, "medium": 1, "low": 2}.get(e.severity, 3),  # severity
                    -dt.fromisoformat(e.timestamp.replace("Z", "+00:00")).timestamp(),  # recency
                    0 if e.suggested_fix else 1  # actionability
                )
            )

            return {
                "query": {
                    "plugin": plugin,
                    "error_type": error_type,
                    "days_back": days_back
                },
                "error_count": len(sorted_errors),
                "errors": [e.to_dict() for e in sorted_errors],
                "summary": self._summarize_errors(sorted_errors)
            }
        except Exception as e:
            # Graceful degradation: return empty result
            logger.warning(f"Failed to query error history: {e}")
            return {
                "query": {"plugin": plugin, "error_type": error_type, "days_back": days_back},
                "error_count": 0,
                "errors": [],
                "summary": "Error history unavailable"
            }

    @staticmethod
    def _suggest_fix_for_pattern(pattern: ErrorPattern) -> str:
        """Suggest a fix for a detected error pattern."""
        suggestions = {
            "handoff_validation": "Ensure all required fields are present in the handoff payload",
            "plugin_unavailable": "Install or enable the unavailable plugin(s)",
            "routing_failed": "Check routing table configuration and phase state",
            "nelly_fetch_failed": "Verify nelly intent and reset brief cache if needed"
        }
        return suggestions.get(pattern.error_type, "Review error logs for context")

    @staticmethod
    def _summarize_errors(errors: List[Any]) -> str:
        """Generate a summary of error list."""
        if not errors:
            return "No errors found"

        by_type = {}
        for error in errors:
            by_type[error.error_type] = by_type.get(error.error_type, 0) + 1

        summary_parts = []
        for error_type, count in sorted(by_type.items()):
            summary_parts.append(f"{count} {error_type}")

        return f"Found {len(errors)} errors: {', '.join(summary_parts)}"

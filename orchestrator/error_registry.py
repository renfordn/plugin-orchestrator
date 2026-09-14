"""ErrorRegistry: Pattern detection and querying for persistent error logs."""

import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from orchestrator.error import OrchestrationError


class ErrorPattern:
    """Represents a detected recurring error pattern."""

    def __init__(
        self,
        pattern_id: str,
        error_type: str,
        occurrence_count: int,
        first_seen: str,
        last_seen: str,
        severity: str,
        affected_plugins: List[str],
        common_root_causes: List[str]
    ):
        self.pattern_id = pattern_id
        self.error_type = error_type
        self.occurrence_count = occurrence_count
        self.first_seen = first_seen
        self.last_seen = last_seen
        self.severity = severity
        self.affected_plugins = affected_plugins
        self.common_root_causes = common_root_causes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "error_type": self.error_type,
            "occurrence_count": self.occurrence_count,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "severity": self.severity,
            "affected_plugins": self.affected_plugins,
            "common_root_causes": self.common_root_causes
        }


class ErrorRegistry:
    """Reads, queries, and analyzes error logs for pattern detection."""

    def __init__(self, registry_path: Optional[Path] = None):
        """Initialize ErrorRegistry.

        Args:
            registry_path: Path to error-registry.json. If None, must be provided to query_errors.
        """
        self.registry_path = registry_path
        self._registry_cache: Dict[str, Any] = {}  # path str -> (mtime, parsed dict)

    def _load_registry(self, path: Path) -> Optional[Dict[str, Any]]:
        """Load the registry JSON, reusing the cached parse when the file's mtime is unchanged."""
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return None

        key = str(path)
        cached = self._registry_cache.get(key)
        if cached is not None and cached[0] == mtime:
            return cached[1]

        try:
            with open(path) as f:
                data = json.load(f)
        except Exception:
            return None

        self._registry_cache[key] = (mtime, data)
        return data

    def query_errors(
        self,
        registry_path: Optional[Path] = None,
        plugin: Optional[str] = None,
        error_type: Optional[str] = None,
        days_back: int = 30
    ) -> List[OrchestrationError]:
        """Query errors by plugin, type, or date range.

        Args:
            registry_path: Path to error-registry.json (uses self.registry_path if not provided)
            plugin: Filter by source_plugin or target_plugin (optional)
            error_type: Filter by error type (optional)
            days_back: Include only errors from past N days (default: 30)

        Returns:
            List of matching OrchestrationError objects
        """
        path = registry_path or self.registry_path
        if not path or not path.exists():
            return []

        registry = self._load_registry(path)
        if registry is None:
            return []

        cutoff_date = (datetime.utcnow() - timedelta(days=days_back)).isoformat()
        results = []

        for error_dict in registry.get("errors", []):
            # Check timestamp
            if error_dict.get("timestamp", "") < cutoff_date:
                continue

            # Check plugin
            if plugin and plugin not in [error_dict.get("source_plugin"), error_dict.get("target_plugin")]:
                continue

            # Check error type
            if error_type and error_dict.get("error_type") != error_type:
                continue

            results.append(OrchestrationError.from_dict(error_dict))

        return results

    def detect_patterns(
        self,
        registry_path: Optional[Path] = None,
        days_back: int = 7
    ) -> List[ErrorPattern]:
        """Identify recurring errors: 2+ of same type in N days = recurring pattern.

        Args:
            registry_path: Path to error-registry.json (uses self.registry_path if not provided)
            days_back: Window for pattern detection (default: 7 days)

        Returns:
            List of detected ErrorPattern objects
        """
        path = registry_path or self.registry_path
        if not path or not path.exists():
            return []

        all_errors = self.query_errors(path, days_back=days_back)

        # Group by error_type
        by_type: Dict[str, List[OrchestrationError]] = {}
        for error in all_errors:
            if error.error_type not in by_type:
                by_type[error.error_type] = []
            by_type[error.error_type].append(error)

        # Detect patterns (2+ errors in window)
        patterns = []
        for error_type, errors in by_type.items():
            if len(errors) >= 2:
                # Extract metadata
                plugins = set()
                causes = set()
                for error in errors:
                    plugins.add(error.source_plugin)
                    if error.target_plugin:
                        plugins.add(error.target_plugin)
                    causes.add(error.root_cause)

                pattern_id = f"{error_type}_x{len(errors)}_{days_back}d"
                pattern = ErrorPattern(
                    pattern_id=pattern_id,
                    error_type=error_type,
                    occurrence_count=len(errors),
                    first_seen=errors[0].timestamp,
                    last_seen=errors[-1].timestamp,
                    severity=errors[0].severity,  # Use first error's severity
                    affected_plugins=sorted(list(plugins)),
                    common_root_causes=sorted(list(causes))
                )
                patterns.append(pattern)

        return patterns

    def get_high_severity_patterns(
        self,
        registry_path: Optional[Path] = None
    ) -> List[ErrorPattern]:
        """Return patterns flagged as high-severity for nelly brief integration.

        Args:
            registry_path: Path to error-registry.json (uses self.registry_path if not provided)

        Returns:
            List of high-severity ErrorPattern objects
        """
        patterns = self.detect_patterns(registry_path)
        return [p for p in patterns if p.severity == "high" and p.occurrence_count >= 2]

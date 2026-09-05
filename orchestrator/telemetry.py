"""TelemetryPublisher: extensible event publishing for external monitoring.

PluginRouter fires standard-shaped events (availability checks, handoff
validation, routing decisions) into a TelemetryPublisher, which fans them out
to any number of registered hooks. This is the integration point for
external sinks (Datadog, New Relic, a custom collector) without coupling the
router to any specific monitoring backend.
"""

import logging
import time
from typing import Callable, Dict

logger = logging.getLogger(__name__)

TelemetryHook = Callable[[Dict], None]


class TelemetryPublisher:
    """Registry of telemetry hooks that receive standard-shaped events."""

    def __init__(self):
        self._hooks: list[TelemetryHook] = []

    def register_hook(self, hook: TelemetryHook) -> None:
        """Register a hook to receive future emitted events."""
        self._hooks.append(hook)

    def unregister_hook(self, hook: TelemetryHook) -> None:
        """Remove a previously registered hook, if present."""
        if hook in self._hooks:
            self._hooks.remove(hook)

    def emit(self, event_type: str, **fields) -> None:
        """Build a standard event envelope and fan it out to all hooks.

        A hook raising does not stop other hooks from receiving the event,
        nor propagate back to the caller (telemetry must never break
        orchestration).
        """
        event = {"timestamp": time.time(), "event_type": event_type, **fields}
        for hook in self._hooks:
            try:
                hook(event)
            except Exception as e:
                logger.warning(f"Telemetry hook {hook!r} raised {e!r}; skipping")

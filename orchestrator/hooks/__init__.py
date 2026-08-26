"""Hooks: PreToolUse and SubagentStop integration for orchestrator.

This module provides two hooks that integrate the orchestrator into the agent-isdd workflow:

1. PreToolUse hook (before_continue.py): Load workflow-state, fetch nelly brief,
   build capability map, and inject cache-optimized context before agent spawn.

2. SubagentStop hook (subagent_stop.py): Capture agent completion, parse phase markers,
   validate output contract, and log handoff to workflow-state.

Both hooks coordinate to maintain state consistency and enable error recovery via
checkpoints and handoff history.
"""

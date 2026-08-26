#!/usr/bin/env python3
"""PreToolUse hook entrypoint (matcher: Agent).

Bridges Claude Code's actual hook contract (JSON on stdin, `hookSpecificOutput`
on stdout) to orchestrator.hooks.before_continue.handle_agent_spawn, the pure
context-injection function this plugin already implements and tests.

Contract (see https://code.claude.com/docs/en/hooks.md):
  stdin:  {"cwd": ..., "tool_name": "Agent", "tool_input": {"prompt": ..., "subagent_type": ...}, ...}
  stdout: {"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": {"prompt": "..."}}}

Any failure degrades to a no-op (exit 0, no output) so a broken hook never blocks
a real agent spawn.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hook_state import workflow_state_path, load_workflow_state, save_workflow_state  # noqa: E402


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    tool_input = payload.get("tool_input") or {}
    spawn_prompt = tool_input.get("prompt")
    agent_type = tool_input.get("subagent_type") or payload.get("agent_type") or "unknown"
    if not spawn_prompt:
        sys.exit(0)

    cwd = payload.get("cwd") or os.getcwd()
    state_path = workflow_state_path(cwd)
    if not state_path:
        sys.exit(0)  # no active SDD workflow — nothing to inject

    workflow_state = load_workflow_state(state_path)

    try:
        from orchestrator.hooks.before_continue import handle_agent_spawn
        modified_prompt = handle_agent_spawn(agent_type, spawn_prompt, workflow_state)
    except Exception:
        sys.exit(0)  # graceful degradation — never block the spawn

    save_workflow_state(state_path, workflow_state)

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": {"prompt": modified_prompt}
        }
    }))
    sys.exit(0)


if __name__ == "__main__":
    main()

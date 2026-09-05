"""Shared helpers for plugin-orchestrator's hook entrypoints.

Locates and persists the same workflow-state.json that agent-isdd scaffolds and
agent-tdd reads, so the orchestrator's PreToolUse/SubagentStop hooks mutate the
one shared per-feature state file rather than an orchestrator-private copy.

project_slug()/memory_dir()/spec_dir() mirror the canonical implementation in
agent-isdd/hooks/sdd_memory.py + shared_slug.py (also duplicated in agent-nelly
and agent-tdd) -- kept here as a small, dependency-free copy since this plugin's
CLAUDE_PLUGIN_ROOT is a separate directory tree from agent-isdd's.
"""
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orchestrator.state_store import FileStateStore  # noqa: E402

BASE = os.path.join(os.path.expanduser("~"), ".claude", "sdd-memory")


def project_slug(cwd):
    absp = os.path.abspath(cwd)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", absp).strip("-").lower()
    return slug or "root"


def memory_dir(cwd):
    return os.path.join(BASE, project_slug(cwd))


def active_state_dir(cwd):
    """Directory of the most recently modified workflow-state.md under memory_dir(cwd), or None."""
    pattern = os.path.join(memory_dir(cwd), "spec", "*", "workflow-state.md")
    files = glob.glob(pattern)
    if not files:
        return None
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return os.path.dirname(files[0])


def workflow_state_path(cwd):
    """Path to the active feature's workflow-state.json, or None if no SDD workflow is active."""
    feature_dir = active_state_dir(cwd)
    if not feature_dir:
        return None
    return os.path.join(feature_dir, "workflow-state.json")


def _state_store_for(path):
    """Build a FileStateStore + workflow_id addressing the exact given path.

    FileStateStore addresses files by (directory, workflow_id) -> "<workflow_id>.json"
    within that directory; the workflow_id here is just the path's basename
    minus ".json", so the file written is the exact path the caller gave us.
    """
    directory = os.path.dirname(path) or "."
    workflow_id = os.path.basename(path)
    if workflow_id.endswith(".json"):
        workflow_id = workflow_id[: -len(".json")]
    return FileStateStore(directory), workflow_id


def load_workflow_state(path):
    """Load workflow-state.json into a dict, tolerant of a missing or malformed file."""
    try:
        store, workflow_id = _state_store_for(path)
        return store.get(workflow_id)
    except (OSError, ValueError):
        return {}


def save_workflow_state(path, data):
    """Write workflow-state.json back to disk (atomic write, advisory lock)."""
    store, workflow_id = _state_store_for(path)
    store.save(workflow_id, data)

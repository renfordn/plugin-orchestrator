"""WorkflowStateStore: pluggable, process-shared workflow state.

Modules across this codebase (interop_parser's capability-map cache,
checkpoint.py, the hooks) each read and write workflow-state.json directly.
This module provides a small store abstraction with a get/save contract so
that state can live behind a shared backend instead: an in-memory store for
tests and single-process use, and a file-based JSON store (one file per
workflow, atomic writes, advisory file locking) so multiple processes on the
same machine can safely share workflow state.
"""

import copy
import json
import os
import tempfile
from abc import ABC, abstractmethod

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX platforms
    fcntl = None


class WorkflowStateStore(ABC):
    """Interface for reading and writing workflow state by workflow_id."""

    @abstractmethod
    def get(self, workflow_id: str) -> dict:
        """Return the stored state for workflow_id, or {} if none exists."""
        raise NotImplementedError

    @abstractmethod
    def save(self, workflow_id: str, state: dict) -> None:
        """Persist state for workflow_id, replacing any prior value."""
        raise NotImplementedError


class InMemoryStateStore(WorkflowStateStore):
    """Single-process state store backed by a plain dict. Default for tests."""

    def __init__(self):
        self._states: dict = {}

    def get(self, workflow_id: str) -> dict:
        return copy.deepcopy(self._states.get(workflow_id, {}))

    def save(self, workflow_id: str, state: dict) -> None:
        self._states[workflow_id] = copy.deepcopy(state)


class FileStateStore(WorkflowStateStore):
    """State store backed by one JSON file per workflow_id in a directory.

    Writes are atomic (write to a temp file, then os.replace) and
    lock-guarded (advisory flock on the target path) so concurrent writers
    in the same or different processes cannot interleave and corrupt a file.
    """

    def __init__(self, directory: str):
        self.directory = directory
        os.makedirs(self.directory, exist_ok=True)

    def _path(self, workflow_id: str) -> str:
        return os.path.join(self.directory, f"{workflow_id}.json")

    def get(self, workflow_id: str) -> dict:
        path = self._path(workflow_id)
        if not os.path.exists(path):
            return {}
        with open(path, "r") as f:
            if fcntl:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                return json.load(f)
            finally:
                if fcntl:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def save(self, workflow_id: str, state: dict) -> None:
        path = self._path(workflow_id)
        lock_path = path + ".lock"
        with open(lock_path, "w") as lock_file:
            if fcntl:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                fd, tmp_path = tempfile.mkstemp(
                    dir=self.directory, prefix=f".{workflow_id}-", suffix=".tmp"
                )
                try:
                    with os.fdopen(fd, "w") as tmp_file:
                        json.dump(state, tmp_file, indent=2)
                    os.replace(tmp_path, path)
                except BaseException:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                    raise
            finally:
                if fcntl:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

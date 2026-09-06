"""WorkflowStateStore: pluggable, process-shared workflow state.

Modules across this codebase (interop_parser's capability-map cache,
checkpoint.py, the hooks) each read and write workflow-state.json directly.
This module provides a small store abstraction with a get/save contract so
that state can live behind a shared backend instead: an in-memory store for
tests and single-process use, a file-based JSON store (one file per
workflow, atomic writes, advisory file locking) so multiple processes on the
same machine can safely share workflow state, and a Redis-backed store so
workflow state can be shared across machines, not just processes on one
host - the "distributed workflow state tracking" enhancement.
"""

import copy
import json
import os
import tempfile
from abc import ABC, abstractmethod
from typing import Optional

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


class RedisStateStore(WorkflowStateStore):
    """State store backed by Redis, so workflow state is shared across machines.

    FileStateStore only helps processes on one host; a multi-host orchestrator
    deployment (e.g. workers behind a load balancer) needs state visible from
    any of them, which is what this store is for.

    Requires the `redis` package (not a hard dependency of this project - only
    import this class if you're using it). Each workflow is stored as a JSON
    string under a namespaced key so unrelated data in the same Redis instance
    isn't touched.

    Connection settings fall back to environment variables when not passed
    explicitly, so a deployment can configure Redis once (env) rather than at
    every call site:

    - REDIS_HOST     -> host
    - REDIS_PORT     -> port (int)
    - REDIS_DB       -> db (int)
    - REDIS_PASSWORD -> password
    - REDIS_KEY_PREFIX -> key_prefix

    An explicit constructor argument always wins over its environment
    variable, and either can be overridden per Redis kwarg (e.g. passing
    host= alone still picks up REDIS_PORT/REDIS_DB from the environment).
    """

    _ENV_KWARGS = {
        "REDIS_HOST": ("host", str),
        "REDIS_PORT": ("port", int),
        "REDIS_DB": ("db", int),
        "REDIS_PASSWORD": ("password", str),
    }

    def __init__(self, redis_client=None, key_prefix: Optional[str] = None, **redis_kwargs):
        """
        Args:
            redis_client: An existing redis.Redis (or compatible) client to
                reuse, e.g. for connection pooling or a fake client in tests.
                If omitted, one is created from redis_kwargs (merged with
                REDIS_* environment variables; see class docstring).
            key_prefix: Prefix applied to every workflow's Redis key. Defaults
                to REDIS_KEY_PREFIX if set, else "orchestrator:workflow:".
            **redis_kwargs: Passed to redis.Redis(...) when redis_client is
                not given (e.g. host, port, db, password). Any left unset
                fall back to the matching REDIS_* environment variable.

        Raises:
            ImportError: If the `redis` package is not installed and no
                redis_client was supplied.
        """
        self.key_prefix = (
            key_prefix
            if key_prefix is not None
            else os.environ.get("REDIS_KEY_PREFIX", "orchestrator:workflow:")
        )
        if redis_client is not None:
            self._client = redis_client
        else:
            try:
                import redis
            except ImportError as e:
                raise ImportError(
                    "RedisStateStore requires the 'redis' package. "
                    "Install it with: pip install redis"
                ) from e

            merged_kwargs = dict(self._env_redis_kwargs())
            merged_kwargs.update(redis_kwargs)
            self._client = redis.Redis(**merged_kwargs)

    @classmethod
    def _env_redis_kwargs(cls) -> dict:
        """Build redis.Redis kwargs from REDIS_* environment variables."""
        kwargs = {}
        for env_var, (kwarg_name, cast) in cls._ENV_KWARGS.items():
            value = os.environ.get(env_var)
            if value is not None:
                kwargs[kwarg_name] = cast(value)
        return kwargs

    def _key(self, workflow_id: str) -> str:
        return f"{self.key_prefix}{workflow_id}"

    def get(self, workflow_id: str) -> dict:
        raw = self._client.get(self._key(workflow_id))
        if raw is None:
            return {}
        return json.loads(raw)

    def save(self, workflow_id: str, state: dict) -> None:
        self._client.set(self._key(workflow_id), json.dumps(state))

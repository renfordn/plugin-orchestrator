"""Tests for WorkflowStateStore: pluggable, process-shared workflow state.

Covers the Priority 1 "distributed workflow state tracking" enhancement's
first slice: a store abstraction (get/save) with an in-memory backend for
tests/single-process use, and a file-based JSON backend so multiple
processes on the same machine can share workflow state instead of each
module reading/writing workflow-state.json directly.
"""

import json
import os
import tempfile
import threading
import unittest
import unittest.mock

from orchestrator.state_store import InMemoryStateStore, FileStateStore, RedisStateStore

try:
    import redis as redis_lib

    HAS_REDIS = False
    REDIS_PORT = None
    for _candidate_port in (6379, 6399):
        try:
            redis_lib.Redis(
                host="localhost", port=_candidate_port, socket_connect_timeout=0.5
            ).ping()
            HAS_REDIS = True
            REDIS_PORT = _candidate_port
            break
        except Exception:
            continue
except ImportError:
    HAS_REDIS = False
    REDIS_PORT = None


class TestInMemoryStateStore(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryStateStore()

    def test_get_missing_workflow_returns_empty_dict(self):
        self.assertEqual(self.store.get("nonexistent"), {})

    def test_save_then_get_roundtrips(self):
        self.store.save("wf-1", {"phase": "design_approved"})
        self.assertEqual(self.store.get("wf-1"), {"phase": "design_approved"})

    def test_save_returns_a_copy_not_a_shared_reference(self):
        state = {"phase": "design_approved"}
        self.store.save("wf-1", state)
        retrieved = self.store.get("wf-1")
        retrieved["phase"] = "mutated"
        self.assertEqual(self.store.get("wf-1"), {"phase": "design_approved"})

    def test_separate_workflow_ids_are_isolated(self):
        self.store.save("wf-1", {"phase": "a"})
        self.store.save("wf-2", {"phase": "b"})
        self.assertEqual(self.store.get("wf-1"), {"phase": "a"})
        self.assertEqual(self.store.get("wf-2"), {"phase": "b"})


class TestFileStateStore(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store = FileStateStore(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_get_missing_workflow_returns_empty_dict(self):
        self.assertEqual(self.store.get("nonexistent"), {})

    def test_save_then_get_roundtrips(self):
        self.store.save("wf-1", {"phase": "design_approved"})
        self.assertEqual(self.store.get("wf-1"), {"phase": "design_approved"})

    def test_save_writes_readable_json_file_on_disk(self):
        self.store.save("wf-1", {"phase": "design_approved"})
        path = os.path.join(self.tmpdir.name, "wf-1.json")
        self.assertTrue(os.path.exists(path))
        with open(path) as f:
            self.assertEqual(json.load(f), {"phase": "design_approved"})

    def test_second_store_instance_sees_saved_state(self):
        """Simulates a second process reading state a first process wrote."""
        self.store.save("wf-1", {"phase": "design_approved"})
        other_store = FileStateStore(self.tmpdir.name)
        self.assertEqual(other_store.get("wf-1"), {"phase": "design_approved"})

    def test_save_is_atomic_no_partial_file_left_on_crash_mid_write(self):
        # Corrupt-write simulation: ensure a completed save never leaves a
        # .tmp file behind (atomic rename cleans up).
        self.store.save("wf-1", {"phase": "design_approved"})
        leftover_tmp_files = [
            f for f in os.listdir(self.tmpdir.name) if f.endswith(".tmp")
        ]
        self.assertEqual(leftover_tmp_files, [])

    def test_concurrent_saves_do_not_corrupt_file(self):
        errors = []

        def writer(n):
            try:
                for _ in range(20):
                    self.store.save("wf-shared", {"counter": n})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        # File must be valid, fully-written JSON, not truncated/interleaved.
        result = self.store.get("wf-shared")
        self.assertIn("counter", result)


class TestRedisStateStoreImportGuard(unittest.TestCase):
    def test_missing_redis_package_raises_clear_import_error(self):
        import builtins
        real_import = builtins.__import__

        def blocking_import(name, *args, **kwargs):
            if name == "redis":
                raise ImportError("No module named 'redis'")
            return real_import(name, *args, **kwargs)

        with unittest.mock.patch("builtins.__import__", side_effect=blocking_import):
            with self.assertRaises(ImportError) as ctx:
                RedisStateStore(host="localhost", port=6379)
        self.assertIn("pip install redis", str(ctx.exception))


class TestRedisStateStoreEnvConfig(unittest.TestCase):
    """Test REDIS_* environment variable fallback for connection settings."""

    @unittest.mock.patch.dict(os.environ, {
        "REDIS_HOST": "redis.internal",
        "REDIS_PORT": "6380",
        "REDIS_DB": "2",
        "REDIS_PASSWORD": "secret",
        "REDIS_KEY_PREFIX": "myapp:workflow:",
    }, clear=False)
    @unittest.mock.patch("redis.Redis")
    def test_env_vars_used_when_no_kwargs_passed(self, mock_redis_cls):
        store = RedisStateStore()

        mock_redis_cls.assert_called_once_with(
            host="redis.internal", port=6380, db=2, password="secret"
        )
        self.assertEqual(store.key_prefix, "myapp:workflow:")

    @unittest.mock.patch.dict(os.environ, {
        "REDIS_HOST": "redis.internal",
        "REDIS_PORT": "6380",
    }, clear=False)
    @unittest.mock.patch("redis.Redis")
    def test_explicit_kwargs_take_precedence_over_env(self, mock_redis_cls):
        RedisStateStore(host="explicit-host", key_prefix="explicit:")

        mock_redis_cls.assert_called_once_with(host="explicit-host", port=6380)

    @unittest.mock.patch.dict(os.environ, {}, clear=True)
    @unittest.mock.patch("redis.Redis")
    def test_defaults_used_when_no_env_and_no_kwargs(self, mock_redis_cls):
        store = RedisStateStore()

        mock_redis_cls.assert_called_once_with()
        self.assertEqual(store.key_prefix, "orchestrator:workflow:")

    def test_redis_client_bypasses_env_and_kwargs_entirely(self):
        fake_client = object()
        with unittest.mock.patch.dict(os.environ, {"REDIS_HOST": "should-be-ignored"}):
            store = RedisStateStore(redis_client=fake_client)
        self.assertIs(store._client, fake_client)


@unittest.skipUnless(HAS_REDIS, "requires a reachable Redis server")
class TestRedisStateStore(unittest.TestCase):
    def setUp(self):
        self.store = RedisStateStore(
            host="localhost", port=REDIS_PORT, key_prefix="test:whats-next:"
        )
        self.addCleanup(self._flush_test_keys)

    def _flush_test_keys(self):
        for key in self.store._client.keys("test:whats-next:*"):
            self.store._client.delete(key)

    def test_get_missing_workflow_returns_empty_dict(self):
        self.assertEqual(self.store.get("nonexistent"), {})

    def test_save_then_get_roundtrips(self):
        self.store.save("wf-1", {"phase": "design_approved"})
        self.assertEqual(self.store.get("wf-1"), {"phase": "design_approved"})

    def test_separate_workflow_ids_are_isolated(self):
        self.store.save("wf-1", {"phase": "a"})
        self.store.save("wf-2", {"phase": "b"})
        self.assertEqual(self.store.get("wf-1"), {"phase": "a"})
        self.assertEqual(self.store.get("wf-2"), {"phase": "b"})

    def test_second_store_instance_sees_saved_state(self):
        """Simulates a second host/process reading state a first one wrote."""
        self.store.save("wf-1", {"phase": "design_approved"})
        other_store = RedisStateStore(
            host="localhost", port=REDIS_PORT, key_prefix="test:whats-next:"
        )
        self.assertEqual(other_store.get("wf-1"), {"phase": "design_approved"})

    def test_keys_are_namespaced_with_prefix(self):
        self.store.save("wf-1", {"phase": "a"})
        self.assertIsNotNone(self.store._client.get("test:whats-next:wf-1"))

    def test_reuses_provided_redis_client(self):
        store = RedisStateStore(redis_client=self.store._client, key_prefix="test:whats-next:")
        store.save("wf-shared-client", {"phase": "a"})
        self.assertEqual(self.store.get("wf-shared-client"), {"phase": "a"})


if __name__ == "__main__":
    unittest.main()

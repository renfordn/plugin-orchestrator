"""Tests for async validation support (high-concurrency handoff validation)."""

import asyncio
import unittest
from pathlib import Path

from orchestrator.core import PluginRouter
from orchestrator.interop_parser import CapabilityMap


class TestValidateHandoffAsync(unittest.IsolatedAsyncioTestCase):
    """Test PluginRouter.validate_handoff_async."""

    def setUp(self):
        self.plugin_dir = str(Path(__file__).parent / "fixtures")
        self.capability_map = CapabilityMap(self.plugin_dir)
        self.router = PluginRouter(self.capability_map)
        self.valid_payload = {
            "requirements_md": "content",
            "design_md": "content",
            "research_cache": {"data": "value"},
            "recap_md": "content"
        }

    async def test_matches_sync_result_on_success(self):
        """Test the async wrapper returns the same result as the sync method."""
        is_valid, error = await self.router.validate_handoff_async(
            "agent-isdd", "design_spec_handoff",
            "agent-tdd", "design_spec_slicing",
            self.valid_payload
        )

        self.assertTrue(is_valid)
        self.assertIsNone(error)

    async def test_matches_sync_result_on_failure(self):
        """Test the async wrapper surfaces the same error as the sync method."""
        is_valid, error = await self.router.validate_handoff_async(
            "agent-isdd", "design_spec_handoff",
            "agent-tdd", "design_spec_slicing",
            {"requirements_md": "content"}
        )

        self.assertFalse(is_valid)
        self.assertIsNotNone(error)

    async def test_concurrent_validations_all_complete_correctly(self):
        """Test many concurrent validate_handoff_async calls each get the right result."""
        valid_calls = [
            self.router.validate_handoff_async(
                "agent-isdd", "design_spec_handoff",
                "agent-tdd", "design_spec_slicing",
                self.valid_payload
            )
            for _ in range(20)
        ]
        invalid_calls = [
            self.router.validate_handoff_async(
                "agent-isdd", "design_spec_handoff",
                "agent-tdd", "design_spec_slicing",
                {}
            )
            for _ in range(20)
        ]

        results = await asyncio.gather(*valid_calls, *invalid_calls)

        valid_results, invalid_results = results[:20], results[20:]
        self.assertTrue(all(is_valid for is_valid, _ in valid_results))
        self.assertTrue(all(not is_valid for is_valid, _ in invalid_results))

    async def test_does_not_block_event_loop(self):
        """Test other coroutines can make progress while validation runs concurrently."""
        progressed = []

        async def ticker():
            for i in range(5):
                await asyncio.sleep(0)
                progressed.append(i)

        await asyncio.gather(
            ticker(),
            *[
                self.router.validate_handoff_async(
                    "agent-isdd", "design_spec_handoff",
                    "agent-tdd", "design_spec_slicing",
                    self.valid_payload
                )
                for _ in range(10)
            ]
        )

        self.assertEqual(progressed, [0, 1, 2, 3, 4])


class TestValidateInputAsync(unittest.IsolatedAsyncioTestCase):
    """Test CapabilityMap.validate_input_async."""

    def setUp(self):
        self.plugin_dir = str(Path(__file__).parent / "fixtures")
        self.cap_map = CapabilityMap(self.plugin_dir)

    async def test_matches_sync_result(self):
        """Test the async wrapper returns the same result as validate_input."""
        is_valid, error = await self.cap_map.validate_input_async(
            "agent-tdd", "design_spec_slicing",
            {
                "requirements_md": "content",
                "design_md": "content",
                "research_cache": {"data": "value"},
                "recap_md": "content"
            }
        )

        self.assertTrue(is_valid)
        self.assertIsNone(error)

    async def test_passes_through_enforce_types(self):
        """Test enforce_types is forwarded to the underlying sync validation."""
        is_valid, error = await self.cap_map.validate_input_async(
            "agent-tdd", "design_spec_slicing",
            {
                "requirements_md": "content",
                "design_md": "content",
                "research_cache": "not-an-object",
                "recap_md": "content"
            },
            enforce_types=True
        )

        self.assertFalse(is_valid)
        self.assertIn("research_cache", error)


if __name__ == "__main__":
    unittest.main()

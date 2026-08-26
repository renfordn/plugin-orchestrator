"""Tests for CacheOptimizedSpawnPrompt."""

import unittest
from orchestrator.cache_strategy import CacheOptimizedSpawnPrompt


class TestCacheOptimizedSpawnPromptRed(unittest.TestCase):
    """Red tests for CacheOptimizedSpawnPrompt tier ordering and assembly."""

    def setUp(self):
        """Set up test fixtures."""
        self.builder = CacheOptimizedSpawnPrompt()

        # Minimal Tier 1 context (stable across plugins)
        self.tier1_context = {
            "capability_map": "# Plugin Registry\nPlugin A, Plugin B, Plugin C",
            "nelly_brief": "Brief summary of project context",
            "interop_excerpts": "Handoff contracts: section 1, section 2",
        }

        # Minimal Tier 2 context (stable across phases)
        self.tier2_context = {
            "requirements_md": "# Requirements\nFeature X, Feature Y",
            "design_md": "# Design\nModule A handles X, Module B handles Y",
            "research_cache": "Research findings on caching patterns",
            "workflow_state": "Current workflow phase: design",
        }

        # Minimal Tier 3 context (unique per call)
        self.tier3_context = {
            "slice_spec": "Implement slice 1.1: CapabilityMap",
            "review_findings": "Code review: approved with minor fixes",
            "plugin_instructions": "Run tests before commit",
        }

    def test_tier_ordering_tier1_first(self):
        """Red: Verify Tier 1 content appears FIRST in spawn prompt."""
        prompt = self.builder.build_spawn_prompt(
            plugin_name="agent-tdd",
            tier1_context=self.tier1_context,
            tier2_context=self.tier2_context,
            tier3_context=self.tier3_context,
        )

        # Extract positions
        tier1_marker = "# TIER 1"
        tier2_marker = "# TIER 2"

        tier1_pos = prompt.find(tier1_marker)
        tier2_pos = prompt.find(tier2_marker)

        # Tier 1 must come before Tier 2
        self.assertGreater(tier1_pos, -1, "Tier 1 marker not found")
        self.assertGreater(tier2_pos, -1, "Tier 2 marker not found")
        self.assertLess(tier1_pos, tier2_pos, "Tier 1 must come before Tier 2")

    def test_tier_ordering_tier2_before_tier3(self):
        """Red: Verify Tier 2 content appears before Tier 3."""
        prompt = self.builder.build_spawn_prompt(
            plugin_name="agent-tdd",
            tier1_context=self.tier1_context,
            tier2_context=self.tier2_context,
            tier3_context=self.tier3_context,
        )

        # Extract positions
        tier2_marker = "# TIER 2"
        tier3_marker = "# TIER 3"

        tier2_pos = prompt.find(tier2_marker)
        tier3_pos = prompt.find(tier3_marker)

        # Tier 2 must come before Tier 3
        self.assertGreater(tier2_pos, -1, "Tier 2 marker not found")
        self.assertGreater(tier3_pos, -1, "Tier 3 marker not found")
        self.assertLess(tier2_pos, tier3_pos, "Tier 2 must come before Tier 3")

    def test_tier1_contains_capability_map(self):
        """Red: Verify Tier 1 includes capability map."""
        prompt = self.builder.build_spawn_prompt(
            plugin_name="agent-tdd",
            tier1_context=self.tier1_context,
            tier2_context=self.tier2_context,
            tier3_context=self.tier3_context,
        )

        # Tier 1 should include capability map content
        self.assertIn(
            self.tier1_context["capability_map"],
            prompt,
            "Capability map not found in Tier 1"
        )

    def test_tier1_contains_nelly_brief(self):
        """Red: Verify Tier 1 includes nelly brief."""
        prompt = self.builder.build_spawn_prompt(
            plugin_name="agent-tdd",
            tier1_context=self.tier1_context,
            tier2_context=self.tier2_context,
            tier3_context=self.tier3_context,
        )

        # Tier 1 should include nelly brief
        self.assertIn(
            self.tier1_context["nelly_brief"],
            prompt,
            "Nelly brief not found in Tier 1"
        )

    def test_tier1_contains_interop_excerpts(self):
        """Red: Verify Tier 1 includes INTEROP excerpts."""
        prompt = self.builder.build_spawn_prompt(
            plugin_name="agent-tdd",
            tier1_context=self.tier1_context,
            tier2_context=self.tier2_context,
            tier3_context=self.tier3_context,
        )

        # Tier 1 should include INTEROP excerpts
        self.assertIn(
            self.tier1_context["interop_excerpts"],
            prompt,
            "INTEROP excerpts not found in Tier 1"
        )

    def test_tier2_contains_requirements(self):
        """Red: Verify Tier 2 includes requirements.md."""
        prompt = self.builder.build_spawn_prompt(
            plugin_name="agent-tdd",
            tier1_context=self.tier1_context,
            tier2_context=self.tier2_context,
            tier3_context=self.tier3_context,
        )

        # Tier 2 should include requirements
        self.assertIn(
            self.tier2_context["requirements_md"],
            prompt,
            "Requirements not found in Tier 2"
        )

    def test_tier2_contains_design(self):
        """Red: Verify Tier 2 includes design.md."""
        prompt = self.builder.build_spawn_prompt(
            plugin_name="agent-tdd",
            tier1_context=self.tier1_context,
            tier2_context=self.tier2_context,
            tier3_context=self.tier3_context,
        )

        # Tier 2 should include design
        self.assertIn(
            self.tier2_context["design_md"],
            prompt,
            "Design not found in Tier 2"
        )

    def test_tier2_contains_research_cache(self):
        """Red: Verify Tier 2 includes research cache."""
        prompt = self.builder.build_spawn_prompt(
            plugin_name="agent-tdd",
            tier1_context=self.tier1_context,
            tier2_context=self.tier2_context,
            tier3_context=self.tier3_context,
        )

        # Tier 2 should include research cache
        self.assertIn(
            self.tier2_context["research_cache"],
            prompt,
            "Research cache not found in Tier 2"
        )

    def test_tier3_contains_slice_spec(self):
        """Red: Verify Tier 3 includes slice spec."""
        prompt = self.builder.build_spawn_prompt(
            plugin_name="agent-tdd",
            tier1_context=self.tier1_context,
            tier2_context=self.tier2_context,
            tier3_context=self.tier3_context,
        )

        # Tier 3 should include slice spec
        self.assertIn(
            self.tier3_context["slice_spec"],
            prompt,
            "Slice spec not found in Tier 3"
        )

    def test_tier3_contains_review_findings(self):
        """Red: Verify Tier 3 includes review findings."""
        prompt = self.builder.build_spawn_prompt(
            plugin_name="agent-tdd",
            tier1_context=self.tier1_context,
            tier2_context=self.tier2_context,
            tier3_context=self.tier3_context,
        )

        # Tier 3 should include review findings
        self.assertIn(
            self.tier3_context["review_findings"],
            prompt,
            "Review findings not found in Tier 3"
        )

    def test_tier3_contains_plugin_instructions(self):
        """Red: Verify Tier 3 includes plugin-specific instructions."""
        prompt = self.builder.build_spawn_prompt(
            plugin_name="agent-tdd",
            tier1_context=self.tier1_context,
            tier2_context=self.tier2_context,
            tier3_context=self.tier3_context,
        )

        # Tier 3 should include plugin instructions
        self.assertIn(
            self.tier3_context["plugin_instructions"],
            prompt,
            "Plugin instructions not found in Tier 3"
        )

    def test_spawn_prompt_is_string(self):
        """Red: Verify spawn prompt is a valid string."""
        prompt = self.builder.build_spawn_prompt(
            plugin_name="agent-tdd",
            tier1_context=self.tier1_context,
            tier2_context=self.tier2_context,
            tier3_context=self.tier3_context,
        )

        # Output should be string
        self.assertIsInstance(prompt, str)
        self.assertGreater(len(prompt), 0)

    def test_spawn_prompt_has_section_separators(self):
        """Red: Verify spawn prompt has clear section separators."""
        prompt = self.builder.build_spawn_prompt(
            plugin_name="agent-tdd",
            tier1_context=self.tier1_context,
            tier2_context=self.tier2_context,
            tier3_context=self.tier3_context,
        )

        # Should have separators between tiers
        self.assertIn("---", prompt)

    def test_plugin_name_in_tier3(self):
        """Red: Verify plugin name is referenced in Tier 3."""
        prompt = self.builder.build_spawn_prompt(
            plugin_name="agent-tdd",
            tier1_context=self.tier1_context,
            tier2_context=self.tier2_context,
            tier3_context=self.tier3_context,
        )

        # Plugin name should be in Tier 3
        self.assertIn("agent-tdd", prompt)

    def test_cache_reuse_annotation(self):
        """Red: Verify spawn prompt includes cache reuse annotation."""
        prompt = self.builder.build_spawn_prompt(
            plugin_name="agent-tdd",
            tier1_context=self.tier1_context,
            tier2_context=self.tier2_context,
            tier3_context=self.tier3_context,
        )

        # Prompt should indicate cache reuse potential
        # Look for tier comments or annotations
        self.assertIn("TIER", prompt, "Tier annotations not found")


class TestCacheOptimizedSpawnPromptHelpers(unittest.TestCase):
    """Tests for helper methods in CacheOptimizedSpawnPrompt."""

    def setUp(self):
        """Set up test fixtures."""
        self.builder = CacheOptimizedSpawnPrompt()

        self.tier1_context = {
            "capability_map": "Plugin Registry Content",
            "nelly_brief": "Brief Content",
            "interop_excerpts": "INTEROP Content",
        }

        self.tier2_context = {
            "requirements_md": "Requirements Content",
            "design_md": "Design Content",
            "research_cache": "Research Content",
            "workflow_state": "Workflow Content",
        }

        self.tier3_context = {
            "slice_spec": "Slice Spec Content",
            "review_findings": "Review Content",
            "plugin_instructions": "Instructions Content",
        }

    def test_render_tier1_returns_string(self):
        """Red: Verify _render_tier1 returns a string."""
        tier1_str = self.builder._render_tier1(self.tier1_context)

        self.assertIsInstance(tier1_str, str)
        self.assertGreater(len(tier1_str), 0)

    def test_render_tier2_returns_string(self):
        """Red: Verify _render_tier2 returns a string."""
        tier2_str = self.builder._render_tier2(self.tier2_context)

        self.assertIsInstance(tier2_str, str)
        self.assertGreater(len(tier2_str), 0)

    def test_render_tier3_returns_string(self):
        """Red: Verify _render_tier3 returns a string."""
        tier3_str = self.builder._render_tier3(
            "agent-tdd",
            self.tier3_context
        )

        self.assertIsInstance(tier3_str, str)
        self.assertGreater(len(tier3_str), 0)


if __name__ == "__main__":
    unittest.main()

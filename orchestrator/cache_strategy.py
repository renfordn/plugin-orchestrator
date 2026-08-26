"""CacheOptimizedSpawnPrompt: Build spawn prompts with tier ordering for cache reuse.

This module implements a three-tier context layout to maximize prompt cache reuse:

Tier 1 (FIRST, ~95% cache hit): Stable across plugins
  - Plugin registry (capability map)
  - INTEROP.md excerpts (handoff contracts)
  - Nelly brief (cached, distributed)

Tier 2 (SECOND, ~70% cache hit): Stable across phases
  - Design Spec: requirements.md, design.md, research_cache
  - Workflow state

Tier 3 (LAST, 0% cache hit): Unique per call
  - Per-call input (slice spec, review findings)
  - Plugin-specific instructions

By placing stable content first, the prompt cache achieves ~95% hit rate on Tier 1+2
content, reducing token cost to ~10% of the full prompt for repeated calls.
"""

from typing import Dict

# Separator between tiers in spawn prompt
TIER_SEPARATOR = "---"


class CacheOptimizedSpawnPrompt:
    """Build spawn prompts in tier order for maximum cache reuse.

    Tier 1+2 (stable across calls) are placed first, achieving ~95% cache hit rate.
    Tier 3 (unique per call) is placed last to avoid cache misses on dynamic content.
    """

    def __init__(self):
        """Initialize spawn prompt builder."""
        pass

    def build_spawn_prompt(
        self,
        plugin_name: str,
        tier1_context: Dict,
        tier2_context: Dict,
        tier3_context: Dict,
    ) -> str:
        """Build spawn prompt in tier order for maximum cache reuse.

        Assembles spawn prompt with:
        - Tier 1 (FIRST): stable content (~95% cache hit)
        - Tier 2 (SECOND): moderately stable (~70% cache hit)
        - Tier 3 (LAST): dynamic per-call content (0% cache hit)

        Args:
            plugin_name: Name of the plugin being spawned (e.g., "agent-tdd")
            tier1_context: Dict with keys: capability_map, nelly_brief, interop_excerpts
            tier2_context: Dict with keys: requirements_md, design_md, research_cache, workflow_state
            tier3_context: Dict with keys: slice_spec, review_findings, plugin_instructions

        Returns:
            Complete spawn prompt string with tiers in order, sections separated by tier separator.
        """
        # Render each tier
        tier1_str = self._render_tier1(tier1_context)
        tier2_str = self._render_tier2(tier2_context)
        tier3_str = self._render_tier3(plugin_name, tier3_context)

        # Assemble tiers in order with separators
        separator = f"\n{TIER_SEPARATOR}\n"
        prompt = separator.join([tier1_str, tier2_str, tier3_str])

        return prompt

    def _render_tier1(self, tier1_context: Dict) -> str:
        """Render Tier 1 context (stable, plugin registry + nelly brief).

        Tier 1 includes:
        - Capability map (plugin registry)
        - INTEROP.md excerpts (handoff contracts)
        - Nelly brief (cached project context)

        Args:
            tier1_context: Dict with capability_map, nelly_brief, interop_excerpts

        Returns:
            Formatted Tier 1 string
        """
        parts = ["# TIER 1: Stable Context (Plugin Registry, Nelly Brief)"]

        if "capability_map" in tier1_context:
            parts.append(f"## Capability Map\n{tier1_context['capability_map']}")

        if "nelly_brief" in tier1_context:
            parts.append(f"## Nelly Brief\n{tier1_context['nelly_brief']}")

        if "interop_excerpts" in tier1_context:
            parts.append(f"## INTEROP Excerpts\n{tier1_context['interop_excerpts']}")

        return "\n\n".join(parts)

    def _render_tier2(self, tier2_context: Dict) -> str:
        """Render Tier 2 context (moderately stable, Design Spec).

        Tier 2 includes:
        - Requirements.md (stable across phases)
        - Design.md (stable across phases)
        - Research cache (findings from design phase)
        - Workflow state (current phase)

        Args:
            tier2_context: Dict with requirements_md, design_md, research_cache, workflow_state

        Returns:
            Formatted Tier 2 string
        """
        parts = ["# TIER 2: Design Spec (Requirements, Design, Research)"]

        if "requirements_md" in tier2_context:
            parts.append(f"## Requirements\n{tier2_context['requirements_md']}")

        if "design_md" in tier2_context:
            parts.append(f"## Design\n{tier2_context['design_md']}")

        if "research_cache" in tier2_context:
            parts.append(f"## Research Cache\n{tier2_context['research_cache']}")

        if "workflow_state" in tier2_context:
            parts.append(f"## Workflow State\n{tier2_context['workflow_state']}")

        return "\n\n".join(parts)

    def _render_tier3(self, plugin_name: str, tier3_context: Dict) -> str:
        """Render Tier 3 context (dynamic, per-call input).

        Tier 3 includes:
        - Slice spec (unique to this call)
        - Review findings (review-specific, changes per review)
        - Plugin-specific instructions (routing, validation rules)

        Args:
            plugin_name: Name of the plugin (for identification in Tier 3)
            tier3_context: Dict with slice_spec, review_findings, plugin_instructions

        Returns:
            Formatted Tier 3 string
        """
        parts = [f"# TIER 3: Per-Call Input for {plugin_name}"]

        if "slice_spec" in tier3_context:
            parts.append(f"## Slice Spec\n{tier3_context['slice_spec']}")

        if "review_findings" in tier3_context:
            parts.append(f"## Review Findings\n{tier3_context['review_findings']}")

        if "plugin_instructions" in tier3_context:
            parts.append(f"## Plugin Instructions\n{tier3_context['plugin_instructions']}")

        return "\n\n".join(parts)

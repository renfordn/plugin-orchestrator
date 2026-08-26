"""PreToolUse hook: Load workflow-state, fetch brief, and inject context before agent spawn.

Implements the before_continue hook that intercepts agent spawn and injects orchestrator
context in three tiers:
1. Tier 1 (stable): Capability map, INTEROP excerpts, nelly brief
2. Tier 2 (derived): Design spec (requirements, design, research_cache)
3. Tier 3 (per-call): Original spawn prompt

Context injection order: Tier 1 → Tier 2 → Tier 3 → Original Prompt

This ensures agents receive stable context first, then derived design context, then
per-call instructions.

Key optimization: Capability map is cached in workflow_state to avoid redundant
INTEROP.md parsing on subsequent agent spawns.
"""

import logging
from typing import Optional, Tuple
from orchestrator.nelly import NellyBriefManager
from orchestrator.interop_parser import CapabilityMap
from orchestrator.checkpoint import CheckpointManager

logger = logging.getLogger(__name__)


def handle_agent_spawn(
    agent_type: str,
    spawn_prompt: str,
    workflow_state: dict
) -> str:
    """
    Inject orchestrator context before agent spawn.

    Loads workflow-state, fetches/caches nelly brief, gets or builds capability map
    (cached to avoid redundant INTEROP parsing), creates checkpoint, and injects
    context in Tier 1 → 2 → 3 order.

    Args:
        agent_type: Name of agent being spawned (e.g., "agent-tdd")
        spawn_prompt: Original spawn prompt from caller
        workflow_state: Current workflow state dict (modified in-place for caching)

    Returns:
        Modified spawn prompt with injected context (original prompt preserved)
    """
    # Step 1: Ensure orchestration structure exists
    _ensure_orchestration_structure(workflow_state)

    # Step 2: Fetch and cache nelly brief (graceful degradation on network failure)
    brief_text, brief_metadata = _fetch_nelly_brief(workflow_state)
    if brief_text:
        workflow_state["orchestration"]["nelly_brief_cache"]["brief_text"] = brief_text
        if brief_metadata:
            workflow_state["orchestration"]["nelly_brief_cache"]["metadata"] = brief_metadata

    # Step 3: Get or build capability map (cached to avoid redundant INTEROP parsing)
    capability_map = _get_or_build_capability_map(workflow_state)

    # Step 4: Create checkpoint before major handoff
    checkpoint_manager = CheckpointManager()
    checkpoint_label = f"before_{agent_type}_spawn"
    checkpoint_manager.create_checkpoint(workflow_state, checkpoint_label)

    # Step 5: Build tiered context and inject into prompt
    tier1_context = _build_tier1_context(capability_map, brief_text)
    tier2_context = _build_tier2_context(workflow_state)
    modified_prompt = f"{tier1_context}\n\n{tier2_context}\n\n{spawn_prompt}"

    return modified_prompt


def _ensure_orchestration_structure(workflow_state: dict) -> None:
    """Ensure workflow_state has required orchestration structure.

    Creates orchestration, nelly_brief_cache, and handoff_history if missing.

    Args:
        workflow_state: Workflow state dict (modified in-place)
    """
    if "orchestration" not in workflow_state:
        workflow_state["orchestration"] = {}

    if "nelly_brief_cache" not in workflow_state["orchestration"]:
        workflow_state["orchestration"]["nelly_brief_cache"] = {}

    if "handoff_history" not in workflow_state["orchestration"]:
        workflow_state["orchestration"]["handoff_history"] = []

    if "checkpoints" not in workflow_state["orchestration"]:
        workflow_state["orchestration"]["checkpoints"] = []


def _fetch_nelly_brief(workflow_state: dict) -> Tuple[Optional[str], dict]:
    """Fetch or retrieve cached nelly brief.

    Attempts to fetch fresh brief via NellyBriefManager. On failure (network error,
    file I/O issue, timeout, etc.), gracefully degrades with fallback to stale cache.

    Args:
        workflow_state: Workflow state dict with orchestration.nelly_brief_cache

    Returns:
        Tuple of (brief_text, metadata_dict):
        - (str, dict): Fresh or cached brief with metadata
        - (None, {}): No brief available (degraded mode)
    """
    try:
        manager = NellyBriefManager()
        # Call fetch_brief with minimal args; mocked in tests
        brief_text, metadata = manager.fetch_brief(
            cwd=".",
            task_description=workflow_state.get("task", "unknown"),
            workflow_state=workflow_state
        )
        if brief_text:
            return brief_text, metadata or {}
        return None, {}
    except (IOError, OSError) as e:
        # File I/O error (file not found, permissions, disk full, etc.)
        logger.warning(
            f"Brief fetch failed: file I/O error: {e.__class__.__name__}. "
            "Continuing without brief."
        )
        return None, {}
    except (TimeoutError, ConnectionError) as e:
        # Network failure (timeout, connection refused, etc.)
        logger.warning(
            f"Brief fetch failed: network error: {e.__class__.__name__}. "
            "Attempting fallback to stale cache."
        )
        return None, {}
    except Exception as e:
        # Any other exception (including NotImplementedError from mocked nelly)
        logger.warning(f"Brief fetch failed: {e}. Continuing without brief.")
        return None, {}


def _get_or_build_capability_map(workflow_state: dict) -> dict:
    """Get cached capability map or build fresh from INTEROP.md files.

    Optimization: checks if capability_map already exists in workflow_state to avoid
    redundant parsing of INTEROP.md files. Builds fresh only if cache is empty.

    Args:
        workflow_state: Workflow state dict with orchestration.capability_map (may be empty)

    Returns:
        Dict representation of capability map (or empty dict on failure)
    """
    # Check if capability map already cached
    existing_map = workflow_state.get("orchestration", {}).get("capability_map")
    if existing_map:
        logger.debug("Using cached capability map (avoiding redundant INTEROP parsing)")
        return existing_map

    # Build fresh capability map from INTEROP.md files
    capability_map = _build_capability_map()
    workflow_state["orchestration"]["capability_map"] = capability_map
    return capability_map


def _build_capability_map() -> dict:
    """Build capability map from INTEROP.md files.

    Parses plugin INTEROP files and builds registry of plugin capabilities and contracts.
    Handles file I/O errors gracefully (missing files, permission issues, etc.).

    Returns:
        Dict representation of capability map:
        {
            "plugin-name": {
                "name": str,
                "handoff_targets": [str],
                "is_soft_dependency": bool,
                "capabilities": [{"id": str, "description": str, "consumes": dict, "produces": dict}]
            },
            ...
        }
        Returns empty dict on failure (graceful degradation).
    """
    try:
        cap_map = CapabilityMap()
        # Convert to serializable dict format for caching in workflow_state
        result = {}
        for plugin_name, plugin_info in cap_map.plugins.items():
            result[plugin_name] = {
                "name": plugin_info.name,
                "handoff_targets": plugin_info.handoff_targets,
                "is_soft_dependency": plugin_info.is_soft_dependency,
                "capabilities": [
                    {
                        "id": cap.id,
                        "description": cap.description,
                        "consumes": cap.consumes,
                        "produces": cap.produces,
                    }
                    for cap in plugin_info.capabilities
                ]
            }
        if result:
            logger.info(f"Built capability map with {len(result)} plugins")
        return result
    except (IOError, OSError) as e:
        # File I/O error (file not found, permissions, disk full, etc.)
        logger.warning(
            f"Failed to build capability map: file I/O error: {e.__class__.__name__}. "
            "Continuing with empty capability map."
        )
        return {}
    except Exception as e:
        # Any other parsing error
        logger.warning(f"Failed to build capability map: {e}. Continuing with empty map.")
        return {}


def _build_tier1_context(capability_map: dict, brief_text: Optional[str]) -> str:
    """Build Tier 1 (stable) context: capability map and nelly brief.

    Tier 1 is the stable, non-changing foundation for agent decisions:
    - Capability map listing all available plugins and their handoff targets
    - Nelly brief providing project context (requirements, patterns, prior art)

    Both are stable for the duration of a workflow run (only invalidated by
    explicit user changes to requirements or INTEROP.md).

    Args:
        capability_map: Dict of capability map (plugin_name → plugin info)
        brief_text: Nelly brief text from agent-nelly, or None if unavailable

    Returns:
        Formatted Tier 1 context string (markdown)
    """
    tier1_parts = ["=== TIER 1: STABLE CONTEXT (Problem Definition & Constraints) ===\n"]

    # Add capability map excerpt (lists available plugins)
    if capability_map:
        tier1_parts.append("## Capability Map\n")
        plugin_list = ", ".join(capability_map.keys())
        tier1_parts.append(f"Available plugins: {plugin_list}\n")

    # Add nelly brief if available (project context, patterns, prior art)
    if brief_text:
        tier1_parts.append("\n## Project Context (from Nelly Brief)\n")
        tier1_parts.append(brief_text)

    return "".join(tier1_parts)


def _build_tier2_context(workflow_state: dict) -> str:
    """Build Tier 2 (derived) context: Design spec (requirements, design, research).

    Tier 2 is derived but stable context produced earlier in the orchestration:
    - Requirements (user stories, acceptance criteria)
    - Design (architecture, file touchpoints, interfaces)
    - Research cache (findings from design phase, file summaries)

    Tier 2 changes only when requirements or design are re-approved upstream.

    Args:
        workflow_state: Workflow state dict with requirements_md, design_md, research_cache

    Returns:
        Formatted Tier 2 context string (markdown)
    """
    tier2_parts = ["=== TIER 2: DESIGN SPECIFICATION (Goals & Implementation Plan) ===\n"]

    # Add requirements (user stories, acceptance criteria)
    if "requirements_md" in workflow_state:
        tier2_parts.append("\n## Requirements\n")
        tier2_parts.append(workflow_state["requirements_md"])

    # Add design (architecture, file touchpoints, interfaces from approved design)
    if "design_md" in workflow_state:
        tier2_parts.append("\n## Design\n")
        tier2_parts.append(workflow_state["design_md"])

    # Add research cache (findings from design phase research)
    if "research_cache" in workflow_state:
        tier2_parts.append("\n## Research Cache\n")
        tier2_parts.append(str(workflow_state["research_cache"]))

    return "".join(tier2_parts)

"""CapabilityMap: Parse INTEROP.md files and build capability registry."""

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class Capability:
    """A capability exposed by a plugin."""
    plugin: str
    id: str
    description: str = ""
    consumes: Dict = field(default_factory=dict)
    produces: Dict = field(default_factory=dict)


@dataclass
class PluginInfo:
    """Information about a plugin."""
    name: str
    handoff_targets: List[str] = field(default_factory=list)
    is_soft_dependency: bool = False
    capabilities: List[Capability] = field(default_factory=list)


class CapabilityMap:
    """Parse INTEROP.md files and build queryable capability registry."""

    PLUGIN_PATHS = {
        "agent-isdd": "agent-isdd/INTEROP.md",
        "agent-tdd": "agent-tdd/INTEROP.md",
        "code-reviewer": "code-reviewer/INTEROP.md",
        "agent-nelly": "agent-nelly/INTEROP.md",
        "agent-ux": "agent-ux/INTEROP.md",
        "agent-cache-plugin": "agent-cache-plugin/STRUCTURE.md",
    }

    def __init__(self, plugin_dir_base: Optional[str] = None):
        """
        Parse INTEROP.md files and build capability registry.

        Args:
            plugin_dir_base: Base directory containing all plugin folders.
                            Defaults to environment variable CLAUDE_PLUGINS_DIR if set,
                            otherwise ~/.claude/plugins/claude-plugins (the standard
                            bootstrap location), falling back to test fixtures only
                            when neither exists.
        """
        if plugin_dir_base is None:
            env_dir = os.environ.get("CLAUDE_PLUGINS_DIR")
            if env_dir:
                plugin_dir_base = Path(os.path.expanduser(os.path.expandvars(env_dir)))
            else:
                default_dir = Path.home() / ".claude" / "plugins" / "claude-plugins"
                if default_dir.exists():
                    plugin_dir_base = default_dir
                else:
                    plugin_dir_base = Path(__file__).parent.parent / "tests" / "fixtures"

        self.plugin_dir_base = Path(plugin_dir_base)
        self.plugins: Dict[str, PluginInfo] = {}
        self.interop_hashes: Dict[str, str] = {}

        self._parse_all_plugins()

    def _parse_all_plugins(self) -> None:
        """Parse all INTEROP.md files and build registry.

        Implements graceful degradation: if a plugin's INTEROP file is missing or
        cannot be parsed, creates an empty PluginInfo entry instead of failing.
        This allows the orchestrator to:
        - Continue operating when some plugins are unavailable
        - Detect plugins as they become available later
        - Log missing plugins without blocking workflow

        Each plugin gets an MD5 hash of its INTEROP content for change detection.
        """
        for plugin_name, rel_path in self.PLUGIN_PATHS.items():
            plugin_info = self._load_plugin(plugin_name, rel_path)
            self.plugins[plugin_name] = plugin_info

    def _load_plugin(self, plugin_name: str, rel_path: str) -> PluginInfo:
        """
        Load a single plugin's INTEROP file and create PluginInfo.

        Implements graceful degradation: if a plugin's INTEROP file is missing or
        cannot be parsed, logs a debug message and returns an empty PluginInfo entry.
        This allows the orchestrator to continue operating even if some plugins are
        unavailable or misconfigured.

        Args:
            plugin_name: Name of the plugin
            rel_path: Relative path to INTEROP/STRUCTURE file

        Returns:
            PluginInfo object (empty if file not found or parsing fails)
        """
        interop_path = self.plugin_dir_base / rel_path

        try:
            if interop_path.exists():
                content = interop_path.read_text(encoding='utf-8')
                hash_val = hashlib.md5(content.encode()).hexdigest()
                self.interop_hashes[plugin_name] = hash_val
                return self._parse_plugin_file(plugin_name, content)
        except Exception as e:
            logger.debug(
                f"Failed to load {plugin_name} INTEROP file from {interop_path}: {e}. "
                f"Creating empty plugin entry for graceful degradation."
            )

        # Fallback: create empty plugin entry for graceful degradation
        self.interop_hashes[plugin_name] = ""
        return PluginInfo(name=plugin_name)

    def _parse_plugin_file(self, plugin_name: str, content: str) -> PluginInfo:
        """
        Parse INTEROP.md content and extract capabilities.

        Orchestrates extraction of handoff targets, soft dependency flags,
        and plugin-specific capabilities.
        """
        plugin_info = PluginInfo(name=plugin_name)

        # Extract handoff targets (e.g., "## → agent-tdd")
        plugin_info.handoff_targets = self._extract_handoff_targets(content)

        # Check if this plugin is optional/soft
        plugin_info.is_soft_dependency = self._is_soft_dependency(plugin_name, content)

        # Extract capabilities based on plugin type
        plugin_info.capabilities = self._extract_capabilities(plugin_name, content)

        return plugin_info

    def _extract_handoff_targets(self, content: str) -> List[str]:
        """
        Extract handoff targets from INTEROP.md.

        Looks for "## → plugin-name" sections indicating handoffs to other plugins.

        Args:
            content: INTEROP.md file content

        Returns:
            List of plugin names this plugin hands off to
        """
        handoff_pattern = r'## → ([a-z\-]+)'
        handoff_targets = re.findall(handoff_pattern, content)
        return list(set(handoff_targets))  # Deduplicate

    def _is_soft_dependency(self, plugin_name: str, content: str) -> bool:
        """
        Determine if plugin is optional (soft dependency).

        Args:
            plugin_name: Name of the plugin
            content: INTEROP.md file content

        Returns:
            True if plugin is optional
        """
        # agent-nelly is documented as soft dependency
        if plugin_name == "agent-nelly":
            return "soft dependency" in content.lower()
        return False

    def _extract_capabilities(self, plugin_name: str, content: str) -> List[Capability]:
        """
        Extract capabilities from INTEROP.md content.

        Each plugin has hardcoded capability definitions based on its role.

        Args:
            plugin_name: Name of the plugin
            content: INTEROP.md file content

        Returns:
            List of Capability objects
        """
        capabilities = []

        if plugin_name == "agent-isdd":
            if "Design Spec" in content:
                capabilities.append(Capability(
                    plugin=plugin_name,
                    id="design_spec_handoff",
                    description="Hand off design spec to implementation agent"
                ))

        elif plugin_name == "agent-tdd":
            if "Design Spec" in content or "Slice Spec" in content:
                capabilities.append(Capability(
                    plugin=plugin_name,
                    id="design_spec_slicing",
                    description="Slice design into TDD-ready phases",
                    consumes={
                        "requirements_md": "string",
                        "design_md": "string",
                        "research_cache": "object",
                        "recap_md": "string"
                    }
                ))

        elif plugin_name == "agent-nelly":
            capabilities.append(Capability(
                plugin=plugin_name,
                id="memory_brief",
                description="Retrieve project memory and error lessons"
            ))

        elif plugin_name == "agent-ux":
            capabilities.append(Capability(
                plugin=plugin_name,
                id="render_event",
                description="Render progress UI events"
            ))

        return capabilities

    def get_plugin(self, plugin_name: str) -> Optional[PluginInfo]:
        """
        Fetch plugin by name; returns PluginInfo or None if unavailable.

        Args:
            plugin_name: Name of the plugin (e.g., "agent-isdd")

        Returns:
            PluginInfo or None
        """
        return self.plugins.get(plugin_name)

    def find_capability(self, plugin_name: str, capability_id: str) -> Optional[Capability]:
        """
        Find specific capability by plugin name and capability ID.

        Args:
            plugin_name: Name of the plugin
            capability_id: ID of the capability (e.g., "design_spec_handoff")

        Returns:
            Capability or None
        """
        plugin = self.plugins.get(plugin_name)
        if not plugin:
            return None

        for cap in plugin.capabilities:
            if cap.id == capability_id:
                return cap

        return None

    def route_to_next_plugin(self, source_plugin: str, output: dict) -> Optional[str]:
        """
        Given source plugin output, find next capable plugin.

        Args:
            source_plugin: Name of the plugin producing output
            output: Output data from source plugin

        Returns:
            Next plugin name or None if end of chain
        """
        source = self.plugins.get(source_plugin)
        if not source:
            return None

        # Route based on source plugin's handoff targets
        # agent-isdd with design_spec output -> agent-tdd
        if source_plugin == "agent-isdd" and output.get("type") == "design_spec":
            if "agent-tdd" in source.handoff_targets:
                return "agent-tdd"

        # Return first available handoff target
        if source.handoff_targets:
            return source.handoff_targets[0]

        return None

    def validate_input(
        self,
        plugin_name: str,
        capability_id: str,
        input_shape: dict
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate input matches capability's consumes contract.

        Args:
            plugin_name: Name of the plugin
            capability_id: ID of the capability
            input_shape: Input data to validate

        Returns:
            Tuple of (is_valid, error_reason)
        """
        capability = self.find_capability(plugin_name, capability_id)
        if not capability:
            return False, f"Capability '{capability_id}' not found in {plugin_name}"

        # If no consumes contract defined, accept any input
        if not capability.consumes:
            return True, None

        # Validate required fields from consumes contract
        for field_name in capability.consumes:
            if field_name not in input_shape:
                return False, f"Missing required field: {field_name}"

        return True, None

    def is_soft_dependency(self, plugin_name: str) -> bool:
        """
        Check if plugin is optional (soft dependency).

        Args:
            plugin_name: Name of the plugin

        Returns:
            True if plugin is optional, False if required
        """
        plugin = self.plugins.get(plugin_name)
        if not plugin:
            return False

        return plugin.is_soft_dependency

    def refresh(self) -> List[str]:
        """
        Re-parse INTEROP files whose content changed on disk, in place.

        Compares each plugin's current MD5 hash against a freshly computed one
        and only re-loads plugins that actually changed, so unaffected plugins
        keep their existing PluginInfo objects. Enables picking up plugin
        capability changes without recreating CapabilityMap (session restart).

        Returns:
            List of plugin names whose INTEROP file changed and were reloaded.
        """
        changed_plugins = []

        for plugin_name, rel_path in self.PLUGIN_PATHS.items():
            previous_hash = self.interop_hashes.get(plugin_name, "")
            plugin_info = self._load_plugin(plugin_name, rel_path)

            if self.interop_hashes.get(plugin_name, "") != previous_hash:
                self.plugins[plugin_name] = plugin_info
                changed_plugins.append(plugin_name)

        return changed_plugins

    def get_interop_hashes(self) -> Dict[str, str]:
        """
        Get current INTEROP file hashes.

        Returns:
            Dict mapping plugin names to file hashes
        """
        return dict(self.interop_hashes)

    def invalidate_on_interop_change(self, current_hashes: dict) -> bool:
        """
        Check if any INTEROP.md file has changed.

        Args:
            current_hashes: Previous hashes to compare against

        Returns:
            True if cache is invalid (hashes changed)
        """
        if not current_hashes:
            return True

        # Check if any hash has changed
        for plugin_name, stored_hash in current_hashes.items():
            current_hash = self.interop_hashes.get(plugin_name)
            if current_hash != stored_hash:
                return True

        return False

    @staticmethod
    def get_cached_map(
        workflow_state_path: str,
        plugin_dir_base: Optional[str] = None
    ) -> Optional['CapabilityMap']:
        """
        Fetch cached map from workflow-state.json if INTEROP hashes unchanged.

        Args:
            workflow_state_path: Path to workflow-state.json file
            plugin_dir_base: Base directory the cached map was built from. Must
                match the directory passed to the original CapabilityMap(), or
                hash comparison will always report a change. Defaults the same
                way CapabilityMap.__init__ does (CLAUDE_PLUGINS_DIR, else fixtures).

        Returns:
            CapabilityMap or None if cache invalid or not found
        """
        workflow_state_file = Path(workflow_state_path)
        if not workflow_state_file.exists():
            return None

        try:
            with open(workflow_state_file, 'r') as f:
                state = json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

        if "capability_map" not in state or "interop_hashes" not in state:
            return None

        # Create new map to check if hashes still match
        current_map = CapabilityMap(plugin_dir_base)
        cached_hashes = state.get("interop_hashes", {})

        # If hashes unchanged, use cached data
        if not current_map.invalidate_on_interop_change(cached_hashes):
            return CapabilityMap._reconstruct_from_cache(
                state.get("capability_map", {}),
                cached_hashes
            )

        return None

    @staticmethod
    def _reconstruct_from_cache(
        capability_map_data: dict,
        interop_hashes: dict
    ) -> 'CapabilityMap':
        """
        Reconstruct CapabilityMap from cached JSON data.

        Args:
            capability_map_data: Serialized plugin capability data
            interop_hashes: Serialized INTEROP file hashes

        Returns:
            CapabilityMap instance with cached data
        """
        cached_map = CapabilityMap.__new__(CapabilityMap)
        cached_map.plugin_dir_base = Path(
            "/Users/jay.nelson/Codebase/AI/plugins/claude"
        )
        cached_map.interop_hashes = interop_hashes

        # Deserialize plugins dict
        cached_map.plugins = {}
        for plugin_name, plugin_dict in capability_map_data.items():
            # Extract capabilities data (don't mutate original dict)
            capabilities_data = plugin_dict.get("capabilities", [])

            # Create PluginInfo with plugin metadata
            plugin_info = PluginInfo(
                name=plugin_dict.get("name", plugin_name),
                handoff_targets=plugin_dict.get("handoff_targets", []),
                is_soft_dependency=plugin_dict.get("is_soft_dependency", False),
                capabilities=[]
            )

            # Reconstruct Capability objects
            plugin_info.capabilities = [
                Capability(**cap_data)
                for cap_data in capabilities_data
            ]

            cached_map.plugins[plugin_name] = plugin_info

        return cached_map

        return None

    def save_to_cache(self, workflow_state_path: str) -> None:
        """
        Cache this map + INTEROP hashes in workflow-state.json.

        Args:
            workflow_state_path: Path to workflow-state.json file
        """
        workflow_state_file = Path(workflow_state_path)

        # Read existing state if present
        if workflow_state_file.exists():
            try:
                with open(workflow_state_file, 'r') as f:
                    state = json.load(f)
            except (json.JSONDecodeError, IOError):
                state = {}
        else:
            state = {}

        # Serialize plugins dict
        serialized_plugins = {}
        for plugin_name, plugin_info in self.plugins.items():
            plugin_dict = {
                "name": plugin_info.name,
                "handoff_targets": plugin_info.handoff_targets,
                "is_soft_dependency": plugin_info.is_soft_dependency,
                "capabilities": [
                    {
                        "plugin": cap.plugin,
                        "id": cap.id,
                        "description": cap.description,
                        "consumes": cap.consumes,
                        "produces": cap.produces,
                    }
                    for cap in plugin_info.capabilities
                ]
            }
            serialized_plugins[plugin_name] = plugin_dict

        # Update state
        state["capability_map"] = serialized_plugins
        state["interop_hashes"] = self.interop_hashes

        # Write back
        workflow_state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(workflow_state_file, 'w') as f:
            json.dump(state, f, indent=2)

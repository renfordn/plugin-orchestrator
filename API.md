# Plugin Orchestrator API Reference

## Overview

The plugin-orchestrator provides a type-safe, high-performance routing and handoff system for multi-agent workflows. The API consists of two main components:

1. **CapabilityMap** - Parses plugin capabilities from INTEROP.md files and maintains a queryable registry
2. **PluginRouter** - Routes between plugins based on capabilities and orchestrates handoffs with contract validation

## CapabilityMap API

### Initialization

```python
from orchestrator.interop_parser import CapabilityMap

# Load capabilities from plugin directory
cap_map = CapabilityMap("./plugins")

# Default: loads from tests/fixtures
cap_map = CapabilityMap()
```

### Core Methods

#### `get_plugin(plugin_name: str) -> Optional[PluginInfo]`

Fetch plugin metadata by name.

**Parameters:**
- `plugin_name` (str): Plugin identifier (e.g., "agent-isdd")

**Returns:**
- `PluginInfo`: Plugin metadata with capabilities and handoff targets, or None

**Example:**
```python
plugin = cap_map.get_plugin("agent-isdd")
if plugin:
    print(f"Capabilities: {plugin.capabilities}")
    print(f"Handoff targets: {plugin.handoff_targets}")
```

---

#### `find_capability(plugin_name: str, capability_id: str) -> Optional[Capability]`

Find a specific capability by plugin and capability ID.

**Parameters:**
- `plugin_name` (str): Plugin identifier
- `capability_id` (str): Capability identifier (e.g., "design_spec_handoff")

**Returns:**
- `Capability`: Capability object with type contracts, or None

**Example:**
```python
cap = cap_map.find_capability("agent-tdd", "design_spec_slicing")
if cap:
    print(f"Consumes: {cap.consumes}")
    print(f"Produces: {cap.produces}")
```

---

#### `validate_input(plugin_name: str, capability_id: str, input_shape: dict) -> Tuple[bool, Optional[str]]`

Validate input data against a capability's consumes contract.

**Parameters:**
- `plugin_name` (str): Target plugin
- `capability_id` (str): Target capability
- `input_shape` (dict): Input data to validate

**Returns:**
- `(bool, Optional[str])`: (is_valid, error_message)

**Example:**
```python
input_data = {
    "requirements_md": "# Requirements",
    "design_md": "# Design"
}
is_valid, error = cap_map.validate_input("agent-tdd", "design_spec_slicing", input_data)
if not is_valid:
    print(f"Validation failed: {error}")
```

---

#### `is_soft_dependency(plugin_name: str) -> bool`

Check if a plugin is optional (soft dependency).

**Parameters:**
- `plugin_name` (str): Plugin identifier

**Returns:**
- `bool`: True if plugin is optional, False if required

**Example:**
```python
if cap_map.is_soft_dependency("agent-nelly"):
    print("agent-nelly is optional - workflow continues if unavailable")
```

---

#### `get_interop_hashes() -> Dict[str, str]`

Get MD5 hashes of all INTEROP.md files for change detection.

**Returns:**
- `Dict[str, str]`: Mapping of plugin names to content hashes

**Example:**
```python
hashes = cap_map.get_interop_hashes()
# Use for cache invalidation when capabilities change
```

---

#### `save_to_cache(workflow_state_path: str) -> None`

Cache capability map to workflow-state.json for faster reloads.

**Parameters:**
- `workflow_state_path` (str): Path to workflow-state.json file

**Example:**
```python
cap_map.save_to_cache("./workflow-state.json")
```

---

#### `get_cached_map(workflow_state_path: str) -> Optional[CapabilityMap]` (static)

Load capability map from cache if INTEROP hashes unchanged.

**Parameters:**
- `workflow_state_path` (str): Path to workflow-state.json file

**Returns:**
- `CapabilityMap` or None if cache invalid

**Example:**
```python
cached_map = CapabilityMap.get_cached_map("./workflow-state.json")
if cached_map:
    cap_map = cached_map  # Use cached version
else:
    cap_map = CapabilityMap()  # Rebuild
```

---

## PluginRouter API

### Initialization

```python
from orchestrator.core import PluginRouter
from orchestrator.interop_parser import CapabilityMap

cap_map = CapabilityMap()
router = PluginRouter(cap_map)
```

### Core Methods

#### `check_plugin_availability(plugin_name: str, system_reminder: str) -> bool`

Check if a plugin is available based on system_reminder.

**Parameters:**
- `plugin_name` (str): Plugin identifier (supports "agent-" prefix normalization)
- `system_reminder` (str): System context string with plugin availability info

**Returns:**
- `bool`: True if plugin is available

**Raises:**
- `ValueError`: If plugin_name or system_reminder is None/empty

**Example:**
```python
system_reminder = "agent-isdd:spec available agent-tdd:tdd available"

if router.check_plugin_availability("agent-tdd", system_reminder):
    print("agent-tdd is ready")

# Short names auto-prepend "agent-" prefix
if router.check_plugin_availability("tdd", system_reminder):
    print("agent-tdd is ready (short name)")
```

---

#### `validate_handoff(source_plugin: str, source_capability: str, target_plugin: str, target_capability: str, payload: dict) -> Tuple[bool, Optional[str]]`

Validate a handoff between two plugins with contract checking.

**Parameters:**
- `source_plugin` (str): Source plugin name
- `source_capability` (str): Source capability that produces the handoff
- `target_plugin` (str): Target plugin name
- `target_capability` (str): Target capability that consumes the handoff
- `payload` (dict): Data being handed off

**Returns:**
- `(bool, Optional[str])`: (is_valid, error_message)

**Raises:**
- `TypeError`: If payload is not a dict or is None

**Example:**
```python
payload = {
    "requirements_md": "# Requirements",
    "design_md": "# Design",
    "research_cache": {},
    "recap_md": "# Recap"
}

is_valid, error = router.validate_handoff(
    "agent-isdd", "design_spec_handoff",
    "agent-tdd", "design_spec_slicing",
    payload
)

if not is_valid:
    print(f"Handoff validation failed: {error}")
```

---

#### `route_to_next_plugin(current_plugin: str, current_phase: str, handoff_valid: bool) -> Optional[str]`

Determine the next plugin in the workflow based on current state.

**Parameters:**
- `current_plugin` (str): Current plugin name
- `current_phase` (str): Current workflow phase (e.g., "design_approved")
- `handoff_valid` (bool): Whether handoff validation passed

**Returns:**
- `str` or None: Next plugin name, or None if workflow is complete

**Example:**
```python
next_plugin = router.route_to_next_plugin("agent-isdd", "design_approved", True)

if next_plugin:
    print(f"Route to: {next_plugin}")
else:
    print("Workflow complete")
```

---

#### `is_hard_dependency(plugin_name: str) -> bool`

Check if a plugin is a required hard dependency.

**Parameters:**
- `plugin_name` (str): Plugin identifier

**Returns:**
- `bool`: True if plugin is required

**Example:**
```python
if router.is_hard_dependency("agent-tdd"):
    print("agent-tdd is required - workflow blocks if unavailable")
```

---

#### `is_soft_dependency(plugin_name: str) -> bool`

Check if a plugin is optional (soft dependency).

**Parameters:**
- `plugin_name` (str): Plugin identifier

**Returns:**
- `bool`: True if plugin is optional

**Example:**
```python
if router.is_soft_dependency("agent-nelly"):
    print("agent-nelly is optional - workflow continues if unavailable")
```

---

## Data Classes

### PluginInfo

Metadata about a plugin.

**Fields:**
- `name` (str): Plugin identifier
- `handoff_targets` (List[str]): Plugins this plugin can hand off to
- `is_soft_dependency` (bool): Whether plugin is optional
- `capabilities` (List[Capability]): Exposed capabilities

---

### Capability

A capability exposed by a plugin.

**Fields:**
- `plugin` (str): Plugin that exposes this capability
- `id` (str): Capability identifier (e.g., "design_spec_handoff")
- `description` (str): Human-readable description
- `consumes` (Dict): Input type contract
- `produces` (Dict): Output type contract

**Example:**
```python
cap = Capability(
    plugin="agent-tdd",
    id="design_spec_slicing",
    description="Slice design into TDD-ready phases",
    consumes={
        "requirements_md": "string",
        "design_md": "string",
        "research_cache": "object"
    }
)
```

---

## Error Handling

### Common Errors

| Error Type | Cause | Handling |
|-----------|-------|----------|
| `ValueError` | Empty/None plugin name or system reminder | Validate inputs before calling router |
| `TypeError` | Non-dict payload passed to validate_handoff | Ensure payload is always a dict |
| Validation failure | Capability not found or contract mismatch | Check capability exists and payload matches contract |

### Example Error Handling

```python
try:
    is_valid, error = router.validate_handoff(
        "agent-isdd", "design_spec_handoff",
        "agent-tdd", "design_spec_slicing",
        payload
    )
    if not is_valid:
        logger.error(f"Handoff validation failed: {error}")
        # Handle validation failure gracefully
except TypeError as e:
    logger.error(f"Invalid payload type: {e}")
    # Payload is not a dict
except ValueError as e:
    logger.error(f"Invalid input: {e}")
    # Plugin name or system reminder is empty/None
```

---

## Performance Characteristics

All operations meet strict SLAs for sub-millisecond latency:

| Operation | Typical Latency | SLA | Notes |
|-----------|-----------------|-----|-------|
| Initialization | 0.34ms | <30ms | One-time cost, negligible |
| Plugin availability check | <0.001ms | <0.1ms | String pattern matching, instant |
| Handoff validation | 0.001ms | <0.5ms | Field presence checking only |
| Routing decision | <0.001ms | <0.1ms | O(1) lookup, phase-based routing |
| Complete chain (3 handoffs) | <0.01ms | <100ms | Sub-millisecond end-to-end |

**Payload size:** Validation performs field presence checks only. Payload content is NOT scanned or serialized. Scales to arbitrarily large payloads (tested up to 500x baseline) without performance penalty.

---

## Best Practices

1. **Reuse CapabilityMap**: Create once per session, reuse for all routing decisions
2. **Cache when possible**: Use `save_to_cache()` and `get_cached_map()` for faster startup
3. **Validate early**: Call `validate_input()` before actual plugin execution
4. **Log handoffs**: Track all handoffs with timestamps for observability
5. **Handle soft dependencies**: Design workflows that degrade gracefully when soft dependencies are unavailable
6. **Monitor SLAs**: Track latency percentiles (P50, P95, P99) in production

---

## See Also

- [Architecture Documentation](./ARCHITECTURE.md)
- [Integration Tests](./tests/test_integration_agent_stubs.py)
- [Performance Profiling](./PERFORMANCE.md)

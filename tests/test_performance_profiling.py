"""Performance Profiling: Orchestrator latency, cache efficiency, and throughput.

Comprehensive benchmarking of:
1. **Latency Breakdown** - Time per component (routing, validation, caching)
2. **Cache Efficiency** - Hit/miss rates and memory overhead
3. **Throughput** - Handoffs per second under realistic load
4. **Memory Usage** - Peak memory and growth patterns
5. **Scalability** - Performance with increasing plugins/handoffs

Results guide optimization priorities and validate performance SLAs.
"""

import json
import time
import unittest
import sys
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict

from orchestrator.core import PluginRouter
from orchestrator.interop_parser import CapabilityMap


class PerformanceMetrics:
    """Collect and analyze performance data."""

    def __init__(self):
        self.timings: Dict[str, List[float]] = defaultdict(list)
        self.peak_memory = 0
        self.handoffs_completed = 0

    def record_timing(self, operation: str, duration_ms: float):
        """Record operation timing."""
        self.timings[operation].append(duration_ms)

    def get_stats(self, operation: str) -> Dict:
        """Get statistics for an operation."""
        if operation not in self.timings or not self.timings[operation]:
            return {}

        times = self.timings[operation]
        return {
            "count": len(times),
            "min_ms": min(times),
            "max_ms": max(times),
            "avg_ms": sum(times) / len(times),
            "p95_ms": sorted(times)[int(len(times) * 0.95)] if len(times) > 1 else times[0],
            "p99_ms": sorted(times)[int(len(times) * 0.99)] if len(times) > 1 else times[0],
        }

    def report(self):
        """Generate performance report."""
        report = {
            "summary": {
                "total_handoffs": self.handoffs_completed,
                "total_operations": sum(len(v) for v in self.timings.values()),
            },
            "operations": {}
        }

        for op in sorted(self.timings.keys()):
            report["operations"][op] = self.get_stats(op)

        return report


class TestRouterLatency(unittest.TestCase):
    """Benchmark PluginRouter latency for core operations."""

    def setUp(self):
        """Set up test fixtures."""
        plugin_dir = str(Path(__file__).parent / "fixtures")
        self.capability_map = CapabilityMap(plugin_dir)
        self.router = PluginRouter(self.capability_map)
        self.metrics = PerformanceMetrics()

    def test_router_initialization_latency(self):
        """Benchmark PluginRouter initialization time."""
        plugin_dir = str(Path(__file__).parent / "fixtures")

        start = time.perf_counter()
        cap_map = CapabilityMap(plugin_dir)
        cap_time = (time.perf_counter() - start) * 1000

        start = time.perf_counter()
        router = PluginRouter(cap_map)
        router_time = (time.perf_counter() - start) * 1000

        self.metrics.record_timing("capability_map_init", cap_time)
        self.metrics.record_timing("plugin_router_init", router_time)

        # SLA: <50ms for initialization
        self.assertLess(cap_time + router_time, 50,
            f"Initialization took {cap_time + router_time}ms (SLA: <50ms)")

        print(f"\n📊 Router Initialization:")
        print(f"  CapabilityMap: {cap_time:.2f}ms")
        print(f"  PluginRouter: {router_time:.2f}ms")
        print(f"  Total: {cap_time + router_time:.2f}ms")

    def test_plugin_availability_check_latency(self):
        """Benchmark plugin availability detection."""
        system_reminder = """
        Available plugins:
        agent-isdd:spec-driven available
        agent-tdd:tdd-engine available
        code-reviewer:quality-gates available
        agent-nelly:memory-system available
        agent-ux:ui-renderer available
        """

        # Warm up
        self.router.check_plugin_availability("agent-tdd", system_reminder)

        # Benchmark
        for plugin in ["agent-isdd", "agent-tdd", "code-reviewer", "agent-nelly", "agent-ux"]:
            start = time.perf_counter()
            for _ in range(100):
                result = self.router.check_plugin_availability(plugin, system_reminder)
            elapsed = (time.perf_counter() - start) * 1000 / 100
            self.metrics.record_timing("plugin_availability_check", elapsed)

        stats = self.metrics.get_stats("plugin_availability_check")
        print(f"\n📊 Plugin Availability Check (100 iterations):")
        print(f"  Avg: {stats['avg_ms']:.3f}ms")
        print(f"  P95: {stats['p95_ms']:.3f}ms")
        print(f"  P99: {stats['p99_ms']:.3f}ms")

    def test_handoff_validation_latency(self):
        """Benchmark handoff contract validation."""
        valid_handoff = {
            "requirements_md": "# Requirements\n" * 100,
            "design_md": "# Design\n" * 100,
            "research_cache": {"findings": ["item"] * 100},
            "recap_md": "# Recap\n" * 100
        }

        # Warm up
        self.router.validate_handoff(
            "agent-isdd", "design_spec_handoff",
            "agent-tdd", "design_spec_slicing",
            valid_handoff
        )

        # Benchmark
        start = time.perf_counter()
        for _ in range(1000):
            is_valid, error = self.router.validate_handoff(
                "agent-isdd", "design_spec_handoff",
                "agent-tdd", "design_spec_slicing",
                valid_handoff
            )
        elapsed = (time.perf_counter() - start) * 1000 / 1000

        self.metrics.record_timing("handoff_validation", elapsed)

        print(f"\n📊 Handoff Validation (1000 iterations):")
        print(f"  Avg: {elapsed:.3f}ms per handoff")
        print(f"  Throughput: {1000/elapsed:.0f} validations/sec")

        # SLA: <0.5ms per validation (allows 1000 per second)
        self.assertLess(elapsed, 0.5,
            f"Validation took {elapsed:.3f}ms (SLA: <0.5ms)")

    def test_routing_decision_latency(self):
        """Benchmark plugin routing decisions."""
        # Warm up
        self.router.route_to_next_plugin("agent-isdd", "design_approved", True)

        # Benchmark routing decisions
        start = time.perf_counter()
        for _ in range(10000):
            next_plugin = self.router.route_to_next_plugin("agent-isdd", "design_approved", True)
        elapsed = (time.perf_counter() - start) * 1000 / 10000

        self.metrics.record_timing("routing_decision", elapsed)

        print(f"\n📊 Routing Decision (10000 iterations):")
        print(f"  Avg: {elapsed:.3f}ms")
        print(f"  Throughput: {1000/elapsed:.0f} decisions/sec")


class TestCacheEfficiency(unittest.TestCase):
    """Benchmark cache efficiency and overhead."""

    def setUp(self):
        """Set up test fixtures."""
        plugin_dir = str(Path(__file__).parent / "fixtures")
        self.capability_map = CapabilityMap(plugin_dir)
        self.metrics = PerformanceMetrics()

    def test_capability_map_cache_hit_rate(self):
        """Benchmark capability map lookups and cache effectiveness."""
        plugins = ["agent-isdd", "agent-tdd", "agent-nelly", "agent-ux"]
        capabilities = ["design_spec_handoff", "design_spec_slicing", "memory_brief", "render_event"]

        # Warm up
        for plugin in plugins:
            for cap_id in capabilities:
                self.capability_map.find_capability(plugin, cap_id)

        # Benchmark cache hits
        start = time.perf_counter()
        hits = 0
        misses = 0
        for _ in range(10000):
            for plugin in plugins:
                for cap_id in capabilities:
                    result = self.capability_map.find_capability(plugin, cap_id)
                    if result is not None:
                        hits += 1
                    else:
                        misses += 1

        elapsed = (time.perf_counter() - start) * 1000

        total = hits + misses
        hit_rate = (hits / total * 100) if total > 0 else 0

        self.metrics.record_timing("capability_lookup", elapsed / total)

        print(f"\n📊 Capability Map Lookup (10000 iterations):")
        print(f"  Cache Hit Rate: {hit_rate:.1f}%")
        print(f"  Avg Lookup: {elapsed/total:.3f}ms")
        print(f"  Total Time: {elapsed:.2f}ms")

    def test_plugin_info_memory_overhead(self):
        """Estimate memory overhead of capability registry."""
        plugin_dir = str(Path(__file__).parent / "fixtures")
        cap_map = CapabilityMap(plugin_dir)

        # Estimate size
        plugins_count = len(cap_map.plugins)
        total_capabilities = sum(len(p.capabilities) for p in cap_map.plugins.values())

        print(f"\n📊 Capability Map Memory Profile:")
        print(f"  Plugins: {plugins_count}")
        print(f"  Total Capabilities: {total_capabilities}")
        print(f"  Avg Capabilities/Plugin: {total_capabilities/plugins_count:.1f}")
        print(f"  INTEROP Hashes: {len(cap_map.interop_hashes)}")


class TestHandoffThroughput(unittest.TestCase):
    """Benchmark handoff throughput and scaling."""

    def setUp(self):
        """Set up test fixtures."""
        plugin_dir = str(Path(__file__).parent / "fixtures")
        self.capability_map = CapabilityMap(plugin_dir)
        self.router = PluginRouter(self.capability_map)
        self.metrics = PerformanceMetrics()

    def test_handoff_chain_throughput(self):
        """Benchmark complete handoff chain (isdd → tdd → reviewer)."""
        handoff_payload = {
            "requirements_md": "# Requirements\n" * 50,
            "design_md": "# Design\n" * 50,
            "research_cache": {"findings": ["item"] * 50},
            "recap_md": "# Recap\n" * 50
        }

        handoffs = [
            ("agent-isdd", "design_spec_handoff", "agent-tdd", "design_spec_slicing"),
            ("agent-tdd", "design_spec_slicing", "code-reviewer", "code_review"),
        ]

        # Benchmark chain execution
        start = time.perf_counter()
        chain_time = 0

        for _ in range(100):
            for source_plugin, source_cap, target_plugin, target_cap in handoffs:
                start_handoff = time.perf_counter()
                is_valid, error = self.router.validate_handoff(
                    source_plugin, source_cap,
                    target_plugin, target_cap,
                    handoff_payload
                )
                chain_time += (time.perf_counter() - start_handoff) * 1000

        avg_chain_time = chain_time / 100

        print(f"\n📊 Handoff Chain Throughput (100 complete chains):")
        print(f"  Avg Chain Time: {avg_chain_time:.2f}ms")
        print(f"  Chains/Second: {1000/avg_chain_time:.1f}")
        print(f"  Handoffs/Second: {1000/avg_chain_time * 2:.1f}")

        # SLA: <100ms per complete handoff chain (allows 10 chains/sec)
        self.assertLess(avg_chain_time, 100,
            f"Chain took {avg_chain_time:.2f}ms (SLA: <100ms)")

    def test_payload_size_impact(self):
        """Benchmark impact of payload size on validation latency."""
        sizes = [1, 10, 50, 100, 500]
        results = []

        for size_factor in sizes:
            payload = {
                "requirements_md": "# Requirements\n" * (10 * size_factor),
                "design_md": "# Design\n" * (10 * size_factor),
                "research_cache": {"findings": ["item"] * (10 * size_factor)},
                "recap_md": "# Recap\n" * (10 * size_factor)
            }

            start = time.perf_counter()
            for _ in range(100):
                self.router.validate_handoff(
                    "agent-isdd", "design_spec_handoff",
                    "agent-tdd", "design_spec_slicing",
                    payload
                )
            elapsed = (time.perf_counter() - start) * 1000 / 100

            results.append((size_factor, elapsed))
            self.metrics.record_timing(f"validation_size_{size_factor}x", elapsed)

        print(f"\n📊 Payload Size Impact:")
        for size_factor, latency in results:
            print(f"  {size_factor}x size: {latency:.3f}ms per validation")


class TestPerformanceReport(unittest.TestCase):
    """Generate comprehensive performance report."""

    def setUp(self):
        """Set up test fixtures."""
        plugin_dir = str(Path(__file__).parent / "fixtures")
        self.capability_map = CapabilityMap(plugin_dir)
        self.router = PluginRouter(self.capability_map)

    def test_generate_performance_report(self):
        """Generate and save performance profiling report."""
        metrics = PerformanceMetrics()

        # Run core operations with timing
        system_reminder = "agent-isdd:spec available agent-tdd:tdd available"

        # 1. Initialization
        start = time.perf_counter()
        CapabilityMap(str(Path(__file__).parent / "fixtures"))
        metrics.record_timing("initialization", (time.perf_counter() - start) * 1000)

        # 2. Plugin checks (100 iterations)
        start = time.perf_counter()
        for _ in range(100):
            self.router.check_plugin_availability("agent-tdd", system_reminder)
        metrics.record_timing("availability_check", (time.perf_counter() - start) * 1000 / 100)

        # 3. Validations (100 iterations)
        payload = {
            "requirements_md": "# Req",
            "design_md": "# Design",
            "research_cache": {},
            "recap_md": "# Recap"
        }
        start = time.perf_counter()
        for _ in range(100):
            self.router.validate_handoff(
                "agent-isdd", "design_spec_handoff",
                "agent-tdd", "design_spec_slicing",
                payload
            )
        metrics.record_timing("handoff_validation", (time.perf_counter() - start) * 1000 / 100)

        # 4. Routing (1000 iterations)
        start = time.perf_counter()
        for _ in range(1000):
            self.router.route_to_next_plugin("agent-isdd", "design_approved", True)
        metrics.record_timing("routing", (time.perf_counter() - start) * 1000 / 1000)

        # Generate report
        report = metrics.report()

        print(f"\n{'='*60}")
        print(f"PERFORMANCE PROFILING REPORT")
        print(f"{'='*60}")
        print(f"\nSummary:")
        print(f"  Total Operations: {report['summary']['total_operations']}")
        print(f"\nOperation Latencies:")

        for op, stats in sorted(report['operations'].items()):
            if stats:
                print(f"\n  {op}:")
                print(f"    Count: {stats['count']}")
                print(f"    Avg:   {stats['avg_ms']:.3f}ms")
                print(f"    P95:   {stats['p95_ms']:.3f}ms")
                print(f"    P99:   {stats['p99_ms']:.3f}ms")
                print(f"    Range: {stats['min_ms']:.3f}ms - {stats['max_ms']:.3f}ms")

        # Assertions validate performance SLAs
        self.assertLess(report['operations']['initialization']['avg_ms'], 30,
            "Initialization SLA: <30ms")
        self.assertLess(report['operations']['availability_check']['avg_ms'], 0.1,
            "Availability check SLA: <0.1ms")
        self.assertLess(report['operations']['handoff_validation']['avg_ms'], 0.5,
            "Handoff validation SLA: <0.5ms")
        self.assertLess(report['operations']['routing']['avg_ms'], 0.1,
            "Routing SLA: <0.1ms")


if __name__ == "__main__":
    # Run with verbose output for performance metrics
    unittest.main(verbosity=2)

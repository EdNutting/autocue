# Copyright © 2025 Ed Nutting
# SPDX-License-Identifier: MIT
# See LICENSE file for details

"""
Performance profiling utilities for analyzing tracking algorithm bottlenecks.

Provides timing decorators, context managers, and reporting tools to identify
slow code paths in real-world usage.
"""

import cProfile
import functools
import io
import json
import logging
import pstats
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

# Type variable for generic function decoration
F = TypeVar('F', bound=Callable[..., Any])


@dataclass
class TimingStats:
    """Statistics for a timed code section."""
    name: str
    call_count: int = 0
    total_time: float = 0.0
    min_time: float = float('inf')
    max_time: float = 0.0
    times: list[float] = field(default_factory=list)

    @property
    def avg_time(self) -> float:
        """Average time per call."""
        return self.total_time / self.call_count if self.call_count > 0 else 0.0

    @property
    def median_time(self) -> float:
        """Median time per call."""
        if not self.times:
            return 0.0
        sorted_times = sorted(self.times)
        n = len(sorted_times)
        if n % 2 == 0:
            return (sorted_times[n//2 - 1] + sorted_times[n//2]) / 2
        return sorted_times[n//2]

    @property
    def p95_time(self) -> float:
        """95th percentile time."""
        if not self.times:
            return 0.0
        sorted_times = sorted(self.times)
        idx = int(len(sorted_times) * 0.95)
        return sorted_times[min(idx, len(sorted_times) - 1)]

    @property
    def p99_time(self) -> float:
        """99th percentile time."""
        if not self.times:
            return 0.0
        sorted_times = sorted(self.times)
        idx = int(len(sorted_times) * 0.99)
        return sorted_times[min(idx, len(sorted_times) - 1)]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "call_count": self.call_count,
            "total_time_ms": self.total_time * 1000,
            "avg_time_ms": self.avg_time * 1000,
            "median_time_ms": self.median_time * 1000,
            "min_time_ms": self.min_time * 1000,
            "max_time_ms": self.max_time * 1000,
            "p95_time_ms": self.p95_time * 1000,
            "p99_time_ms": self.p99_time * 1000,
        }


class PerformanceProfiler:
    """
    Global performance profiler for tracking code execution times.

    Thread-safe singleton that collects timing data from decorated functions
    and context managers.
    """

    _instance: "PerformanceProfiler | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "PerformanceProfiler":
        """Ensure singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize the profiler (only once)."""
        if self._initialized:
            return
        self._initialized = True
        self._stats: dict[str, TimingStats] = defaultdict(lambda: TimingStats(name=""))
        self._stats_lock = threading.Lock()
        self._enabled = False
        self._keep_all_times = False  # Whether to keep individual call times

    def enable(self, keep_all_times: bool = False) -> None:
        """
        Enable profiling.

        Args:
            keep_all_times: If True, keep all individual call times for percentile analysis.
                           Warning: Can use significant memory for high-frequency calls.
        """
        self._enabled = True
        self._keep_all_times = keep_all_times
        logger.info("Performance profiling enabled (keep_all_times=%s)", keep_all_times)

    def disable(self) -> None:
        """Disable profiling."""
        self._enabled = False
        logger.info("Performance profiling disabled")

    def is_enabled(self) -> bool:
        """Check if profiling is currently enabled."""
        return self._enabled

    def reset(self) -> None:
        """Clear all collected statistics."""
        with self._stats_lock:
            self._stats.clear()
        logger.info("Performance profiling statistics reset")

    def record_timing(self, name: str, duration: float) -> None:
        """
        Record a timing measurement.

        Args:
            name: Name of the timed operation
            duration: Duration in seconds
        """
        if not self._enabled:
            return

        with self._stats_lock:
            if name not in self._stats:
                self._stats[name] = TimingStats(name=name)

            stats = self._stats[name]
            stats.call_count += 1
            stats.total_time += duration
            stats.min_time = min(stats.min_time, duration)
            stats.max_time = max(stats.max_time, duration)

            # Only keep individual times if requested (can use lots of memory)
            if self._keep_all_times:
                stats.times.append(duration)

    def get_stats(self) -> dict[str, TimingStats]:
        """Get a copy of all collected statistics."""
        with self._stats_lock:
            return dict(self._stats)

    def print_report(self, top_n: int = 20, sort_by: str = "total") -> None:
        """
        Print a formatted performance report.

        Args:
            top_n: Number of top items to show
            sort_by: Sort key - "total" (total time), "avg" (average), "calls" (call count)
        """
        stats = self.get_stats()

        if not stats:
            print("No performance data collected.")
            return

        # Sort stats
        sort_keys = {
            "total": lambda s: s.total_time,
            "avg": lambda s: s.avg_time,
            "calls": lambda s: s.call_count,
        }
        sort_key = sort_keys.get(sort_by, sort_keys["total"])
        sorted_stats = sorted(stats.values(), key=sort_key, reverse=True)[:top_n]

        print("\n" + "=" * 100)
        print("PERFORMANCE PROFILING REPORT")
        print("=" * 100)
        print(f"{'Function':<50} {'Calls':>8} {'Total(ms)':>12} {'Avg(ms)':>10} {'Min(ms)':>10} {'Max(ms)':>10}")
        print("-" * 100)

        for stat in sorted_stats:
            print(f"{stat.name:<50} {stat.call_count:>8} "
                  f"{stat.total_time*1000:>12.2f} {stat.avg_time*1000:>10.3f} "
                  f"{stat.min_time*1000:>10.3f} {stat.max_time*1000:>10.3f}")

        if self._keep_all_times:
            print("\n" + "-" * 100)
            print(f"{'Function':<50} {'Median(ms)':>12} {'P95(ms)':>10} {'P99(ms)':>10}")
            print("-" * 100)
            for stat in sorted_stats:
                print(f"{stat.name:<50} {stat.median_time*1000:>12.3f} "
                      f"{stat.p95_time*1000:>10.3f} {stat.p99_time*1000:>10.3f}")

        print("=" * 100 + "\n")

    def save_report(self, output_path: Path | str) -> None:
        """
        Save performance report to JSON file.

        Args:
            output_path: Path to save the JSON report
        """
        stats = self.get_stats()
        report = {
            "timestamp": time.time(),
            "stats": [s.to_dict() for s in stats.values()]
        }

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)

        logger.info("Performance report saved to %s", output_path)


# Global profiler instance
_profiler = PerformanceProfiler()


def enable_profiling(keep_all_times: bool = False) -> None:
    """Enable global performance profiling."""
    _profiler.enable(keep_all_times=keep_all_times)


def disable_profiling() -> None:
    """Disable global performance profiling."""
    _profiler.disable()


def reset_profiling() -> None:
    """Reset all profiling statistics."""
    _profiler.reset()


def get_profiler() -> PerformanceProfiler:
    """Get the global profiler instance."""
    return _profiler


@contextmanager
def profile_section(name: str):
    """
    Context manager for timing a code section.

    Usage:
        with profile_section("my_operation"):
            # code to time
            pass
    """
    if not _profiler.is_enabled():
        yield
        return

    start = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start
        _profiler.record_timing(name, duration)


def profile_function(name: str | None = None) -> Callable[[F], F]:
    """
    Decorator for timing function calls.

    Args:
        name: Optional name for the timing record. If None, uses the function's qualified name.

    Usage:
        @profile_function()
        def my_function():
            pass

        @profile_function("custom_name")
        def my_function():
            pass
    """
    def decorator(func: F) -> F:
        timing_name = name if name else f"{func.__module__}.{func.__qualname__}"

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not _profiler.is_enabled():
                return func(*args, **kwargs)

            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                duration = time.perf_counter() - start
                _profiler.record_timing(timing_name, duration)

        return wrapper  # type: ignore[return-value]

    return decorator


@contextmanager
def profile_cprofile(output_path: Path | str | None = None, top_n: int = 30):
    """
    Context manager for running cProfile on a code section.

    Args:
        output_path: Optional path to save profile stats
        top_n: Number of top functions to print

    Usage:
        with profile_cprofile("profile_output.prof"):
            # code to profile
            pass
    """
    profiler = cProfile.Profile()
    profiler.enable()

    try:
        yield profiler
    finally:
        profiler.disable()

        # Print stats
        s = io.StringIO()
        stats = pstats.Stats(profiler, stream=s)
        stats.strip_dirs()
        stats.sort_stats('cumulative')
        stats.print_stats(top_n)
        print(s.getvalue())

        # Save to file if requested
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            stats.dump_stats(str(output_path))
            logger.info("cProfile stats saved to %s", output_path)

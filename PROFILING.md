# Performance Profiling Guide

This document explains how to use the profiling infrastructure to analyze and optimize the tracking algorithm performance.

## Overview

The profiling infrastructure provides:

1. **Low-overhead timing decorators** - Measure function execution times without significant performance impact
2. **Detailed statistics** - Call counts, averages, min/max, percentiles (P95, P99)
3. **Performance tests** - Automated benchmarks to catch regressions
4. **cProfile integration** - Deep analysis of hot code paths

## Quick Start

### Run the Example Profiling Script

```bash
python examples/profile_tracking.py
```

This will:
- Profile a realistic tracking session
- Print a performance report
- Save detailed JSON reports to `profiling_results/`
- Generate cProfile stats for deep analysis

### Run Performance Tests

```bash
# Run all performance tests
python -m pytest tests/test_performance.py -v

# Run specific test
python -m pytest tests/test_performance.py::TestTrackingPerformance::test_realistic_session_performance -v

# Run with detailed cProfile (slower)
python -m pytest tests/test_performance.py::TestTrackingPerformance::test_comprehensive_cprofile -v -m slow
```

## Using Profiling in Your Code

### Enable Profiling

```python
from autocue.profiling import enable_profiling, get_profiler

# Enable profiling (minimal memory)
enable_profiling()

# Enable with percentile tracking (uses more memory)
enable_profiling(keep_all_times=True)
```

### Decorate Functions

```python
from autocue.profiling import profile_function

@profile_function()  # Uses function name
def my_function():
    pass

@profile_function("custom_name")  # Custom name
def my_function():
    pass
```

### Profile Code Sections

```python
from autocue.profiling import profile_section

with profile_section("my_operation"):
    # Code to profile
    pass
```

### Get Results

```python
from autocue.profiling import get_profiler

profiler = get_profiler()

# Print report to console
profiler.print_report(top_n=20, sort_by="total")  # or "avg" or "calls"

# Save to JSON
profiler.save_report("results.json")

# Get raw statistics
stats = profiler.get_stats()
for name, stat in stats.items():
    print(f"{name}: {stat.avg_time*1000:.3f}ms avg")
```

### Reset Statistics

```python
from autocue.profiling import reset_profiling

reset_profiling()  # Clear all collected stats
```

## Profiling the Main Application

To profile a live Autocue session:

1. Enable profiling in `main.py`:

```python
from autocue.profiling import enable_profiling, get_profiler

# At startup
enable_profiling(keep_all_times=True)

# At shutdown (in app.stop())
profiler = get_profiler()
profiler.save_report("live_session_profile.json")
```

2. Run Autocue normally and use it
3. Stop the application to save the profile

## Analyzing Results

### Performance Report Format

```
Function                          Calls  Total(ms)  Avg(ms)  Min(ms)  Max(ms)  Median(ms)  P95(ms)  P99(ms)
tracker.update                     1250    1250.50    1.000    0.100   15.500       0.850    2.500    5.000
tracker._update_partial            1000     800.00    0.800    0.050   10.000       0.600    1.800    3.500
tracker._match_single_word         5000     300.50    0.060    0.010    2.000       0.050    0.150    0.300
...
```

**Key Metrics:**
- **Total(ms)** - Total time spent in function (find the biggest time sinks)
- **Avg(ms)** - Average per call (find slow functions)
- **Calls** - Number of calls (find hot paths)
- **P95/P99** - Tail latency (find worst-case performance)

### Using cProfile Output

```bash
# Analyze cProfile stats
python -m pstats profiling_results/tracking_cprofile.prof

# In pstats interactive mode:
> strip
> sort cumulative
> stats 30
> sort time
> stats 30
```

## Performance Targets

Based on real-time requirements (audio chunks every 100ms):

| Operation | Target Avg | Target P95 | Notes |
|-----------|-----------|-----------|--------|
| Partial update | < 5ms | < 20ms | Happens frequently |
| Final update | < 10ms | < 30ms | Less frequent, can be slower |
| Single word match | < 2ms | < 5ms | Very frequent |
| Backtrack detection | < 15ms | < 50ms | Rare, can be slower |
| Initialization | < 50ms | < 100ms | One-time cost |

## Finding Bottlenecks

1. **Run performance tests** to establish baseline:
   ```bash
   python -m pytest tests/test_performance.py -v
   ```

2. **Check which functions use the most total time**:
   ```python
   profiler.print_report(sort_by="total")
   ```

3. **Check which functions are slowest per-call**:
   ```python
   profiler.print_report(sort_by="avg")
   ```

4. **Use cProfile for deep analysis**:
   ```bash
   python examples/profile_tracking.py
   ```

## Optimization Strategies

Based on profiling results, consider:

### 1. Algorithmic Improvements
- Reduce search space (e.g., limit window size)
- Use more efficient data structures (e.g., hash maps instead of lists)
- Cache computed results (e.g., normalized words)

### 2. Parallelization
- Run tracking in separate thread/process from audio capture
- Use asyncio for concurrent operations
- Consider queue-based architecture

### 3. Code-level Optimizations
- Replace hot loops with list comprehensions or NumPy
- Reduce function call overhead (inline hot functions)
- Use faster libraries (e.g., Cython for critical paths)

### 4. Reduce Work
- Skip unnecessary computations (e.g., don't process if same as last)
- Early exit when possible
- Batch operations instead of one-by-one

## Continuous Performance Monitoring

Add performance tests to CI:

```bash
# Add to CI pipeline
python -m pytest tests/test_performance.py -v --tb=short
```

Set up alerts if performance regresses beyond thresholds.

## Advanced: Profiling with py-spy

For low-overhead sampling profiling of running processes:

```bash
# Install py-spy
pip install py-spy

# Profile running Autocue
sudo py-spy record -o profile.svg --pid <autocue_pid>

# Or run directly
sudo py-spy record -o profile.svg -- python -m autocue.main
```

## Troubleshooting

### Profiling overhead too high

- Disable profiling in production: `disable_profiling()`
- Don't use `keep_all_times=True` for long sessions
- Profile only critical sections instead of everything

### Results don't match expectations

- Ensure profiling is enabled before running code
- Check that decorators are on the right functions
- Verify Python isn't optimizing away your code
- Try cProfile for comparison

### Memory usage too high with `keep_all_times=True`

- Don't use it for long sessions (thousands of calls)
- Or periodically save and reset: `profiler.save_report()` then `reset_profiling()`

## See Also

- [Python profiling documentation](https://docs.python.org/3/library/profile.html)
- [py-spy sampling profiler](https://github.com/benfred/py-spy)
- [line_profiler for line-by-line profiling](https://github.com/pyutils/line_profiler)

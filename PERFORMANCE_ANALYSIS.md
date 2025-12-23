# Performance Analysis Summary

## Initial Profiling Results

Based on the realistic session performance test, here are the key findings:

### Current Bottlenecks (Ranked by Total Time)

1. **`_detect_jump_internal()` - 319ms total (0.33ms avg, 983 calls)**
   - **Why it's slow**: Performs window-based fuzzy matching across a search range
   - **Impact**: Called frequently for partial updates, checking for backtracks
   - **P95 latency**: 0.42ms

2. **`_find_best_match()` - 308ms total (0.31ms avg, 983 calls)**
   - **Why it's slow**: Slides window through search range, doing fuzzy matching at each position
   - **Impact**: Called by `_detect_jump_internal()` for every potential jump
   - **P95 latency**: 0.41ms

3. **`_process_words()` - 355ms total (0.33ms avg, 1073 calls)**
   - **Why it's slow**: Main word processing loop, calls jump detection
   - **Impact**: Core of the tracking algorithm
   - **P95 latency**: 0.46ms

4. **`_match_words_with_skipping()` - 32ms total (0.05ms avg, 610 calls)**
   - **Why it's moderate**: Tries multiple skip strategies with state cloning
   - **Impact**: Called when single-word matching fails
   - **P95 latency**: 0.06ms

### Update Latency Analysis

| Update Type | Avg Latency | P95 Latency | Max Latency | Notes |
|-------------|------------|-------------|-------------|-------|
| **Partial** | 3.5ms | 16.4ms | 18.5ms | **CONCERN** - Can miss audio chunks |
| **Final** | 0.25ms | 0.58ms | 0.58ms | Acceptable |

**Critical Issue**: Partial updates averaging 3.5ms with P95 of 16.4ms is problematic because:

- Audio chunks arrive every 100ms
- Multiple operations happen per chunk (transcription + tracking + UI update)
- P95 of 16ms leaves little headroom
- Max of 18.5ms could cause audio buffer issues

### Per-Call Performance

| Function | Avg Time | P95 Time | Call Count |
|----------|----------|----------|-----------|
| `_match_single_word()` | 0.001ms | 0.002ms | 11,610 |
| `_update_final()` | 0.248ms | 0.582ms | 20 |
| `_find_best_match()` | 0.313ms | 0.410ms | 983 |
| `_detect_jump_internal()` | 0.325ms | 0.423ms | 983 |
| `_update_partial()` | 3.526ms | 16.758ms | 100 |

## Root Cause Analysis

### Why Partial Updates Are Slow

Looking at the call hierarchy:

```
_update_partial() [3.5ms avg]
└─ _process_words() [0.33ms avg, called ~10x per partial]
   └─ _detect_jump_internal() [0.33ms avg, called for most words]
      └─ _find_best_match() [0.31ms avg]
```

The issue: **Jump detection is called too frequently for partial updates**

Current behavior:

- Every partial update clones state and processes all words
- For each unmatched word queue with ≥5 words, jump detection runs
- Jump detection searches a window (±50 words by default)
- At each position, it calculates fuzzy match score

**Calculation**:

- 100 partial updates × ~10 jump detections each = 1000 jump detections
- Each jump detection searches ~100 positions
- Each position calculates fuzzy match: ~100,000 fuzzy matches total!

## Optimization Opportunities

### 1. **Reduce Jump Detection Frequency for Partials** (High Impact)

**Problem**: Partial transcripts trigger jump detection as aggressively as finals

**Solution**: Skip jump detection for partial updates

```python
# In _process_words(), check if this is a partial
if update_validation_counter:  # Only for finals
    _, is_jump = self._detect_jump_internal(state)
```

**Expected Improvement**: 90% reduction in partial update latency (from 3.5ms → 0.35ms)

### 2. **Cache Fuzzy Match Results** (Medium Impact)

**Problem**: Same text is fuzzy-matched repeatedly

**Solution**: LRU cache on `_find_best_match()` with transcription as key (consider if position must also be a key)

```python
from functools import lru_cache

@lru_cache(maxsize=128)
def _find_best_match_cached(self, spoken_words: str, current_position: int):
    # ... existing logic
```

**Expected Improvement**: 30-50% reduction in `_find_best_match()` time

### 3. **Optimize Window Search Range** (Medium Impact)

**Problem**: Searches ±50 words even when unnecessary

**Solution**: Use exponential search - start with small range, expand if needed

```python
# Try small range first (±10 words)
# If confidence is high, use it
# Otherwise expand to ±25, then ±50
```

**Expected Improvement**: 40% reduction in search time for common cases

### 4. **Parallelize Tracking from Transcription** (High Impact)

**Problem**: Tracking blocks the main loop

**Solution**: Run tracker in separate thread with queue

```python
# Main loop puts transcription in queue
# Tracker thread processes and sends updates
# Non-blocking for audio capture
```

**Expected Improvement**: Eliminates blocking, allows 10ms+ tracking time

### 5. **Batch Partial Updates** (Low Impact)

**Problem**: Every partial word triggers full reprocessing

**Solution**: Only update from partials every 50ms or more

```python
if is_partial and time_since_last_partial < 0.05:
    return  # Skip this partial
```

**Expected Improvement**: 50% reduction in partial update frequency

## Recommended Action Plan

### Phase 1: Quick Wins (1-2 hours)

1. ✅ Set up profiling infrastructure
2. ✅ Skip jump detection for partial updates
3. ✅ Reduce window search range for partials

**Expected Result**: Partial updates from 3.5ms → 0.5ms avg

### Phase 2: Caching (2-3 hours)

1. ✅ Add LRU cache to fuzzy matching
2. ✅ Cache normalized words
3. ✅ Profile again to measure improvement

**Expected Result**: Overall 30% speedup

**Implementation Details**:

- Added `@lru_cache(maxsize=512)` to `normalize_word()` in [script_parser.py](src/autocue/script_parser.py:128)
- Implemented instance-level LRU cache for `_find_best_match()` in [tracker.py](src/autocue/tracker.py:1035)
    - Cache key: `(spoken_words, current_word_index)`
    - Max cache size: 128 entries
    - Automatic LRU eviction when maxsize exceeded
    - Cache cleared on `reset()` and `jump_to()` operations
- Added comprehensive test suite in [tests/tracker/test_caching.py](tests/tracker/test_caching.py)
    - 12 tests covering cache initialization, storage, reuse, eviction, and integration
    - All tests passing with no regressions in existing test suite (135 tests)

### Phase 3: Architecture (1 day)

1. ⏭️ Move tracking to separate thread
2. ⏭️ Implement queue-based communication
3. ⏭️ Limit partial updates to every 50ms or more
4. ⏭️ Add backpressure handling

**Expected Result**: Non-blocking tracking, eliminates all latency concerns

## How to Continue Analysis

### Run Profiling During Live Session

Add to `main.py`:

```python
from autocue.profiling import enable_profiling, get_profiler

# In AutocueApp.__init__()
enable_profiling(keep_all_times=True)

# In AutocueApp.stop()
profiler = get_profiler()
profiler.save_report("live_session_profile.json")
profiler.print_report(top_n=30)
```

### Monitor Specific Operations

Add custom profiling:

```python
from autocue.profiling import profile_section

with profile_section("audio_processing"):
    # ... your code

with profile_section("ui_update"):
    # ... your code
```

### Compare Before/After Optimizations

```bash
# Before
python -m pytest tests/test_performance.py::TestTrackingPerformance::test_realistic_session_performance -v

# Make changes

# After
python -m pytest tests/test_performance.py::TestTrackingPerformance::test_realistic_session_performance -v

# Compare profiling_results/performance_report.json
```

## Next Steps

1. ✅ **Validate findings in real usage** - Run profiling during actual recording session
2. **Implement Phase 1 optimizations** - Quick wins for immediate improvement
3. ~**Set up performance CI** - Catch regressions early~
4. **Consider parallel architecture** - For maximum responsiveness

## Tools Available

- `python -m pytest tests/test_performance.py` - Automated benchmarks
- `python examples/profile_tracking.py` - Interactive profiling
- `PROFILING.md` - Complete profiling guide
- `profiling_results/` - Saved profiling data

---

**Created**: 2025-12-23
**Tool**: autocue.profiling
**Status**: Initial analysis complete, optimizations recommended

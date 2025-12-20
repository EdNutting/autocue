# Claude Code Instructions for Autocue

This file contains instructions for Claude Code sessions working on this project.

## Testing Guidelines

### Always Add Tests to the Test Suite

When implementing new features or fixing bugs, **always add tests to the test suite** rather than running one-off Python commands to verify behavior.

**DO NOT** run ad-hoc verification like:
```python
# Bad - one-off test
python -c "from src.autocue.tracker import ScriptTracker; t = ScriptTracker('A / B'); print(t.words)"
```

**INSTEAD** add a proper test to the test suite:
```python
# Good - add to tests/test_tracker.py or appropriate test file
def test_slash_parsing(self):
    """Verify '/' is handled correctly in scripts."""
    tracker = ScriptTracker("A / B")
    assert "slash" in tracker.words or "or" in tracker.words
```

### Test File Organization

- `tests/test_tracker.py` - Tests for the ScriptTracker class and optimistic matching
- `tests/test_tracker_comprehensive.py` - Integration tests with realistic speech patterns
- `tests/test_script_parser.py` - Tests for the script_parser module (punctuation expansion, Markdown handling)

### Running Tests

Run all tests:
```bash
python -m pytest tests/ -v
```

Run a specific test file:
```bash
python -m pytest tests/test_script_parser.py -v
```

Run a specific test class:
```bash
python -m pytest tests/test_tracker.py::TestAlternativePunctuationMatching -v
```

### Test Naming Conventions

- Test classes should be named `TestFeatureName`
- Test methods should be named `test_specific_behavior`
- Each test should have a docstring explaining what it verifies

### What to Test

When adding new functionality, ensure tests cover:

1. **Happy path** - Normal expected behavior
2. **Edge cases** - Boundary conditions, empty inputs, single-item inputs
3. **Error conditions** - Invalid inputs, if applicable
4. **Integration** - How the feature works with other components

### Punctuation Expansion Testing

The `script_parser.py` module handles punctuation that gets spoken aloud (e.g., `&` as "and", `/` as "slash"). When modifying punctuation expansions:

1. Update `PUNCTUATION_EXPANSIONS` in `src/autocue/script_parser.py`
2. Add corresponding tests in `tests/test_script_parser.py::TestPunctuationExpansionStructure`
3. Add tracker matching tests in `tests/test_tracker.py::TestAlternativePunctuationMatching`

## Project Architecture

### Key Modules

- `src/autocue/tracker.py` - Speech position tracking with optimistic matching
- `src/autocue/script_parser.py` - Three-version script parsing (raw tokens, speakable words, HTML)
- `src/autocue/server.py` - WebSocket server for frontend communication
- `src/autocue/transcribe.py` - Audio transcription integration

### Three-Version Script Architecture

The system maintains three representations of the script text:

1. **Raw tokens** - Tokens as they appear in rendered HTML (after Markdown processing)
2. **Speakable words** - Words as they would be spoken (with punctuation expanded)
3. **HTML rendering** - With word indices mapping back to raw tokens

This ensures the speech tracker and UI highlighting stay in sync.

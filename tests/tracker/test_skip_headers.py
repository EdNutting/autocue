# Copyright © 2025 Ed Nutting
# SPDX-License-Identifier: MIT
# See LICENSE file for details

"""Tests for skip headers functionality."""

import unittest

from src.autocue.tracker import ScriptTracker


class TestSkipHeaders(unittest.TestCase):
    """Test that headers can be skipped during tracking."""

    def test_skip_headers_disabled_by_default(self):
        """Verify that headers are not skipped by default."""
        script = """# Introduction

This is the introduction text.

## Section One

This is section one content."""

        tracker: ScriptTracker = ScriptTracker(script)

        # Headers should be tracked by default
        self.assertFalse(tracker.skip_headers)

    def test_skip_headers_enabled(self):
        """Verify that headers are skipped when option is enabled."""
        script = """# Introduction

This is the introduction text.

## Section One

This is section one content."""

        tracker: ScriptTracker = ScriptTracker(script, skip_headers=True)

        # Option should be set
        self.assertTrue(tracker.skip_headers)

    def test_tracking_skips_header_words(self):
        """Verify that tracking skips over header words when enabled."""
        script = """# Introduction

This is the introduction text."""

        tracker: ScriptTracker = ScriptTracker(script, skip_headers=True)

        # Start speaking - should skip "Introduction" header and match "this"
        pos = tracker.update("this", is_partial=False)

        # Position should be past the matched word, pointing at next word
        # Check that we're past the header
        speakable_words = tracker.parsed_script.speakable_words

        # The previous word (just matched) should be "this"
        if pos.speakable_index > 0:
            previous_word = speakable_words[pos.speakable_index - 1]
            self.assertEqual(previous_word.text, "this")
            self.assertFalse(previous_word.is_header)

        # Current position should not be pointing at a header
        current_word = speakable_words[pos.speakable_index]
        self.assertFalse(current_word.is_header)

    def test_header_words_marked_correctly(self):
        """Verify that header words are correctly marked in parsed script."""
        script = """# Header One

Regular text here.

## Header Two

More regular text."""

        tracker: ScriptTracker = ScriptTracker(script)

        # Check that header words are marked
        speakable_words = tracker.parsed_script.speakable_words

        # Find words
        header_one_idx = None
        header_two_idx = None
        regular_text_idx = None

        for idx, sw in enumerate(speakable_words):
            if sw.text == "header" and sw.is_header and header_one_idx is None:
                header_one_idx = idx
            elif sw.text == "header" and sw.is_header and header_one_idx is not None and header_two_idx is None:
                header_two_idx = idx
            elif sw.text == "regular" and not sw.is_header and regular_text_idx is None:
                regular_text_idx = idx

        # Verify we found header words
        self.assertIsNotNone(header_one_idx, "Should find 'Header' from first header")
        self.assertIsNotNone(header_two_idx, "Should find 'Header' from second header")
        self.assertIsNotNone(regular_text_idx, "Should find 'Regular' from body text")

        # Verify header words are marked
        self.assertTrue(speakable_words[header_one_idx].is_header)
        self.assertTrue(speakable_words[header_two_idx].is_header)
        self.assertFalse(speakable_words[regular_text_idx].is_header)

    def test_skip_headers_with_multiple_headers(self):
        """Verify that multiple headers in sequence are all skipped."""
        script = """# Main Title

## Subtitle

### Sub-subtitle

Now here is the actual content."""

        tracker: ScriptTracker = ScriptTracker(script, skip_headers=True)

        # Speak first non-header word
        pos = tracker.update("now", is_partial=False)

        # Position points to next word after match, so check previous word
        speakable_words = tracker.parsed_script.speakable_words
        if pos.speakable_index > 0:
            previous_word = speakable_words[pos.speakable_index - 1]
            self.assertEqual(previous_word.text, "now")
            self.assertFalse(previous_word.is_header)

    def test_skip_headers_partial_updates(self):
        """Verify that header skipping works with partial updates."""
        script = """# Introduction

This is the content."""

        tracker: ScriptTracker = ScriptTracker(script, skip_headers=True)

        # Send partial update
        pos = tracker.update("th", is_partial=True)

        # Should still skip header and match content
        # (position might not advance much on a partial, but it shouldn't match header)
        # This is more about ensuring no errors occur
        self.assertIsNotNone(pos)

    def test_no_headers_in_script(self):
        """Verify that skip_headers doesn't break when there are no headers."""
        script = "This is plain text with no headers at all."

        tracker: ScriptTracker = ScriptTracker(script, skip_headers=True)

        # Should work normally
        pos = tracker.update("this is plain", is_partial=False)
        self.assertGreater(pos.speakable_index, 0)

    def test_headers_tracked_when_disabled(self):
        """Verify that headers ARE tracked when skip_headers is False."""
        script = """# Introduction

Content here."""

        tracker: ScriptTracker = ScriptTracker(script, skip_headers=False)

        # Speak the header word
        pos = tracker.update("introduction", is_partial=False)

        # Position points to next word after match, so check previous word
        speakable_words = tracker.parsed_script.speakable_words
        if pos.speakable_index > 0:
            previous_word = speakable_words[pos.speakable_index - 1]
            self.assertEqual(previous_word.text, "introduction")
            self.assertTrue(previous_word.is_header)

    def test_mixed_content_with_headers(self):
        """Test tracking through mixed content with headers."""
        script = """# First Section

This is the first paragraph.

## Subsection

This is a subsection.

# Second Section

This is the second paragraph."""

        tracker: ScriptTracker = ScriptTracker(script, skip_headers=True)

        # Track through the content, skipping headers
        tracker.update("this is the first paragraph", is_partial=False)
        pos1 = tracker.current_position

        # Continue to subsection content
        tracker.update("this is a subsection", is_partial=False)
        pos2 = tracker.current_position

        # Should have advanced
        self.assertGreater(pos2.speakable_index, pos1.speakable_index)

        # Continue to second section content
        tracker.update("this is the second paragraph", is_partial=False)
        pos3 = tracker.current_position

        # Should have advanced further
        self.assertGreater(pos3.speakable_index, pos2.speakable_index)


if __name__ == "__main__":
    unittest.main()

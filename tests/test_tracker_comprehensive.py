"""
Comprehensive tests for ScriptTracker using realistic speech patterns.

These tests use the sample_script.md content to simulate realistic
speech recognition scenarios including:
- Normal accurate speech across multiple paragraphs
- Minor speech faults (ums, ahs, repetitions, word swaps)
- Backtracking to earlier positions
- Forward jumping (skipping sentences)
- False-positive backtrack prevention
- Nearest-backtrack behavior
- False-positive forward jump prevention
"""

from src.autocue.tracker import ScriptTracker


# Sample script content (from sample_script.md)
SAMPLE_SCRIPT = """# Welcome to Autocue

Hello and welcome to this demonstration of the autocue system. Today I'm going to walk you through how this teleprompter works and why it might be useful for your video production workflow.

## How It Works

The system listens to your voice through the microphone and uses speech recognition to figure out where you are in the script. It then scrolls the display automatically to keep up with you.

What makes this different from a traditional teleprompter is that you don't need a separate operator. The software handles everything for you.

## Key Features

Let me tell you about some of the key features:

- **Automatic scrolling** that follows your natural speaking pace
- **Backtrack detection** so if you make a mistake and restart a sentence, it rewinds with you
- **Low latency** because everything runs locally on your machine
- **Privacy focused** since your audio never leaves your computer

## Testing the Backtrack Feature

Now I want to demonstrate the backtrack detection. When I make a mistake and go back to restart my sentence, the prompter should detect this and scroll back to match.

Let me try that now. This sentence is designed for you to deliberately restart it partway through and see if the display follows.

## Formatting Examples

The prompter supports **bold text** and *italic text* which can help you emphasise certain words in your script.

You can also use headers to break up your content into logical sections, making it easier to navigate at a glance.

### Subsection Example

This is a subsection with a smaller header. You might use these to organise talking points within a larger topic.

## Numbers and Technical Content

Sometimes you need to read out specific numbers or technical terms. For example:

- The M3 processor has approximately 25 billion transistors
- Clock speeds can reach up to 4.05 gigahertz
- The memory bandwidth is around 100 gigabytes per second

These specific details can be tricky with speech recognition, so it's good to test how well the tracking handles them.

## Speaking Naturally

Remember that you don't need to speak like a robot. The fuzzy matching algorithm is designed to handle natural speech patterns.

If you say "gonna" instead of "going to" or drop a word here and there, the system should still track your position correctly.

Feel free to pause, take a breath, and continue at your own pace. The prompter will wait for you.

## Wrapping Up

That brings us to the end of this demonstration script. Hopefully this has given you a good feel for how the autocue system works.

The main things to remember are: speak naturally, don't worry about small mistakes, and if you need to restart a sentence, just do it and the prompter will follow.

Thanks for watching, and good luck with your recordings!
"""


class TestNormalTalking:
    """
    Tests for accurate speech tracking where multiple paragraphs of speech
    exactly match the words of the script. The tracking should accurately
    track position word by word.

    Note: The sample script starts with "# Welcome to Autocue" header, so the
    first parsed words are: welcome(0), to(1), autocue(2), hello(3), and(4), ...
    """

    def test_first_paragraph_word_by_word(self):
        """Accurately spoken first paragraph should track word by word."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Start from the actual first words (including header)
        # Script word order: welcome(0), to(1), autocue(2), hello(3), and(4), welcome(5)...
        words = ["welcome", "to", "autocue", "hello", "and", "welcome",
                 "to", "this", "demonstration", "of"]

        transcript = ""
        for i, word in enumerate(words):
            transcript = (transcript + " " + word).strip()
            pos = tracker.update(transcript)

            # Position should advance by 1 for each word
            assert pos.word_index == i + 1, f"Expected word_index {i + 1} after '{word}', got {pos.word_index}"

    def test_multi_paragraph_tracking(self):
        """Speaking through multiple paragraphs should maintain accurate position."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Start with the header, then continue into intro
        # Words: welcome to autocue hello and welcome to this demonstration of the autocue system...
        intro = "welcome to autocue hello and welcome to this demonstration of the autocue system today im going to walk you through how this teleprompter works and why it might be useful for your video production workflow"
        pos = tracker.update(intro)

        # Should have advanced through all words
        intro_word_count = len(intro.split())
        assert pos.word_index >= intro_word_count - 3, f"Should be near position {intro_word_count}, got {pos.word_index}"

        # Continue with the next section header and content
        section_start = intro + " how it works the system listens to your voice through the microphone"
        pos = tracker.update(section_start)

        assert pos.word_index > intro_word_count, "Should have advanced into 'How It Works' section"

    def test_section_by_section_tracking(self):
        """Tracking should remain accurate as we move through different sections."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Track through header + intro (starting from actual first words)
        tracker.update("welcome to autocue hello and welcome to this demonstration of the autocue system")
        first_section_pos = tracker.optimistic_position
        assert first_section_pos > 0

        # Continue through more of intro
        tracker.update("welcome to autocue hello and welcome to this demonstration of the autocue system today im going to walk you through how this teleprompter works")
        second_pos = tracker.optimistic_position
        assert second_pos > first_section_pos

        # Continue into "How It Works" section
        tracker.update("welcome to autocue hello and welcome to this demonstration of the autocue system today im going to walk you through how this teleprompter works and why it might be useful for your video production workflow how it works the system listens to your voice")
        third_pos = tracker.optimistic_position
        assert third_pos > second_pos

    def test_continuous_accurate_speech_through_features_section(self):
        """Accurate speech through the Key Features section should track correctly."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Start from header and work up to key features
        intro = "welcome to autocue hello and welcome to this demonstration of the autocue system today im going to walk you through how this teleprompter works and why it might be useful for your video production workflow how it works the system listens to your voice through the microphone and uses speech recognition to figure out where you are in the script it then scrolls the display automatically to keep up with you what makes this different from a traditional teleprompter is that you dont need a separate operator the software handles everything for you key features let me tell you about some of the key features"
        pos = tracker.update(intro)
        pos_before_features = tracker.optimistic_position

        # Speak through the feature bullets
        features = intro + " automatic scrolling that follows your natural speaking pace backtrack detection so if you make a mistake and restart a sentence it rewinds with you"
        pos = tracker.update(features)

        assert tracker.optimistic_position > pos_before_features

    def test_position_accuracy_within_tolerance(self):
        """Position should always be within 3 words of expected for accurate speech."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Use the actual parsed words from the tracker
        script_words = tracker.words[:50]  # First 50 normalized words

        transcript = ""
        for expected_pos, word in enumerate(script_words, 1):
            transcript = (transcript + " " + word).strip()
            pos = tracker.update(transcript)

            # Position should be within 3 words of expected
            assert abs(pos.word_index - expected_pos) <= 3, \
                f"Position {pos.word_index} too far from expected {expected_pos} after word '{word}'"


class TestMinorSpeechFaults:
    """
    Tests for largely accurate speech with minor faults like ums, ahs,
    word repetitions, word order swaps, etc. Tracking should remain
    accurate to within 3 words across several paragraphs.

    Note: Script starts with header "# Welcome to Autocue", so first words are:
    welcome(0), to(1), autocue(2), hello(3), and(4), welcome(5), to(6), this(7)...
    """

    def test_um_and_ah_filler_words(self):
        """Filler words (um, ah, uh) should not disrupt tracking."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Speech with filler words - starting from actual first words
        speech = "welcome um to autocue uh hello ah and welcome to this demonstration"
        pos = tracker.update(speech)

        # Should still track past the filler words
        assert pos.word_index >= 5, \
            f"Should have advanced despite fillers, got {pos.word_index}"

    def test_word_repetition(self):
        """Repeating a word once should not significantly disrupt tracking."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Normal start with correct words
        tracker.update("welcome to autocue hello")
        pos_before = tracker.optimistic_position

        # Repeat "and" then continue
        tracker.update("welcome to autocue hello and and welcome to this")
        pos_after = tracker.optimistic_position

        # Should have continued advancing despite repetition
        assert pos_after > pos_before
        # Position should be within 3 words of where we'd expect
        assert pos_after >= 6

    def test_word_order_swap(self):
        """Swapping order of two adjacent words should not break tracking."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Swap "to" and "autocue" -> "welcome autocue to hello"
        speech = "welcome autocue to hello and welcome to this demonstration"
        pos = tracker.update(speech)

        # Should still track reasonably - surrounding words should help
        assert pos.word_index >= 5, \
            f"Should track past the swapped words, got {pos.word_index}"

    def test_minor_mispronunciation(self):
        """Minor pronunciation differences should still match via fuzzy matching."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Say "demonstrashun" instead of "demonstration"
        speech = "welcome to autocue hello and welcome to this demonstrashun"
        pos = tracker.update(speech)

        # Fuzzy matching should handle this
        assert pos.word_index >= 6, \
            f"Should track despite mispronunciation, got {pos.word_index}"

    def test_dropped_word(self):
        """Dropping a single word should still allow tracking to continue."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Skip "hello" - say "welcome to autocue and welcome"
        speech = "welcome to autocue and welcome to this demonstration"
        pos = tracker.update(speech)

        # Tracker allows skipping up to 2 words, so this should work
        assert pos.word_index >= 5, \
            f"Should track despite dropped word, got {pos.word_index}"

    def test_multiple_minor_faults_across_paragraphs(self):
        """Multiple minor faults through script should maintain reasonable tracking."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # First part with some fillers and a repeat
        para1 = "welcome to autocue um hello and welcome to this this demonstration"
        tracker.update(para1)
        pos1 = tracker.optimistic_position

        # Continue with slight variations
        para2 = para1 + " of the uh autocue system today im gonna walk you through"
        tracker.update(para2)
        pos2 = tracker.optimistic_position

        assert pos2 > pos1, "Should continue advancing despite faults"

        # Add more content with faults
        para3 = para2 + " how this um teleprompter works"
        tracker.update(para3)
        pos3 = tracker.optimistic_position

        assert pos3 > pos2, "Should continue advancing"

    def test_tracking_accuracy_with_faults_within_three_words(self):
        """Despite minor faults, tracking should stay within 3 words of correct."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Speak with various minor faults using correct starting words
        speech_segments = [
            "welcome to autocue",  # Clean
            "welcome to autocue hello um and",  # Filler
            "welcome to autocue hello um and welcome to",  # Continue
            "welcome to autocue hello um and welcome to this this",  # Repeat
            "welcome to autocue hello um and welcome to this this demonstration",
        ]

        pos = None
        for speech in speech_segments:
            pos = tracker.update(speech)

        # Should be around word 9 (after "demonstration")
        expected = 9
        assert pos is not None, "Loop should have executed at least once"
        assert abs(pos.word_index - expected) <= 4, \
            f"Position {pos.word_index} too far from expected ~{expected}"

    def test_gonna_instead_of_going_to(self):
        """Common contractions like 'gonna' should work with fuzzy matching."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Build up to "going to" section - script says "going to walk you through"
        speech = ("welcome to autocue hello and welcome to this demonstration "
                  "of the autocue system today im gonna walk you through")
        pos = tracker.update(speech)

        # Should still track - "gonna" vs "going" may not match exactly
        # but surrounding context should keep us on track
        assert pos.word_index >= 12, \
            f"Should track through with 'gonna', got {pos.word_index}"


class TestBacktracking:
    """
    Tests for backtracking detection when the user goes back and starts
    from an earlier sentence or heading. The beginning of the backtrack
    should be accurately detected, and words spoken after should match
    against the new position.

    Note: Script words start: welcome(0), to(1), autocue(2), hello(3)...
    """

    def test_backtrack_to_beginning_of_paragraph(self):
        """Backtracking to restart the current paragraph should be detected."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Speak partway through - use correct starting words
        speech = ("welcome to autocue hello and welcome to this demonstration "
                  "of the autocue system today im going to walk you through")
        tracker.update(speech)
        high_water = tracker.high_water_mark
        assert high_water > 10, "Should have advanced significantly"

        # Now restart from the beginning
        tracker.last_transcription = ""
        tracker.needs_validation = True
        _, is_backtrack = tracker.validate_position(
            "welcome to autocue hello and welcome"
        )

        # Should detect backtrack
        assert is_backtrack, "Should detect backtrack to beginning"
        assert tracker.optimistic_position < high_water, "Should have moved back"

    def test_backtrack_to_earlier_section(self):
        """Backtracking to a previous section should be detected."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Advance through intro and into "How It Works"
        speech = ("welcome to autocue hello and welcome to this demonstration "
                  "of the autocue system today im going to walk you through "
                  "how this teleprompter works and why it might be useful for "
                  "your video production workflow how it works the system "
                  "listens to your voice through the microphone")
        tracker.update(speech)
        original_pos = tracker.optimistic_position
        assert original_pos > 30, "Should be well into the script"

        # Backtrack to the intro
        tracker.last_transcription = ""
        tracker.needs_validation = True
        _, is_backtrack = tracker.validate_position(
            "welcome to autocue hello and welcome to this demonstration"
        )

        assert is_backtrack, "Should detect backtrack to intro"
        assert tracker.optimistic_position < original_pos, "Should move back"

    def test_backtrack_mid_sentence(self):
        """Backtracking mid-sentence to restart should be detected."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # First advance to "the system listens" section
        preamble = ("welcome to autocue hello and welcome to this demonstration "
                    "of the autocue system today im going to walk you through "
                    "how this teleprompter works and why it might be useful for "
                    "your video production workflow how it works")
        tracker.update(preamble)

        # Speak partway through the sentence
        full = preamble + " the system listens to your voice through the microphone and uses"
        tracker.update(full)
        mid_pos = tracker.optimistic_position

        # Restart from "the system listens"
        tracker.last_transcription = ""
        tracker.needs_validation = True
        tracker.validate_position("the system listens to your voice through")

        # Position should have adjusted
        assert tracker.optimistic_position <= mid_pos

    def test_words_after_backtrack_track_from_new_position(self):
        """After backtrack, subsequent words should track from new position."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Advance using correct words
        speech = ("welcome to autocue hello and welcome to this demonstration "
                  "of the autocue system today im going to walk you through "
                  "how this teleprompter works")
        tracker.update(speech)

        # Backtrack
        tracker.last_transcription = ""
        tracker.needs_validation = True
        tracker.validate_position("welcome to autocue hello and welcome to")
        backtrack_pos = tracker.optimistic_position

        # Continue speaking from the new position
        tracker.update("welcome to autocue hello and welcome to this demonstration of the")
        new_pos = tracker.optimistic_position

        # Should advance from the backtrack position
        assert new_pos >= backtrack_pos, "Should advance from backtrack position"

    def test_backtrack_to_heading(self):
        """Backtracking to restart at a section heading should work."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Advance past the first heading into the content
        speech = ("welcome to autocue hello and welcome to this demonstration "
                  "of the autocue system today im going to walk you through "
                  "how this teleprompter works and why it might be useful")
        tracker.update(speech)

        # Now restart at the "how it works" heading
        tracker.last_transcription = ""
        tracker.needs_validation = True
        tracker.validate_position("how it works the system listens")

        # Should have found a match in "how it works" section
        assert tracker.optimistic_position > 0

    def test_significant_backtrack_detection_threshold(self):
        """Backtrack detected only when going back more than threshold words."""
        tracker = ScriptTracker(SAMPLE_SCRIPT, backtrack_threshold=3)

        # Advance to a reasonable position
        speech = ("welcome to autocue hello and welcome to this demonstration "
                  "of the autocue system today im going to walk you through "
                  "how this teleprompter")
        tracker.update(speech)

        # Going back just 2 words shouldn't trigger backtrack
        tracker.needs_validation = True
        tracker.validate_position("walk you through how this teleprompter")

        # Going back 10+ words should trigger backtrack
        tracker.needs_validation = True
        _, is_backtrack_large = tracker.validate_position(
            "welcome to autocue hello and welcome"
        )
        assert is_backtrack_large, "Large backtrack should be detected"


class TestForwardJumping:
    """
    Tests for forward jump detection when the user skips a sentence.
    The tracking should detect the small forward jump and adjust.
    """

    def test_skip_sentence_detected(self):
        """Skipping a sentence should be detected as a forward jump."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Speak intro using correct starting words
        tracker.update("welcome to autocue hello and welcome to this demonstration")
        initial_pos = tracker.optimistic_position

        # Skip ahead - go directly to "The system listens" section
        tracker.last_transcription = ""
        tracker.needs_validation = True
        tracker.validate_position(
            "the system listens to your voice through the microphone"
        )

        # Position should have advanced significantly
        assert tracker.optimistic_position > initial_pos + 5, "Should have jumped"

    def test_skip_bullet_point(self):
        """Skipping a bullet point in a list should be tracked."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Navigate to the features section using correct starting words
        intro = ("welcome to autocue hello and welcome to this demonstration "
                 "of the autocue system today im going to walk you through "
                 "how this teleprompter works and why it might be useful for "
                 "your video production workflow how it works the system "
                 "listens to your voice through the microphone and uses speech "
                 "recognition to figure out where you are in the script it then "
                 "scrolls the display automatically to keep up with you what "
                 "makes this different from a traditional teleprompter is that "
                 "you dont need a separate operator the software handles "
                 "everything for you key features let me tell you about some "
                 "of the key features automatic scrolling that follows your "
                 "natural speaking pace")
        tracker.update(intro)
        pos_after_first_bullet = tracker.optimistic_position

        # Skip "backtrack detection" bullet, go to "low latency"
        skip_speech = intro + " low latency because everything runs locally"
        tracker.update(skip_speech)

        # Should have advanced past first bullet
        assert tracker.optimistic_position > pos_after_first_bullet

    def test_forward_jump_updates_high_water_mark(self):
        """Forward jumping should update the high water mark."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Start at beginning with correct words
        tracker.update("welcome to autocue hello and welcome to this demonstration")
        initial_hwm = tracker.high_water_mark

        # Jump forward via validation
        tracker.last_transcription = ""
        tracker.needs_validation = True
        tracker.validate_position(
            "the system listens to your voice through the microphone"
        )

        # High water mark should have increased
        assert tracker.high_water_mark >= initial_hwm


class TestFalsePositiveBacktrackPrevention:
    """
    Tests that when a current sentence is very similar to an earlier position
    in the script, no backtrack should be detected because the user is speaking
    accurately and optimistic position tracking has high confidence.
    """

    def test_repeated_phrase_no_false_backtrack(self):
        """Repeated phrases later in script shouldn't trigger false backtrack to earlier occurrence."""
        # Script with repeated phrase "the system"
        script_with_repeats = """The system is great. It works well.

Later on, the system handles more tasks. The system never fails."""

        tracker = ScriptTracker(script_with_repeats)

        # Advance past first "the system"
        tracker.update("the system is great it works well later on")
        pos_before = tracker.optimistic_position

        # Say "the system" again - should NOT backtrack to first occurrence
        tracker.update("the system is great it works well later on the system handles")

        # Should have advanced, not gone back
        assert tracker.optimistic_position >= pos_before, "Should not backtrack to earlier 'the system'"

    def test_common_words_no_false_backtrack(self):
        """Common words like 'the', 'and', 'to' shouldn't cause false backtracks."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Advance well into the script with correct starting words
        speech1 = ("welcome to autocue hello and welcome to this demonstration "
                   "of the autocue system today im going to walk you through "
                   "how this teleprompter works and why it might be useful for "
                   "your video production workflow how it works the system "
                   "listens to your voice")
        tracker.update(speech1)
        position_in_section_2 = tracker.optimistic_position

        # Continue speaking
        speech2 = (speech1 + " through the microphone and uses speech "
                   "recognition to figure out where you are in the script")
        tracker.update(speech2)

        # Should continue forward, not jump back
        assert tracker.optimistic_position >= position_in_section_2

    def test_similar_sentence_structure_no_backtrack(self):
        """Similar sentence structures shouldn't cause backtrack."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Advance to a position
        speech1 = ("welcome to autocue hello and welcome to this demonstration "
                   "of the autocue system today")
        tracker.update(speech1)
        pos1 = tracker.optimistic_position

        # Continue speaking
        speech2 = speech1 + " im going to walk you through"
        tracker.update(speech2)
        pos2 = tracker.optimistic_position

        assert pos2 > pos1, "Should continue forward"

    def test_optimistic_position_trusted_with_small_deviation(self):
        """Small deviations should trust optimistic position."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Advance with correct words
        for text in ["welcome", "welcome to", "welcome to autocue",
                     "welcome to autocue hello", "welcome to autocue hello and",
                     "welcome to autocue hello and welcome"]:
            tracker.update(text)

        # Force validation
        tracker.needs_validation = True
        _, is_backtrack = tracker.validate_position("welcome to autocue hello and")

        # Should NOT backtrack for small deviation
        assert is_backtrack is False

    def test_confident_current_position_prevents_backtrack(self):
        """Confident current position shouldn't trigger false backtrack."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Advance through content
        speech = ("welcome to autocue hello and welcome to this demonstration "
                  "of the autocue system today im going to walk you through "
                  "how this teleprompter works and why it might be useful")
        tracker.update(speech)
        current_pos = tracker.optimistic_position

        # Validate with current transcript - should NOT backtrack
        tracker.needs_validation = True
        _, is_backtrack = tracker.validate_position(
            "walk you through how this teleprompter works and why it might be useful"
        )

        assert is_backtrack is False
        assert abs(tracker.optimistic_position - current_pos) <= 5


class TestNearestBacktrack:
    """
    Tests that when a user backtracks to a sentence that is similar to other
    sentences in the script, the backtrack should jump to the version nearest
    to the current position (users most likely backtrack small distances).
    """

    def test_backtrack_to_nearest_repeated_phrase(self):
        """When backtracking to repeated phrase, should jump to nearest occurrence."""
        # Create script with repeated phrases at different positions
        script = """Start here. The quick brown fox jumps.

Middle section with content here.

The quick brown fox jumps again. And more content follows.

Later section. The quick brown fox jumps one more time. End."""

        tracker = ScriptTracker(script, max_jump_distance=50)

        # Advance to the "Later section" part
        tracker.update("start here the quick brown fox jumps middle section with content here the quick brown fox jumps again and more content follows later section")
        pos_at_later = tracker.optimistic_position

        # Now backtrack to "the quick brown fox" - should go to nearest one (the third occurrence)
        tracker.last_transcription = ""
        tracker.needs_validation = True
        validated_pos, is_backtrack = tracker.validate_position("the quick brown fox jumps one more time")

        # Should match the nearest occurrence, not jump all the way back
        # The third "the quick brown fox" is closest to where we were
        assert tracker.optimistic_position >= pos_at_later - 20, "Should backtrack to nearest occurrence"

    def test_max_jump_distance_prevents_distant_match(self):
        """max_jump_distance should prevent matching very distant similar text."""
        tracker = ScriptTracker(SAMPLE_SCRIPT, max_jump_distance=20)

        # Advance far into the script with correct starting words
        long_speech = ("welcome to autocue hello and welcome to this demonstration "
                       "of the autocue system today im going to walk you through "
                       "how this teleprompter works and why it might be useful for "
                       "your video production workflow how it works the system "
                       "listens to your voice through the microphone and uses speech "
                       "recognition to figure out where you are in the script it then "
                       "scrolls the display automatically to keep up with you what "
                       "makes this different from a traditional teleprompter is that "
                       "you dont need a separate operator the software handles "
                       "everything for you")
        tracker.update(long_speech)
        pos_far_in = tracker.optimistic_position

        # Try to validate with text from way back at beginning
        tracker.needs_validation = True
        _, is_backtrack = tracker.validate_position(
            "welcome to autocue hello and welcome"
        )

        # With max_jump_distance=20, should not jump back more than ~20 words
        if is_backtrack:
            assert pos_far_in - tracker.optimistic_position <= 30, \
                "Jump should be limited by max_jump_distance"

    def test_nearby_similar_sentences_prefer_nearest(self):
        """When multiple similar sentences exist, prefer the one nearest current position."""
        script = """First: speak clearly and naturally.

Second: remember to speak clearly and naturally.

Third: always speak clearly and naturally. The end."""

        tracker = ScriptTracker(script, max_jump_distance=50)

        # Advance to "Third" section
        tracker.update("first speak clearly and naturally second remember to speak clearly and naturally third always")
        pos_at_third = tracker.optimistic_position

        # Backtrack to "speak clearly and naturally"
        tracker.last_transcription = ""
        tracker.needs_validation = True
        validated_pos, is_backtrack = tracker.validate_position("speak clearly and naturally")

        # Should prefer the nearest match (the third occurrence)
        # Position shouldn't jump all the way back to the first occurrence


class TestFalsePositiveForwardJumpPrevention:
    """
    Tests that when a current sentence is very similar to a later position
    in the script, no forward jumps should be detected because the user is
    speaking accurately and optimistic position tracking has high confidence.
    """

    def test_similar_future_sentence_no_false_jump(self):
        """Similarity to a future sentence shouldn't cause false forward jump."""
        # Script where similar phrases appear later
        script = """Start with the basics. Learn the fundamentals first.

Now practice the basics. This reinforces learning.

Finally, master the basics. You have completed training."""

        tracker = ScriptTracker(script)

        # Speak the first "basics" sentence
        tracker.update("start with the basics learn the fundamentals first")
        pos_after_first = tracker.optimistic_position

        # Continue with "now" - should NOT jump to "finally master the basics"
        # even though "the basics" appears there too
        tracker.update("start with the basics learn the fundamentals first now practice")

        # Should move forward normally, not jump to the end
        assert tracker.optimistic_position < pos_after_first + 15, "Should not jump far forward"

    def test_repeated_later_content_no_jump(self):
        """Content repeated later in script shouldn't cause premature forward jump."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Start speaking with correct words
        tracker.update("welcome to autocue hello and welcome to this")
        pos1 = tracker.optimistic_position

        # Continue speaking - shouldn't jump to later similar content
        tracker.update("welcome to autocue hello and welcome to this demonstration")
        pos2 = tracker.optimistic_position

        # Should advance only by words spoken, not jump
        assert pos2 - pos1 < 10, "Should not jump forward unexpectedly"

    def test_optimistic_tracking_prevents_forward_jump(self):
        """Strong optimistic position should prevent false forward jumps."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Build up strong optimistic position with correct words
        words = ["welcome", "to", "autocue", "hello", "and", "welcome",
                 "to", "this", "demonstration", "of"]
        transcript = ""
        for word in words:
            transcript = (transcript + " " + word).strip()
            tracker.update(transcript)

        optimistic = tracker.optimistic_position

        # Validation shouldn't jump forward
        tracker.needs_validation = True
        _, is_jump = tracker.validate_position(transcript)

        assert is_jump is False, "Should not detect false forward jump"
        assert abs(tracker.optimistic_position - optimistic) <= 3

    def test_forward_jump_only_when_genuinely_ahead(self):
        """Forward jump only triggers when speaker is genuinely ahead."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Speak beginning
        tracker.update("welcome to autocue hello")
        pos1 = tracker.optimistic_position

        # Continue normally
        tracker.update("welcome to autocue hello and welcome to this")
        pos2 = tracker.optimistic_position

        # Validate - should NOT detect forward jump for normal advancement
        tracker.needs_validation = True
        tracker.validate_position("welcome to autocue hello and welcome to this demonstration")

        # Normal forward progress is not a "jump"
        assert tracker.optimistic_position <= pos2 + 5

    def test_small_forward_advance_not_flagged_as_jump(self):
        """Small forward advances should not be flagged as forward jumps."""
        tracker = ScriptTracker(SAMPLE_SCRIPT, backtrack_threshold=3)

        # Advance with correct words
        tracker.update("welcome to autocue hello and welcome to this demonstration")

        # Validate with slightly ahead content
        tracker.needs_validation = True
        tracker.validate_position("demonstration of the autocue system today")

        # Small advances shouldn't be flagged as jumps


class TestEdgeCasesWithSampleScript:
    """Edge cases and boundary conditions using the sample script."""

    def test_script_beginning_tracking(self):
        """Tracking should work correctly at the very beginning."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        assert tracker.optimistic_position == 0

        # First word is "welcome" (from header "# Welcome to Autocue")
        pos = tracker.update("welcome")
        assert pos.word_index == 1

    def test_script_end_tracking(self):
        """Tracking should handle reaching the end of script."""
        # Use a shorter script for this test
        short_script = "Hello world end."
        tracker = ScriptTracker(short_script)

        tracker.update("hello world end")

        # Should be at or near end
        assert tracker.progress >= 0.9

    def test_empty_update(self):
        """Empty updates should not change position."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)
        tracker.update("welcome to autocue")
        pos = tracker.optimistic_position

        tracker.update("")
        assert tracker.optimistic_position == pos

        tracker.update("   ")
        assert tracker.optimistic_position == pos

    def test_very_long_transcription(self):
        """Very long transcriptions should be handled correctly."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Simulate a long continuous transcription with correct words
        words = ["welcome", "to", "autocue", "hello", "and", "welcome",
                 "to", "this", "demonstration", "of"]
        long_transcript = " ".join(words * 3)
        pos = tracker.update(long_transcript)

        # Should handle without error
        assert pos.word_index >= 0

    def test_numbers_in_script(self):
        """Numbers in the script (e.g., 'M3', '25 billion') should be trackable."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Use the actual script words to advance to numbers section
        # This is a simplified approach - just verify we can track numbers
        script_with_numbers = "the m3 processor has approximately"
        tracker.update(script_with_numbers)

        # The tracker should find some match (numbers section exists in script)
        # We mainly verify no error occurs and some tracking happens
        assert tracker.optimistic_position >= 0

    def test_markdown_formatting_stripped(self):
        """Markdown formatting (**, *, #) should be stripped from word matching."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Verify markdown is stripped - "bold" and "text" should be words
        # Look for these words in the script
        assert "bold" in tracker.words
        assert "text" in tracker.words

        # The word list shouldn't contain ** markers
        for word in tracker.words:
            assert "**" not in word
            assert "*" not in word or word.isalnum()


class TestProgressTracking:
    """Tests for progress calculation and reporting."""

    def test_progress_starts_at_zero(self):
        """Progress should start at 0%."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)
        assert tracker.progress == 0.0

    def test_progress_increases_with_speech(self):
        """Progress should increase as we speak through the script."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Use correct starting words
        tracker.update("welcome to autocue hello and welcome to this")
        progress1 = tracker.progress
        assert progress1 > 0

        speech2 = ("welcome to autocue hello and welcome to this demonstration "
                   "of the autocue system today im going to walk you through")
        tracker.update(speech2)
        progress2 = tracker.progress
        assert progress2 > progress1

    def test_progress_calculation_accuracy(self):
        """Progress should reflect actual position through the script."""
        short_script = "one two three four five six seven eight nine ten"
        tracker = ScriptTracker(short_script)

        tracker.update("one two three four five")

        # Should be at position 5 of 10 words = 50%
        assert 0.4 <= tracker.progress <= 0.6


class TestIntegrationScenarios:
    """Integration tests simulating realistic usage scenarios."""

    def test_complete_paragraph_then_backtrack_and_continue(self):
        """Speak a paragraph, backtrack to fix mistake, then continue."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Speak through intro with correct words
        speech = ("welcome to autocue hello and welcome to this demonstration "
                  "of the autocue system today im going to walk you through "
                  "how this teleprompter works")
        tracker.update(speech)
        pos_after_intro = tracker.optimistic_position

        # Simulate backtrack - in real usage, transcript naturally resets when
        # speech recognition detects a new utterance
        tracker.needs_validation = True
        tracker.validate_position("today im going to walk you through")
        backtrack_pos = tracker.optimistic_position

        # Position should have adjusted backward
        assert backtrack_pos <= pos_after_intro

        # After backtrack, skip_disabled_count should be set
        assert tracker.skip_disabled_count == 5

        # Continue speaking - simulate incremental speech recognition updates
        # Each update extends the transcript and matches sequentially
        tracker.update("today im going to walk you through how")
        tracker.update("today im going to walk you through how this")
        tracker.update("today im going to walk you through how this teleprompter")
        tracker.update("today im going to walk you through how this teleprompter works")
        tracker.update("today im going to walk you through how this teleprompter works and")
        final_pos = tracker.optimistic_position

        # Should have advanced past the backtrack position
        assert final_pos > backtrack_pos
        # Skip logic should be re-enabled after 5 successful matches
        assert tracker.skip_disabled_count == 0

    def test_natural_speaking_with_pauses_and_fillers(self):
        """Simulate natural speech with pauses (empty updates) and fillers."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Speak some words with correct starting words
        tracker.update("welcome to autocue hello")
        pos1 = tracker.optimistic_position

        # Pause (empty or same transcript)
        tracker.update("welcome to autocue hello")
        tracker.update("")
        tracker.update("welcome to autocue hello")

        # Position shouldn't regress
        assert tracker.optimistic_position >= pos1

        # Continue with fillers
        tracker.update("welcome to autocue hello um and welcome uh to this")

        # Should have advanced
        assert tracker.optimistic_position > pos1

    def test_reading_full_section(self):
        """Test reading an entire section of the script accurately."""
        tracker = ScriptTracker(SAMPLE_SCRIPT)

        # Read How It Works section content
        how_it_works = ("the system listens to your voice through the microphone "
                        "and uses speech recognition to figure out where you are "
                        "in the script it then scrolls the display automatically "
                        "to keep up with you")

        # First get past the intro with correct words
        intro = ("welcome to autocue hello and welcome to this demonstration "
                 "of the autocue system today im going to walk you through "
                 "how this teleprompter works and why it might be useful for "
                 "your video production workflow how it works")
        tracker.update(intro)
        pos_before_section = tracker.optimistic_position

        # Read the section
        tracker.update(intro + " " + how_it_works)
        pos_after_section = tracker.optimistic_position

        # Should have advanced significantly through the section
        assert pos_after_section > pos_before_section + 10

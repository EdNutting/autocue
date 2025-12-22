"""
Script tracking module that matches spoken words to script text.
Uses fuzzy matching to handle speech recognition errors and
detects when the speaker backtracks to restart a sentence.
"""

import logging
from dataclasses import dataclass, field

import markdown
from rapidfuzz import fuzz

from .expansion_matcher import ExpansionMatcher
from .script_parser import (
    ParsedScript,
    get_speakable_word_list,
    normalize_word,
    parse_script,
    speakable_to_raw_index,
)

logger = logging.getLogger(__name__)


@dataclass
class TrackingState:
    """Encapsulates the state needed for tracking progress through the script."""
    optimistic_position: int = 0
    word_queue: list[str] = field(default_factory=list)
    last_matched_spoken: str | None = None
    expansion_matcher: 'ExpansionMatcher | None' = None
    last_transcription: str = ""  # Last final transcription processed by this state
    current_transcription: str = ""  # Current full transcription being processed

    def clone(self) -> 'TrackingState':
        """Create a deep copy of this tracking state."""
        return TrackingState(
            optimistic_position=self.optimistic_position,
            word_queue=self.word_queue.copy(),
            last_matched_spoken=self.last_matched_spoken,
            expansion_matcher=self.expansion_matcher.clone() if self.expansion_matcher else None,
            last_transcription=self.last_transcription,
            current_transcription=self.current_transcription
        )


@dataclass
class ScriptPosition:
    """Represents the current position in the script."""
    word_index: int  # Index of current word in script (raw token index for UI)
    line_index: int  # Index of current line
    confidence: float  # Match confidence (0-100)
    matched_words: list[str] = field(
        default_factory=list)  # Recently matched words
    # Index in speakable words list (for internal tracking)
    speakable_index: int = 0
    # Whether this update involved a jump (backtrack or forward jump)
    is_jump: bool = False


@dataclass
class ScriptLine:
    """A line from the script with its words."""
    text: str  # Original text
    words: list[str]  # Normalized words
    word_start_index: int  # Index of first word in global word list
    html: str = ""  # HTML rendered version (for Markdown)


@dataclass
class SingleWordMatchResult:
    """Result of trying to match a single word."""
    matched: bool
    advanced: bool
    skipped: bool


@dataclass
class ManyWordMatchResult:
    """Result of trying to match multiple words."""
    matches: int
    advances: int


class ScriptTracker:
    """
    Tracks position in a script based on spoken words.

    Uses a sliding window approach with fuzzy matching to find
    where the speaker is in the script. Detects backtracking
    when the speaker restarts a sentence.

    Internally works with "speakable words" (punctuation expanded to words)
    but returns raw token indices for UI highlighting.
    """

    window_size: int
    match_threshold: float
    jump_threshold: int
    max_jump_distance: int
    max_skip_distance: int

    parsed_script: ParsedScript
    words: list[str]
    lines: list[ScriptLine]
    word_to_line: list[int]

    current_word_index: int
    last_transcription: str
    words_since_validation: int
    skip_disabled_count: int
    last_update_was_jump: bool

    # Two-state system for handling partials
    committed_state: TrackingState
    committed_display_position: int
    speculative_display_position: int
    last_partial_transcription: str

    _expansion_matcher: ExpansionMatcher

    def __init__(
        self,
        script_text: str,
        window_size: int = 8,
        match_threshold: float = 70.0,
        jump_threshold: int = 3,
        max_jump_distance: int = 50,
        max_skip_distance: int = 2
    ) -> None:
        """
        Initialize the script tracker.

        Args:
            script_text: The full script text
            window_size: Number of words to consider for matching
            match_threshold: Minimum fuzzy match score (0-100)
            backtrack_threshold: Minimum words back to count as backtrack
            max_jump_distance: Maximum words to jump in one validation (prevents
                jumping to similar sentences far away in the script)
            max_skip_distance: Maximum script words to skip when looking for a match
                (prevents false matches when speaker deviates from script)
        """
        self.window_size = window_size
        self.match_threshold = match_threshold
        self.jump_threshold = jump_threshold
        self.max_jump_distance = max_jump_distance
        self.max_skip_distance = max_skip_distance

        # Render markdown to HTML first
        rendered_html: str = markdown.markdown(
            script_text,
            extensions=['nl2br', 'sane_lists']
        )

        # Parse script using three-version parser with rendered HTML
        self.parsed_script: ParsedScript = parse_script(
            script_text, rendered_html)

        # Speakable words for matching (what the user will say)
        self.words: list[str] = get_speakable_word_list(self.parsed_script)

        # Build lines for display from raw text (for legacy compatibility)
        self.lines: list[ScriptLine] = []
        self.word_to_line: list[int] = []
        self._build_lines_from_text(script_text)

        # Tracking state (all indices are speakable word indices)
        self.current_word_index = 0
        self.words_since_validation = 0  # Counter for validation triggering
        # Counter to temporarily disable skip logic after backtrack
        self.skip_disabled_count = 0
        self.last_update_was_jump = False  # Track if last update was a jump

        # Dynamic expansion matching (handles numbers/punctuation alternatives)
        self._expansion_matcher = ExpansionMatcher(self.parsed_script)

        # Two-state system: committed (from finals) and speculative (from partials)
        # Committed state - only updated by final transcripts
        self.committed_state = TrackingState(
            optimistic_position=0,
            word_queue=[],
            last_matched_spoken=None,
            expansion_matcher=self._expansion_matcher.clone(),
            last_transcription=""
        )

        # Display positions
        self.committed_display_position: int = 0
        self.speculative_display_position: int = 0

        # Track last partial to avoid reprocessing
        self.last_partial_transcription: str = ""

    # Property accessors for expansion state (delegated to ExpansionMatcher)
    @property
    def active_expansions(self) -> list[list[str]]:
        """Currently valid expansions being matched."""
        return self._expansion_matcher.active_expansions

    @property
    def expansion_match_position(self) -> int:
        """Position within the current expansion being matched."""
        return self._expansion_matcher.match_position

    def _build_lines_from_text(self, text: str) -> None:
        """Build ScriptLine list and word_to_line mapping from raw text.

        This provides line information for display purposes. The word indices
        here correspond to speakable word indices.
        """
        lines: list[str] = text.split('\n')
        speakable_idx: int = 0

        for line_text in lines:
            # Normalize line words the same way as the parser
            line_words: list[str] = [normalize_word(w)
                                     for w in line_text.split() if w.strip()]
            line_words = [w for w in line_words if w]

            start_idx: int = speakable_idx

            # Map each speakable word to this line
            for _ in line_words:
                if speakable_idx < len(self.words):
                    self.word_to_line.append(len(self.lines))
                    speakable_idx += 1

            self.lines.append(ScriptLine(
                text=line_text,
                words=line_words,
                word_start_index=start_idx
            ))

    def _normalize_word(self, word: str) -> str:
        """Normalize a word for matching (lowercase, strip punctuation)."""
        return normalize_word(word)

    def _speakable_to_raw_index(self, speakable_idx: int) -> int:
        """Convert speakable word index to raw token index for UI."""
        return speakable_to_raw_index(self.parsed_script, speakable_idx)

    def _start_expansion_matching(self, speakable_idx: int) -> bool:
        """Initialize expansion matching state for an expandable token."""
        return self._expansion_matcher.start(speakable_idx)

    def _filter_expansions_by_word(self, spoken_word: str) -> bool:
        """Filter active expansions to those matching the spoken word."""
        return self._expansion_matcher.filter_by_word(spoken_word)

    def _is_expansion_complete(self) -> bool:
        """Check if any active expansion has been fully matched."""
        return self._expansion_matcher.is_complete()

    def clear_expansion_state(self) -> None:
        """Clear the expansion matching state."""
        self._expansion_matcher.clear()

    def _get_window_text(self, start_index: int) -> str:
        """Get a window of words starting at the given index."""
        end_index: int = min(start_index + self.window_size, len(self.words))
        return ' '.join(self.words[start_index:end_index])

    def _word_matches(self, spoken: str, script: str) -> bool:
        """Check if a spoken word matches a script word (with fuzzy tolerance).

        Uses stricter matching than window-based matching since we have less context.
        """
        spoken_norm: str = self._normalize_word(spoken)
        script_norm: str = self._normalize_word(script)

        if not spoken_norm or not script_norm:
            return False

        # Exact match
        if spoken_norm == script_norm:
            return True

        # Fuzzy match for speech recognition errors
        return fuzz.ratio(spoken_norm, script_norm) >= self.match_threshold

    def extract_new_words(self, transcription: str, state: TrackingState) -> list[str]:
        """
        Extract only the NEW words from the transcription.
        Compares with state's last_transcription to find what was just spoken.
        """
        current_words: list[str] = [
            w for w in transcription.split() if w.strip()]
        last_words: list[str] = [
            w for w in state.last_transcription.split() if w.strip()]

        # Find where the new words start
        # Usually the new transcription extends the previous one
        if not last_words:
            return current_words

        # Check if current starts with previous (common case)
        match_len: int = 0
        for i, (cur, last) in enumerate(zip(current_words, last_words, strict=False)):
            if self._normalize_word(cur) == self._normalize_word(last):
                match_len = i + 1
            else:
                break

        # Return words after the matching prefix
        if match_len > 0:
            return current_words[match_len:]

        # If no prefix match, this is a new utterance
        return current_words

    # Common filler words to skip during optimistic matching
    FILLER_WORDS: frozenset[str] = frozenset([
        'um', 'uh', 'ah', 'er', 'eh', 'hm', 'hmm', 'mm', 'mhm', 'umm', 'ahh',
        'err', 'ehh', 'uhh', 'mmm', 'huh',
        'like', 'so', 'well', 'anyway', 'basically', 'actually',
        'literally', 'honestly', 'right', 'okay', 'ok', 'yeah', 'yes', 'no'
    ])

    def _is_filler_word(self, word: str) -> bool:
        """Check if a word is a common filler word that can be skipped."""
        return self._normalize_word(word) in self.FILLER_WORDS

    def update(self, transcription: str, is_partial: bool = False) -> ScriptPosition:
        """
        Update position based on new transcription.

        Uses a two-track approach:
        1. Optimistic: Advance word-by-word for immediate UI response
        2. Validation: Triggered to catch errors/backtracks

        Handles partial results by:
        - Detecting when previous words have been corrected
        - Rewinding when corrections affect already-matched words
        - Processing new words optimistically for speed

        Args:
            transcription: The transcribed text
            is_partial: True if this is a partial (in-progress) result

        Returns:
            Updated ScriptPosition (uses optimistic position for responsiveness)
        """
        transcription = transcription.strip()
        if not transcription:
            return self.current_position

        if is_partial:
            return self._update_partial(transcription)
        else:
            return self._update_final(transcription)

    def _update_partial(self, transcription: str) -> ScriptPosition:
        """
        Update position based on partial transcription result.

        Runs matching from committed state with partial words as a speculative "what if".
        Committed state is untouched - only speculative display position is updated.
        """
        # Skip if same as last partial (avoid reprocessing)
        if transcription == self.last_partial_transcription:
            return self.current_position

        print(f"Partial: Processing '{transcription}'")

        # Clone committed state for speculative matching
        speculative_state = self.committed_state.clone()

        # Add all words from the partial transcript to speculative state
        partial_words = [w for w in transcription.split() if w.strip()]
        print(f"Partial: Queuing {len(partial_words)} words from partial")
        for word in partial_words:
            speculative_state.word_queue.append(word)

        # Sync expansion matcher for speculative processing
        if speculative_state.expansion_matcher:
            self._expansion_matcher = speculative_state.expansion_matcher

        # Process words speculatively (don't update validation counter)
        self._process_words(
            speculative_state, self.max_skip_distance, update_validation_counter=False)

        # If words remain unmatched, try recovery by dropping words one at a time
        # This helps recover from single misheard/misspoken words in partial results
        while speculative_state.word_queue:
            initial_queue_len = len(speculative_state.word_queue)
            print(
                f"Partial: {initial_queue_len} unmatched words remain, attempting recovery")

            # Drop the first unmatched word and try again
            dropped_word = speculative_state.word_queue.pop(0)
            print(f"Partial: Dropping word '{dropped_word}' and retrying")

            # Try processing remaining words
            if speculative_state.word_queue:
                self._process_words(
                    speculative_state, self.max_skip_distance, update_validation_counter=False)

                # If we made progress (queue got shorter), keep trying
                if len(speculative_state.word_queue) < initial_queue_len - 1:
                    print(
                        f"Partial: Recovery successful, {initial_queue_len - 1 - len(speculative_state.word_queue)} more words matched")

        # Update speculative display position (never goes backwards)
        if speculative_state.optimistic_position > self.speculative_display_position:
            print(
                f"Partial: Advancing speculative position from {self.speculative_display_position} to {speculative_state.optimistic_position}")
            self.speculative_display_position = speculative_state.optimistic_position

        # Restore committed state expansion matcher
        if self.committed_state.expansion_matcher:
            self._expansion_matcher = self.committed_state.expansion_matcher

        # Update current_word_index to chosen display position
        self.current_word_index = max(
            self.committed_display_position, self.speculative_display_position)

        # Remember this partial
        self.last_partial_transcription = transcription

        return self.current_position

    def _update_final(self, transcription: str) -> ScriptPosition:
        """
        Update position based on final transcription result.

        Updates committed state and clears speculative state.
        """
        print(f"Final: Processing '{transcription}'")

        # Extract only the NEW words from the transcription
        new_words: list[str] = self.extract_new_words(
            transcription, self.committed_state)
        if not new_words:
            self.committed_state.last_transcription = transcription
            # Clear speculative state even if no new words
            self.speculative_display_position = self.committed_display_position
            self.last_partial_transcription = ""
            return self.current_position

        print("-------------------------------------------")
        print(
            f"Tracker: Word queue '{' '.join(self.committed_state.word_queue)}'")
        print(f"Tracker: New words '{' '.join(new_words)}'")
        for word in new_words:
            self.committed_state.word_queue.append(word)
        print(
            f"Tracker: Updated word queue '{' '.join(self.committed_state.word_queue)}'")

        # Sync expansion matcher
        if self.committed_state.expansion_matcher:
            self._expansion_matcher = self.committed_state.expansion_matcher

        # Store the full transcription in state for jump detection context
        self.committed_state.current_transcription = transcription

        # Process words on committed state
        self._process_words(self.committed_state, 2 * self.max_skip_distance)

        # If words remain unmatched, try recovery by dropping words one at a time
        # This helps recover from single misheard/misspoken words
        while self.committed_state.word_queue:
            initial_queue_len = len(self.committed_state.word_queue)
            print(
                f"Final: {initial_queue_len} unmatched words remain, attempting recovery")

            # Drop the first unmatched word and try again
            dropped_word = self.committed_state.word_queue.pop(0)
            print(f"Final: Dropping word '{dropped_word}' and retrying")

            # Try processing remaining words
            if self.committed_state.word_queue:
                self._process_words(self.committed_state,
                                    2 * self.max_skip_distance)

                # If we made progress (queue got shorter), keep trying
                if len(self.committed_state.word_queue) < initial_queue_len - 1:
                    print(
                        f"Final: Recovery successful, {initial_queue_len - 1 - len(self.committed_state.word_queue)} more words matched")

        # Clear any remaining words that still couldn't be matched
        if self.committed_state.word_queue:
            print(
                f"Final: Discarding {len(self.committed_state.word_queue)} remaining unmatched words")
            self.committed_state.word_queue.clear()

        # Update committed display position
        direction = "forward" if self.committed_display_position < self.committed_state.optimistic_position else "backward"
        print(
            f"Final({direction}): Moving committed position from {self.committed_display_position} to {self.committed_state.optimistic_position}")
        self.committed_display_position = self.committed_state.optimistic_position

        # Update expansion matcher in committed state
        self.committed_state.expansion_matcher = self._expansion_matcher.clone()

        # Clear speculative state (will be rebuilt from next partial)
        self.speculative_display_position = self.committed_display_position
        self.last_partial_transcription = ""

        # Update current_word_index to committed display position
        self.current_word_index = self.committed_display_position

        # Store transcription for next comparison
        self.committed_state.last_transcription = transcription

        return self.current_position

    def reset(self) -> None:
        """Reset tracking to the beginning of the script."""
        # Reset tracking state
        self.current_word_index = 0
        self.words_since_validation = 0
        self.skip_disabled_count = 0
        # Reset committed state
        self.committed_state = TrackingState(
            optimistic_position=0,
            word_queue=[],
            last_matched_spoken=None,
            expansion_matcher=self._expansion_matcher.clone(),
            last_transcription=""
        )
        # Reset display positions
        self.committed_display_position = 0
        self.speculative_display_position = 0
        self.last_partial_transcription = ""
        # Reset expansion state
        self.clear_expansion_state()

    def jump_to(self, word_index: int) -> None:
        """Jump to a specific position in the script."""
        word_index = max(0, min(word_index, len(
            self.words) - 1)) if self.words else 0

        self.reset()

        self.current_word_index = word_index
        self.committed_state.optimistic_position = word_index
        self.committed_display_position = word_index
        self.speculative_display_position = word_index

    def get_display_lines(
        self,
        past_lines: int = 1,
        future_lines: int = 10
    ) -> tuple[list[ScriptLine], int, int]:
        """
        Get lines to display around the current position.

        Args:
            past_lines: Number of lines before current to show
            future_lines: Number of lines after current to show

        Returns:
            Tuple of (lines_to_display, current_line_index_in_list, current_word_offset)
        """
        current_line: int = self._word_to_line_index(self.current_word_index)

        start_line: int = max(0, current_line - past_lines)
        end_line: int = min(len(self.lines), current_line + future_lines + 1)

        display_lines: list[ScriptLine] = self.lines[start_line:end_line]
        current_in_display: int = current_line - start_line

        # Calculate word offset within current line
        word_offset: int
        if current_line < len(self.lines):
            line: ScriptLine = self.lines[current_line]
            word_offset = self.current_word_index - line.word_start_index
        else:
            word_offset = 0

        return display_lines, current_in_display, word_offset

    def _process_words(self, state: TrackingState, max_skip_distance: int, update_validation_counter: bool = True) -> None:
        """Process words in the queue against the script, updating the state.

        Args:
            state: The tracking state to update
            max_skip_distance: Maximum script words to skip when looking for matches
            update_validation_counter: Whether to update words_since_validation counter (only for final updates)
        """
        # Clear jump flag at start of processing (unless we detect one)
        if update_validation_counter:
            self.last_update_was_jump = False

        previous_length = len(state.word_queue) + 1
        while bool(state.word_queue) and previous_length > len(state.word_queue):
            previous_length = len(state.word_queue)

            # Try to advance optimistically based on new words
            spoken_word = state.word_queue.pop(0)
            print(f"Exact-match detection: Testing word '{spoken_word}'")
            match_result = self._match_single_word(spoken_word, state)

            if match_result.matched:
                state.last_matched_spoken = spoken_word

                if match_result.advanced:
                    # Update optimistic position
                    state.optimistic_position += 1

                    # Track words for validation triggering (only for final updates)
                    if update_validation_counter:
                        self.words_since_validation += 1
                        # Decrement skip_disabled_count on successful matches
                        if self.skip_disabled_count > 0:
                            self.skip_disabled_count -= 1
            else:
                state.last_matched_spoken = None

                state.word_queue.insert(0, spoken_word)
                # Only use skip logic if not disabled
                if self.skip_disabled_count == 0:
                    match_result = self._match_words_with_skipping(
                        state, max_skip_distance)
                else:
                    match_result = ManyWordMatchResult(0, 0)
                if match_result.matches > 0:
                    # Update optimistic position
                    state.optimistic_position += match_result.advances

                    # Track words for validation triggering (only for final updates)
                    if update_validation_counter:
                        self.words_since_validation += match_result.advances
                # Else check for backtrack / forward jump
                elif len(state.word_queue) >= 5:  # allow_jump_detection
                    # No words matched - this could indicate a backtrack or forward jump!
                    # Immediately validate if we have enough new words to work with
                    _, is_jump = self._detect_jump_internal(state)
                    if update_validation_counter and is_jump:
                        self.last_update_was_jump = True

    def _match_single_word(self, spoken_word: str, state: TrackingState) -> SingleWordMatchResult:
        """
        Try to advance position based on new spoken words.

        Uses dynamic expansion matching for numbers/punctuation:
        - Tracks which expansions are still valid as words are matched
        - Filters out expansions that don't match
        - Advances position when an expansion is complete

        Also skips filler words, repeated words, and allows skipping script words.
        Returns whether the word was matched, and whether to advance in the script.
        """
        optimistic_position = state.optimistic_position

        if optimistic_position >= len(self.words):
            return SingleWordMatchResult(False, False, False)

        spoken_norm: str = self._normalize_word(spoken_word)

        # Skip empty words
        if not spoken_norm:
            return SingleWordMatchResult(True, False, True)

        # 1. Try detection against the script first
        #    - optimistic assumption that the speaker didn't mess up
        #    1.a. Are we matching an expansion? If so, try to continue the match
        #    1.b. Else, try to match against the script
        # 2. Else, skip filler words
        # 3. Else, skip repeated words

        # Check if we're in the middle of matching an expansion
        if self.active_expansions:
            # Try to continue the current expansion
            if self._filter_expansions_by_word(spoken_norm):
                # Check if expansion is complete
                if self._is_expansion_complete():
                    self.clear_expansion_state()
                    return SingleWordMatchResult(True, True, False)
                return SingleWordMatchResult(True, False, False)
            else:
                # Word doesn't match any remaining expansion
                # Expansion ended early - advance position and try this word at next pos
                self.clear_expansion_state()

        # Not in an expansion - try to start one or match normally
        speakable_words = self.parsed_script.speakable_words

        if optimistic_position < len(speakable_words):
            sw = speakable_words[optimistic_position]
            if sw.is_expansion:
                # This is an expandable token - start expansion matching
                self._start_expansion_matching(optimistic_position)
                if self._filter_expansions_by_word(spoken_norm):
                    # Check if single-word expansion is complete
                    if self._is_expansion_complete():
                        self.clear_expansion_state()
                        return SingleWordMatchResult(True, True, False)
                    return SingleWordMatchResult(True, False, False)
                else:
                    # First word doesn't match any expansion - clear and fall through
                    self.clear_expansion_state()
            else:
                # Regular word - try direct matching
                # Exact match
                if spoken_norm == sw or fuzz.ratio(spoken_norm, sw.text) >= self.match_threshold:
                    return SingleWordMatchResult(True, True, False)

        if self._is_filler_word(spoken_norm):
            return SingleWordMatchResult(True, False, True)

        # Skip repeated words (same word spoken twice in a row)
        if state.last_matched_spoken and spoken_norm == self._normalize_word(state.last_matched_spoken):
            return SingleWordMatchResult(True, False, True)

        return SingleWordMatchResult(False, False, False)

    def _match_words_with_skipping(self, state: TrackingState, max_skip_distance: int) -> ManyWordMatchResult:
        def try_matching(variant_name: str, optimism_mode: int, tmp_optimistic_position: int):
            # Clone state to work on - only copy back if successful
            temp_state = state.clone()
            temp_state.optimistic_position = tmp_optimistic_position

            speakable_words = self.parsed_script.speakable_words
            print(
                f"Skip detection ({variant_name}): Current word queue: '{' '.join(temp_state.word_queue)}'"
            )

            skip_count: int = 0
            match_count: int = 0
            advance_count: int = 0

            previous_skip_count: int = -1
            previous_match_count: int = -1
            while (
                # While there are some words left to process
                bool(temp_state.word_queue)
                # And we're allowed to skip words
                and skip_count <= max_skip_distance
                # And we're making some progress
                and (skip_count > previous_skip_count or match_count > previous_match_count)
                # And we're in-bounds of the script
                and temp_state.optimistic_position < len(speakable_words)
            ):
                previous_skip_count = skip_count
                previous_match_count = match_count

                spoken_word = temp_state.word_queue.pop(0)
                sw = speakable_words[temp_state.optimistic_position]

                # If the current script word is longer than the current spoken word,
                # double check to see if combining the current and next spoken words
                # matches the current script word.
                # (e.g. ["every", "thing"] -> "everything")
                #
                # We know we're calling this after failing to match a single word in
                # the caller of this function. So we're safe to try to match longer
                # words right away.
                if bool(temp_state.word_queue) and not sw.is_expansion and len(sw.text) >= len(spoken_word) * 1.5:
                    next_spoken_word = temp_state.word_queue[0]
                    print(
                        f"Skip detection ({variant_name}): Testing compound spoken '{spoken_word + next_spoken_word}' against scripted '{sw.text}'"
                    )
                    if sw.text == spoken_word + next_spoken_word:
                        temp_state.word_queue.pop(0)
                        match_count += 1 + skip_count
                        advance_count += 1
                        temp_state.optimistic_position += 1
                        temp_state.last_matched_spoken = None
                        # We matched a word, so clear the skip state
                        skip_count = 0
                        break

                print(
                    f"Skip detection ({variant_name}): Testing spoken '{spoken_word}' against scripted '{sw.text}'"
                )

                # Try to skip over the odd mismatched word (which can be a result of
                # the speaker mispeaking or the transcription picking the wrong word
                # compared to what the speaker actually spoke)
                match_result = self._match_single_word(spoken_word, temp_state)
                # Did we find a matching word?
                if match_result.matched:
                    temp_state.last_matched_spoken = spoken_word

                    match_count += 1 + skip_count

                    if match_result.advanced:
                        advance_count += 1
                        temp_state.optimistic_position += 1

                    # We matched a word, so clear the skip state
                    skip_count = 0
                    break
                else:
                    # Skip one word
                    skip_count += 1
                    advance_count += optimism_mode
                    temp_state.optimistic_position += optimism_mode
                    temp_state.last_matched_spoken = None

                    if sw.is_expansion:
                        self.clear_expansion_state()

            # If we succeeded in matching, copy temp_state back to state
            # BUT don't copy optimistic_position - we'll return advances instead
            # and let the caller update the position
            if match_count > 0:
                state.word_queue = temp_state.word_queue
                state.last_matched_spoken = temp_state.last_matched_spoken
                if temp_state.expansion_matcher:
                    state.expansion_matcher = temp_state.expansion_matcher

            print(
                f"Skip detection ({variant_name}): Final word queue: '{str(list(temp_state.word_queue))}'"
            )

            return ManyWordMatchResult(match_count, advance_count)

        # Offset starting position in the script
        # Technically this mechanism allows a slip of 2 * max_skip_distance but who cares
        for offset in range(0, max_skip_distance + 1):
            # Transcript and Script words skipped together
            result = try_matching(
                f"T+S[{offset}]", 1, state.optimistic_position + offset)
            if result.matches > 0:
                # Add offset to advances since caller will add this to state.optimistic_position
                return ManyWordMatchResult(result.matches, result.advances + offset)

            # Only transcript words skipped
            result = try_matching(
                f"T@S[{offset}]", 0, state.optimistic_position + offset)
            if result.matches > 0:
                # Add offset to advances since caller will add this to state.optimistic_position
                return ManyWordMatchResult(result.matches, result.advances + offset)

        return ManyWordMatchResult(0, 0)

    def _detect_jump_internal(self, state: TrackingState) -> tuple[int, bool]:
        """
        Detect if the speaker has jumped to a different part of the script.

        Uses window-based fuzzy matching to find where the unmatched words
        in the queue actually appear in the script. If they're significantly
        far from the current position, treats it as a jump (backward or forward).

        Jumps are the "uncommon" path - the threshold is set high to avoid
        jumping around unnecessarily, but we do want to catch significant
        backtracks or forward skips.

        Args:
            state: The tracking state to check and potentially update

        Returns:
            Tuple of (new_position, is_jump) where is_jump indicates whether
            a jump (backward or forward) was detected and applied
        """
        # Need enough words to reliably detect position
        if len(state.word_queue) < 3:
            print(
                f"Jump detection: Skipping (insufficient words: {len(state.word_queue)} < 3)")
            return state.optimistic_position, False

        # Use full current transcription if available (provides better context)
        # Otherwise fall back to word queue
        transcription = state.current_transcription if state.current_transcription else ' '.join(
            state.word_queue)
        print(
            f"Jump detection: Checking transcription '{transcription}' at position {state.optimistic_position}")

        # Use window-based matching to find where these words are
        best_index, confidence = self._find_best_match(transcription)
        print(
            f"Jump detection: Best match at index {best_index} with confidence {confidence:.1f}")

        # Low confidence match - can't determine position reliably
        if confidence < self.match_threshold:
            print(
                f"Jump detection: Skipping (low confidence: {confidence:.1f} < {self.match_threshold})")
            return state.optimistic_position, False

        # Calculate deviation from optimistic position
        position_diff = state.optimistic_position - best_index
        print(
            f"Jump detection: Position diff = {position_diff} (optimistic={state.optimistic_position}, best={best_index})")

        # If deviation is small, trust the optimistic position
        # This prevents repeated words from causing false jump detection
        if abs(position_diff) <= self.jump_threshold:
            print(
                f"Jump detection: Skipping (small deviation: {abs(position_diff)} <= {self.jump_threshold})")
            return state.optimistic_position, False

        # Before considering a jump, check if the transcript words
        # match what we expect at/near the optimistic position.
        # If they do, trust the optimistic position.
        transcript_words = [w for w in transcription.split() if w.strip()]
        if self._transcript_matches_position(transcript_words, state.optimistic_position):
            print("Jump detection: Skipping (transcript matches current position)")
            return state.optimistic_position, False

        # Reject jumps that are too large - prevents jumping to similar sentences
        # far away in the script (e.g., repeated phrases in different paragraphs)
        jump_distance = abs(position_diff)
        if jump_distance > self.max_jump_distance:
            print(
                f"Jump detection: Skipping (jump too large: {jump_distance} > {self.max_jump_distance})")
            return state.optimistic_position, False

        # Determine jump type
        # Backtrack: validated position is significantly behind where we currently are
        is_backtrack = (
            best_index < state.optimistic_position - self.jump_threshold and
            state.optimistic_position > 0 and
            position_diff > self.jump_threshold
        )

        # Forward jump: validated position is significantly ahead of where we are
        is_forward_jump = (
            position_diff < -self.jump_threshold and
            best_index > state.optimistic_position
        )

        if not (is_backtrack or is_forward_jump):
            print(
                f"Jump detection: Skipping (not classified as jump: backtrack={is_backtrack}, forward={is_forward_jump})")
            return state.optimistic_position, False

        # Find where the first transcript word actually matches within the window
        # (best_index is where the window starts, not necessarily where first word is)
        first_word = self._normalize_word(transcript_words[0])
        transcript_start_offset = 0

        for offset in range(min(self.window_size, len(self.words) - best_index)):
            if best_index + offset < len(self.words) and self._word_matches(first_word, self.words[best_index + offset]):
                transcript_start_offset = offset
                break

        # Calculate actual position: where transcript starts + length of transcript
        # This positions us AFTER the spoken words (ready for the next word)
        actual_start = best_index + transcript_start_offset
        adjusted_position = min(
            actual_start + len(transcript_words),
            len(self.words) - 1 if self.words else 0
        )

        jump_type = "BACKTRACK" if is_backtrack else "FORWARD_JUMP"
        print(
            f"{jump_type}: from position {state.optimistic_position} to {adjusted_position} "
            f"(best_idx={best_index}, offset={transcript_start_offset}, "
            f"transcript_len={len(transcript_words)})"
        )

        # Update state to new position
        state.optimistic_position = adjusted_position
        state.word_queue.clear()  # Words have been processed
        state.last_matched_spoken = None

        # Disable skip logic temporarily after a backtrack to prevent stale word matching
        if is_backtrack:
            print("Jump detection: Disabling skip logic for next 3 matches")
            self.skip_disabled_count = 3

        # Clear expansion state - we're at a new position
        if state.expansion_matcher:
            state.expansion_matcher.clear()
        self.clear_expansion_state()

        return adjusted_position, True

    def detect_jump(self, transcription: str) -> tuple[int, bool]:
        """
        Public API for jump detection - accepts a transcription string.

        This is for compatibility with tests and external callers.
        Internally, creates a temporary state with the transcription words
        and calls the internal jump detection logic.

        Args:
            transcription: The transcribed text to check for jumps

        Returns:
            Tuple of (new_position, is_jump) where is_jump indicates whether
            a jump was detected
        """
        # Create a temporary state with the transcription words
        temp_state = self.committed_state.clone()
        temp_state.word_queue = [w for w in transcription.split() if w.strip()]
        # Provide full context for jump detection
        temp_state.current_transcription = transcription

        # Detect jump using internal method
        new_position, is_jump = self._detect_jump_internal(temp_state)

        # Reset validation counter (whether or not a jump was detected)
        self.words_since_validation = 0

        # Track if this was a jump
        self.last_update_was_jump = is_jump

        if is_jump:
            # Apply changes to committed state
            self.committed_state.optimistic_position = temp_state.optimistic_position
            self.committed_state.word_queue = temp_state.word_queue
            self.committed_state.last_matched_spoken = temp_state.last_matched_spoken

            # Update display positions
            self.committed_display_position = temp_state.optimistic_position
            self.speculative_display_position = temp_state.optimistic_position
            self.current_word_index = temp_state.optimistic_position

        return new_position, is_jump

    def _find_best_match(self, spoken_words: str) -> tuple[int, float]:
        """
        Find the best matching position in the script for spoken words.

        Args:
            spoken_words: The transcribed spoken text

        Returns:
            Tuple of (best_word_index, confidence_score)
        """
        if not spoken_words.strip():
            return self.current_word_index, 0.0

        # Normalize spoken words
        spoken_normalized: str = ' '.join(
            self._normalize_word(w) for w in spoken_words.split() if w.strip()
        )

        if not spoken_normalized:
            return self.current_word_index, 0.0

        # Search within max_jump_distance to avoid matching similar text far away
        # This prevents jumping to repeated phrases in distant paragraphs
        search_start: int = max(
            0, self.current_word_index - self.max_jump_distance)
        search_end: int = min(
            len(self.words),
            self.current_word_index + self.max_jump_distance
        )

        # Also always search from the beginning of current line
        if self.current_word_index < len(self.word_to_line):
            current_line: int = self.word_to_line[self.current_word_index]
            line_start: int = self.lines[current_line].word_start_index
            search_start = min(search_start, line_start)

        best_index: int = self.current_word_index
        best_score: float = 0.0

        # Slide window through search range
        for i in range(search_start, search_end):
            window_text: str = self._get_window_text(i)
            if not window_text:
                continue

            # Use token_set_ratio for better partial matching
            score: float = fuzz.token_set_ratio(spoken_normalized, window_text)

            # Penalize very short windows - they can give false positives
            # when a common word like "you" or "the" matches by itself
            window_word_count: int = len(window_text.split())
            spoken_word_count: int = len(spoken_normalized.split())
            if window_word_count < min(self.window_size, spoken_word_count):
                # Reduce score proportionally to how short the window is
                coverage: float = window_word_count / \
                    min(self.window_size, spoken_word_count)
                score = score * coverage

            # Slight preference for forward progress (avoid getting stuck)
            if i >= self.current_word_index:
                score += 2

            if score > best_score:
                best_score = score
                best_index = i

        return best_index, best_score

    def _transcript_matches_position(self, transcript_words: list[str], position: int) -> bool:
        """
        Check if the transcript words match the script around the given position.
        Used to verify if the optimistic position is reasonable.
        """
        if not transcript_words or position >= len(self.words):
            return False

        # Look at a window around the position (a few words before and after)
        start: int = max(0, position - 3)
        end: int = min(len(self.words), position + 3)
        nearby_words: list[str] = self.words[start:end]

        if not nearby_words:
            return False

        # Check if the last few transcript words match any nearby script words
        # This indicates we're in the right area
        last_transcript: list[str] = transcript_words[-3:] if len(
            transcript_words) >= 3 else transcript_words
        matches: int = 0
        for tw in last_transcript:
            tw_norm: str = self._normalize_word(tw)
            for sw in nearby_words:
                if self._word_matches(tw_norm, sw):
                    matches += 1
                    break

        # If most of the recent words match nearby script, trust the position
        threshold: float = len(last_transcript) * 0.5
        return matches >= threshold

    def _word_to_line_index(self, word_index: int) -> int:
        """Convert a word index to a line index."""
        if word_index >= len(self.word_to_line):
            return len(self.lines) - 1 if self.lines else 0
        return self.word_to_line[word_index]

    @property
    def optimistic_position(self) -> int:
        """Get the current optimistic position (speakable word index).

        For compatibility with tests and external API.
        Maps to the committed state's optimistic position.
        """
        return self.committed_state.optimistic_position

    @optimistic_position.setter
    def optimistic_position(self, value: int) -> None:
        """Set the optimistic position.

        For compatibility with tests. Updates the committed state.
        """
        self.committed_state.optimistic_position = value

    @property
    def allow_jump_detection(self) -> bool:
        """Check if we have enough words to trigger jump detection.

        For compatibility with tests. Returns True when we have accumulated
        enough new words since last validation to trigger jump detection.
        """
        return self.words_since_validation >= 5

    @property
    def progress(self) -> float:
        """Get overall progress through the script (0.0 to 1.0)."""
        total_raw: int = self.parsed_script.total_raw_tokens
        if total_raw == 0:
            return 0.0
        raw_index: int = self._speakable_to_raw_index(self.current_word_index)
        return raw_index / total_raw

    @property
    def current_position(self) -> ScriptPosition:
        """Get the current position without updating."""
        raw_index: int = self._speakable_to_raw_index(self.current_word_index)
        # Optimistic matching assumes 100% confidence
        return ScriptPosition(
            word_index=raw_index,
            line_index=self._word_to_line_index(self.current_word_index),
            confidence=100.0,
            speakable_index=self.current_word_index,
            is_jump=self.last_update_was_jump
        )

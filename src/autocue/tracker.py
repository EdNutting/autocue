"""
Script tracking module that matches spoken words to script text.
Uses fuzzy matching to handle speech recognition errors and
detects when the speaker backtracks to restart a sentence.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, FrozenSet
from rapidfuzz import fuzz
import markdown

from . import debug_log
from .expansion_matcher import ExpansionMatcher
from .script_parser import (
    ParsedScript, parse_script, normalize_word,
    speakable_to_raw_index, get_speakable_word_list
)

logger = logging.getLogger(__name__)


@dataclass
class ScriptPosition:
    """Represents the current position in the script."""
    word_index: int  # Index of current word in script (raw token index for UI)
    line_index: int  # Index of current line
    confidence: float  # Match confidence (0-100)
    matched_words: List[str] = field(
        default_factory=list)  # Recently matched words
    is_backtrack: bool = False  # True if this is a backtrack from previous position
    # Index in speakable words list (for internal tracking)
    speakable_index: int = 0


@dataclass
class ScriptLine:
    """A line from the script with its words."""
    text: str  # Original text
    words: List[str]  # Normalized words
    word_start_index: int  # Index of first word in global word list
    html: str = ""  # HTML rendered version (for Markdown)


class ScriptTracker:
    """
    Tracks position in a script based on spoken words.

    Uses a sliding window approach with fuzzy matching to find
    where the speaker is in the script. Detects backtracking
    when the speaker restarts a sentence.

    Internally works with "speakable words" (punctuation expanded to words)
    but returns raw token indices for UI highlighting.
    """

    def __init__(
        self,
        script_text: str,
        window_size: int = 8,
        match_threshold: float = 70.0,
        backtrack_threshold: int = 3,
        max_jump_distance: int = 50,
        max_skip_distance: int = 2
    ):
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
        self.backtrack_threshold = backtrack_threshold
        self.max_jump_distance = max_jump_distance
        self.max_skip_distance = max_skip_distance

        # Render markdown to HTML first
        rendered_html = markdown.markdown(
            script_text,
            extensions=['nl2br', 'sane_lists']
        )

        # Parse script using three-version parser with rendered HTML
        self.parsed_script: ParsedScript = parse_script(
            script_text, rendered_html)

        # Speakable words for matching (what the user will say)
        self.words: List[str] = get_speakable_word_list(self.parsed_script)

        # Build lines for display from raw text (for legacy compatibility)
        self.lines: List[ScriptLine] = []
        self.word_to_line: List[int] = []
        self._build_lines_from_text(script_text)

        # Tracking state (all indices are speakable word indices)
        self.current_word_index = 0
        self.high_water_mark = 0  # Furthest position reached
        # Recent match positions for smoothing
        self.recent_matches: List[int] = []

        # Optimistic tracking state
        self.optimistic_position = 0  # Fast-path position for immediate UI updates
        self.last_transcription = ""  # Track previous transcript to detect new words
        self.words_since_validation = 0  # Counter for validation triggering
        self.needs_validation = False  # Flag when validation should run

        # After backtrack, disable skip logic until we've matched a few words
        # This prevents old transcript words from incorrectly matching future positions
        self.skip_disabled_count = 0  # Number of words to disable skip for

        # Dynamic expansion matching (handles numbers/punctuation alternatives)
        self._expansion_matcher = ExpansionMatcher(self.parsed_script)

    # Property accessors for expansion state (delegated to ExpansionMatcher)
    @property
    def active_expansions(self) -> List[List[str]]:
        """Currently valid expansions being matched."""
        return self._expansion_matcher.active_expansions

    @property
    def expansion_match_position(self) -> int:
        """Position within the current expansion being matched."""
        return self._expansion_matcher.match_position

    def _build_lines_from_text(self, text: str):
        """Build ScriptLine list and word_to_line mapping from raw text.

        This provides line information for display purposes. The word indices
        here correspond to speakable word indices.
        """
        lines = text.split('\n')
        speakable_idx = 0

        for line_text in lines:
            # Normalize line words the same way as the parser
            line_words = [normalize_word(w)
                          for w in line_text.split() if w.strip()]
            line_words = [w for w in line_words if w]

            start_idx = speakable_idx

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

    def _get_expansion_first_words(self, speakable_idx: int) -> List[str]:
        """Get all possible FIRST words that could start matching at this position."""
        return self._expansion_matcher.get_first_words(speakable_idx)

    def _start_expansion_matching(self, speakable_idx: int) -> bool:
        """Initialize expansion matching state for an expandable token."""
        return self._expansion_matcher.start(speakable_idx)

    def _filter_expansions_by_word(self, spoken_word: str) -> bool:
        """Filter active expansions to those matching the spoken word."""
        return self._expansion_matcher.filter_by_word(spoken_word)

    def _is_expansion_complete(self) -> bool:
        """Check if any active expansion has been fully matched."""
        return self._expansion_matcher.is_complete()

    def _clear_expansion_state(self):
        """Clear the expansion matching state."""
        self._expansion_matcher.clear()

    def _get_window_text(self, start_index: int) -> str:
        """Get a window of words starting at the given index."""
        end_index = min(start_index + self.window_size, len(self.words))
        return ' '.join(self.words[start_index:end_index])

    def _word_matches(self, spoken: str, script: str) -> bool:
        """Check if a spoken word matches a script word (with fuzzy tolerance).

        Uses stricter matching than window-based matching since we have less context.
        """
        spoken_norm = self._normalize_word(spoken)
        script_norm = self._normalize_word(script)

        if not spoken_norm or not script_norm:
            return False

        # Exact match
        if spoken_norm == script_norm:
            return True

        # Fuzzy match for speech recognition errors
        # Use stricter threshold (75%) than window matching (65%)
        return fuzz.ratio(spoken_norm, script_norm) >= 75

    def _word_matches_at_position(self, spoken: str, speakable_idx: int) -> bool:
        """Check if a spoken word could START matching at a speakable position.

        For expandable tokens, checks if the word matches the first word
        of any possible expansion. For regular words, checks direct match.
        """
        spoken_norm = self._normalize_word(spoken)
        if not spoken_norm:
            return False

        first_words = self._get_expansion_first_words(speakable_idx)
        for word in first_words:
            # Exact match
            if spoken_norm == word:
                return True
            # Fuzzy match
            if fuzz.ratio(spoken_norm, word) >= 75:
                return True

        return False

    def _extract_new_words(self, transcription: str) -> List[str]:
        """
        Extract only the NEW words from the transcription.
        Compares with last_transcription to find what was just spoken.
        """
        current_words = [w for w in transcription.split() if w.strip()]
        last_words = [w for w in self.last_transcription.split() if w.strip()]

        # Find where the new words start
        # Usually the new transcription extends the previous one
        if not last_words:
            return current_words

        # Check if current starts with previous (common case)
        match_len = 0
        for i, (cur, last) in enumerate(zip(current_words, last_words)):
            if self._normalize_word(cur) == self._normalize_word(last):
                match_len = i + 1
            else:
                break

        # Return words after the matching prefix
        if match_len > 0:
            return current_words[match_len:]

        # If no prefix match, this might be a new utterance
        # Return all current words but be conservative
        return current_words[-3:] if len(current_words) > 3 else current_words

    def _transcript_matches_position(self, transcript_words: List[str], position: int) -> bool:
        """
        Check if the transcript words match the script around the given position.
        Used to verify if the optimistic position is reasonable.
        """
        if not transcript_words or position >= len(self.words):
            return False

        # Look at a window around the position (a few words before and after)
        start = max(0, position - 3)
        end = min(len(self.words), position + 3)
        nearby_words = self.words[start:end]

        if not nearby_words:
            return False

        # Check if the last few transcript words match any nearby script words
        # This indicates we're in the right area
        last_transcript = transcript_words[-3:] if len(
            transcript_words) >= 3 else transcript_words
        matches = 0
        for tw in last_transcript:
            tw_norm = self._normalize_word(tw)
            for sw in nearby_words:
                if self._word_matches(tw_norm, sw):
                    matches += 1
                    break

        # If most of the recent words match nearby script, trust the position
        threshold = len(last_transcript) * 0.5
        return matches >= threshold

    # Common filler words to skip during optimistic matching
    FILLER_WORDS = frozenset([
        'um', 'uh', 'ah', 'er', 'eh', 'hm', 'hmm', 'mm', 'mhm',
        'like', 'so', 'well', 'anyway', 'basically', 'actually',
        'literally', 'honestly', 'right', 'okay', 'ok', 'yeah', 'yes', 'no'
    ])

    def _is_filler_word(self, word: str) -> bool:
        """Check if a word is a common filler word that can be skipped."""
        return self._normalize_word(word) in self.FILLER_WORDS

    def _advance_optimistically(self, new_words: List[str]) -> int:
        """
        Try to advance position based on new spoken words.

        Uses dynamic expansion matching for numbers/punctuation:
        - Tracks which expansions are still valid as words are matched
        - Filters out expansions that don't match
        - Advances position when an expansion is complete

        Also skips filler words, repeated words, and allows skipping script words.
        Returns the number of script positions we advanced.
        """
        if not new_words or self.optimistic_position >= len(self.words):
            return 0

        positions_advanced = 0
        pos = self.optimistic_position
        consecutive_misses = 0  # Track consecutive non-matching words
        max_consecutive_misses = 3  # Allow skipping up to 3 spoken words
        last_matched_spoken = None  # Track last matched word to detect repetitions

        word_idx = 0
        while word_idx < len(new_words):
            if pos >= len(self.words):
                break

            spoken_word = new_words[word_idx]
            spoken_norm = self._normalize_word(spoken_word)

            # Skip empty words
            if not spoken_norm:
                word_idx += 1
                continue

            # Skip filler words - but only if they DON'T match the current script position
            # This prevents skipping "like" when the script actually says "like"
            if self._is_filler_word(spoken_word):
                # Check if this filler word matches the script at current position
                if not self._word_matches_at_position(spoken_word, pos):
                    consecutive_misses = 0  # Filler words don't count as misses
                    debug_log.log_server_word(
                        pos, f"[filler:{spoken_word}]", "skip_filler")
                    word_idx += 1
                    continue
                # Otherwise, fall through and try to match normally

            # Skip repeated words (same word spoken twice in a row)
            if last_matched_spoken and spoken_norm == self._normalize_word(last_matched_spoken):
                consecutive_misses = 0  # Repetitions don't count as misses
                debug_log.log_server_word(
                    pos, f"[repeat:{spoken_word}]", "skip_repeat")
                word_idx += 1
                continue

            matched = False
            skip_allowed = self.skip_disabled_count <= 0

            # Check if we're in the middle of matching an expansion
            if self.active_expansions:
                # Try to continue the current expansion
                if self._filter_expansions_by_word(spoken_word):
                    msg = (f"exp_match \"{spoken_norm}\" pos={self.expansion_match_position} "
                           f"remaining={len(self.active_expansions)}")
                    debug_log.log_server_word(pos, self.words[pos], msg)
                    matched = True
                    last_matched_spoken = spoken_word
                    consecutive_misses = 0
                    word_idx += 1

                    # Check if expansion is complete
                    if self._is_expansion_complete():
                        debug_log.log_server_word(
                            pos, self.words[pos], "exp_complete")
                        pos += 1
                        positions_advanced += 1
                        self._clear_expansion_state()
                        if self.skip_disabled_count > 0:
                            self.skip_disabled_count -= 1
                else:
                    # Word doesn't match any remaining expansion
                    # Expansion ended early - advance position and try this word at next pos
                    msg = (f"exp_ended \"{spoken_norm}\" "
                           f"(no match at pos {self.expansion_match_position})")
                    debug_log.log_server_word(pos, self.words[pos], msg)
                    pos += 1
                    positions_advanced += 1
                    self._clear_expansion_state()
                    if self.skip_disabled_count > 0:
                        self.skip_disabled_count -= 1
                    # Don't increment word_idx - try this word at the new position
                    continue
            else:
                # Not in an expansion - try to start one or match normally
                speakable_words = self.parsed_script.speakable_words
                sw = speakable_words[pos] if pos < len(
                    speakable_words) else None

                if sw and sw.is_expansion and sw.all_expansions:
                    # This is an expandable token - start expansion matching
                    self._start_expansion_matching(pos)
                    if self._filter_expansions_by_word(spoken_word):
                        debug_log.log_server_word(
                            pos, self.words[pos],
                            f"exp_start \"{spoken_norm}\" remaining={len(self.active_expansions)}"
                        )
                        matched = True
                        last_matched_spoken = spoken_word
                        consecutive_misses = 0
                        word_idx += 1

                        # Check if single-word expansion is complete
                        if self._is_expansion_complete():
                            debug_log.log_server_word(
                                pos, self.words[pos], "exp_complete_1word")
                            pos += 1
                            positions_advanced += 1
                            self._clear_expansion_state()
                            if self.skip_disabled_count > 0:
                                self.skip_disabled_count -= 1
                    else:
                        # First word doesn't match any expansion - clear and fall through
                        self._clear_expansion_state()
                else:
                    # Regular word - try direct matching
                    if self._word_matches_at_position(spoken_word, pos):
                        debug_log.log_server_word(
                            pos, self.words[pos], f"match \"{spoken_norm}\"")
                        pos += 1
                        positions_advanced += 1
                        matched = True
                        last_matched_spoken = spoken_word
                        consecutive_misses = 0
                        word_idx += 1
                        if self.skip_disabled_count > 0:
                            self.skip_disabled_count -= 1

                # Try skipping script words if no match yet (up to max_skip_distance)
                if not matched and skip_allowed:
                    for skip_count in range(1, self.max_skip_distance + 1):
                        skip_pos = pos + skip_count
                        if skip_pos >= len(self.words):
                            break
                        if self._word_matches_at_position(spoken_word, skip_pos):
                            # Log skipped words
                            for i in range(skip_count):
                                debug_log.log_server_word(
                                    pos +
                                    i, self.words[pos +
                                                  i], f"skip{skip_count}_missed"
                                )
                            msg = f"skip{skip_count}_match \"{spoken_norm}\""
                            debug_log.log_server_word(
                                skip_pos, self.words[skip_pos], msg)
                            # Check if the skipped-to position starts an expansion
                            sw_skip = self.parsed_script.speakable_words[skip_pos] \
                                if skip_pos < len(self.parsed_script.speakable_words) else None
                            if sw_skip and sw_skip.is_expansion and sw_skip.all_expansions:
                                self._start_expansion_matching(skip_pos)
                                self._filter_expansions_by_word(spoken_word)
                                if self._is_expansion_complete():
                                    pos = skip_pos + 1
                                    positions_advanced += skip_count + 1
                                    self._clear_expansion_state()
                                else:
                                    pos = skip_pos
                                    positions_advanced += skip_count
                            else:
                                pos = skip_pos + 1
                                positions_advanced += skip_count + 1
                            matched = True
                            last_matched_spoken = spoken_word
                            consecutive_misses = 0
                            word_idx += 1
                            break

            if not matched:
                # Word doesn't match - continue trying subsequent words
                # Don't break early - process all words to behave same as word-by-word updates
                consecutive_misses += 1
                debug_log.log_server_word(
                    pos, self.words[pos] if pos < len(self.words) else "?",
                    f"no_match \"{spoken_norm}\" miss#{consecutive_misses}"
                )
                word_idx += 1
                # Reset consecutive misses after a while to allow recovery
                if consecutive_misses >= max_consecutive_misses:
                    consecutive_misses = 0

        return positions_advanced

    def _find_best_match(self, spoken_words: str) -> Tuple[int, float]:
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
        spoken_normalized = ' '.join(
            self._normalize_word(w) for w in spoken_words.split() if w.strip()
        )

        if not spoken_normalized:
            return self.current_word_index, 0.0

        # Search within max_jump_distance to avoid matching similar text far away
        # This prevents jumping to repeated phrases in distant paragraphs
        search_start = max(0, self.current_word_index - self.max_jump_distance)
        search_end = min(
            len(self.words),
            max(self.high_water_mark, self.current_word_index) +
            self.max_jump_distance
        )

        # Also always search from the beginning of current line
        if self.current_word_index < len(self.word_to_line):
            current_line = self.word_to_line[self.current_word_index]
            line_start = self.lines[current_line].word_start_index
            search_start = min(search_start, line_start)

        # Only log at DEBUG level - this is called frequently
        # logger.debug(
        #     "[FIND BEST MATCH] search_start=%d, search_end=%d, current_word_index=%d, "
        #     "high_water_mark=%d, spoken='%s'",
        #     search_start, search_end, self.current_word_index, self.high_water_mark,
        #     spoken_normalized[:50] + "..." if len(spoken_normalized) > 50 else spoken_normalized
        # )

        best_index = self.current_word_index
        best_score = 0.0

        # Slide window through search range
        for i in range(search_start, search_end):
            window_text = self._get_window_text(i)
            if not window_text:
                continue

            # Use token_set_ratio for better partial matching
            score = fuzz.token_set_ratio(spoken_normalized, window_text)

            # Penalize very short windows - they can give false positives
            # when a common word like "you" or "the" matches by itself
            window_word_count = len(window_text.split())
            spoken_word_count = len(spoken_normalized.split())
            if window_word_count < min(self.window_size, spoken_word_count):
                # Reduce score proportionally to how short the window is
                coverage = window_word_count / \
                    min(self.window_size, spoken_word_count)
                score = score * coverage

            # Slight preference for forward progress (avoid getting stuck)
            if i >= self.current_word_index:
                score += 2

            if score > best_score:
                best_score = score
                best_index = i

        # logger.debug(
        #     "[FIND BEST MATCH] Result: best_index=%d, best_score=%.1f",
        #     best_index, best_score
        # )

        return best_index, best_score

    def update(self, transcription: str, is_partial: bool = True) -> ScriptPosition:
        """
        Update position based on new transcription using optimistic matching.

        Uses a two-track approach:
        1. Optimistic: Advance word-by-word for immediate UI response
        2. Validation: Triggered after N words to catch errors/backtracks

        Args:
            transcription: The transcribed text
            is_partial: True if this is a partial (in-progress) result

        Returns:
            Updated ScriptPosition (uses optimistic position for responsiveness)
        """
        # Update position using optimistic matching (fast path)

        if not transcription.strip():
            return self.current_position()

        # Extract only the NEW words from the transcription
        new_words = self._extract_new_words(transcription)

        # Try to advance optimistically based on new words
        words_advanced = self._advance_optimistically(new_words)

        # Verbose logging commented out to reduce noise
        # if new_words and (words_advanced > 0 or self.high_water_mark > 0):
        #     logger.debug(
        #         "[UPDATE] new_words=%s, words_advanced=%d, optimistic_position=%d, "
        #         "high_water_mark=%d, words_since_validation=%d",
        #         new_words[:5] if len(new_words) > 5 else new_words,
        #         words_advanced, self.optimistic_position, self.high_water_mark,
        #         self.words_since_validation
        #     )

        is_backtrack = False

        if words_advanced > 0:
            # Update optimistic position
            self.optimistic_position += words_advanced

            # Track words for validation triggering
            self.words_since_validation += len(new_words)

            # Trigger validation after every 5 words
            if self.words_since_validation >= 5:
                self.needs_validation = True

            # Update high water mark
            self.high_water_mark = max(
                self.high_water_mark, self.optimistic_position)

            # Sync current_word_index with optimistic for display
            self.current_word_index = self.optimistic_position
        elif self.active_expansions:
            # We're in the middle of matching a multi-word expansion (e.g., "1500" ->
            # "one thousand five hundred"). The position won't advance until the
            # expansion is complete. Don't trigger validation - trust the expansion
            # matching process.
            pass
        else:
            # No words matched - this could indicate a backtrack or forward jump!
            # Immediately validate if we have enough new words to work with
            if new_words and len(new_words) >= 3:
                _, is_backtrack = self.validate_position(transcription)
            elif new_words and self.high_water_mark > 0:
                self.needs_validation = True

        # Store transcription for next comparison
        self.last_transcription = transcription

        # Convert speakable index to raw token index for UI
        raw_index = self._speakable_to_raw_index(self.optimistic_position)

        position = ScriptPosition(
            word_index=raw_index,  # Raw token index for UI highlighting
            line_index=self._word_to_line_index(self.optimistic_position),
            confidence=100.0 if words_advanced > 0 else 0.0,
            matched_words=new_words[-3:] if new_words else [],
            is_backtrack=is_backtrack,
            speakable_index=self.optimistic_position  # Internal tracking index
        )

        # Check if validation is needed (every 5 words)
        position.is_backtrack = False
        if self.needs_validation:
            logger.debug(
                "[VALIDATION] Triggering validation at position %d",
                position.word_index
            )
            validated_pos, is_backtrack = self.validate_position(transcription)
            position.is_backtrack = is_backtrack
            if position.is_backtrack or validated_pos != position.word_index:
                # Position was corrected by validation
                logger.info(
                    "[VALIDATION RESULT] is_backtrack=%s, validated_pos=%d, "
                    "original_pos=%d",
                    is_backtrack, validated_pos, position.word_index
                )
                position = self.current_position()
                position.is_backtrack = is_backtrack
            # if position.is_backtrack:
            #     logger.warning(
            #         "[BACKTRACK] Sending backtrack signal to clients, "
            #         "new position=%d",
            #         position.word_index
            #     )

        return position

    def validate_position(self, transcription: str) -> Tuple[int, bool]:
        """
        Validate current position using window-based fuzzy matching.
        Called periodically to catch errors and detect backtracks.

        Only triggers corrections when there's significant deviation (>2 words)
        from the expected position. This prevents repeated words from causing
        false backtrack detection.

        Returns:
            Tuple of (validated_position, is_backtrack)
        """
        self.words_since_validation = 0
        self.needs_validation = False

        if not transcription.strip():
            return self.optimistic_position, False

        # Don't validate with very short transcripts - not enough context
        # to reliably determine position (especially with repeated words)
        transcript_words = [w for w in transcription.split() if w.strip()]
        if len(transcript_words) < 3:
            return self.optimistic_position, False

        # Use existing window-based matching for validation
        best_index, confidence = self._find_best_match(transcription)

        if confidence < self.match_threshold:
            return self.optimistic_position, False

        # Calculate deviation from optimistic position
        position_diff = self.optimistic_position - best_index

        # If deviation is small (≤2 words), trust the optimistic position
        # This prevents repeated words from causing false corrections
        if abs(position_diff) <= 2:
            return self.optimistic_position, False

        # Before considering a backtrack, check if the transcript words
        # match what we expect at/near the optimistic position.
        # If they do, trust the optimistic position.
        transcript_matches = (
            self._transcript_matches_position(
                transcript_words, self.optimistic_position
            )
        )
        if transcript_matches:
            return self.optimistic_position, False

        # Reject jumps that are too large - prevents jumping to similar sentences
        # far away in the script (e.g., repeated phrases in different paragraphs)
        jump_distance = abs(position_diff)
        if jump_distance > self.max_jump_distance:
            logger.info(
                "[JUMP REJECTED] Jump too large: %d words (max=%d). "
                "best_index=%d, optimistic_position=%d. Staying at current position.",
                jump_distance, self.max_jump_distance, best_index, self.optimistic_position
            )
            return self.optimistic_position, False

        # Check for backtrack - only if validated position is significantly behind
        # the high water mark (more than backtrack_threshold words)
        #
        # Backtrack conditions (all must be true):
        # 1. best_index < high_water_mark - backtrack_threshold
        #    (validated position is significantly behind the furthest we've reached)
        # 2. high_water_mark > 0
        #    (we've actually made forward progress)
        # 3. position_diff > 2
        #    (optimistic is significantly ahead of validated - confirms mismatch)

        cond1 = best_index < self.high_water_mark - self.backtrack_threshold
        cond2 = self.high_water_mark > 0
        cond3 = position_diff > 2

        is_backtrack = cond1 and cond2 and cond3

        # Log backtrack detection evaluation with individual conditions
        logger.info(
            "[BACKTRACK CHECK] best_index=%d, high_water_mark=%d, threshold=%d, "
            "optimistic_position=%d, position_diff=%d, confidence=%.1f",
            best_index, self.high_water_mark, self.backtrack_threshold,
            self.optimistic_position, position_diff, confidence
        )
        logger.info(
            "[BACKTRACK CONDITIONS] cond1(best<%d-%d=%d): %s, cond2(hwm>0): %s, "
            "cond3(diff>2): %s => is_backtrack=%s",
            self.high_water_mark, self.backtrack_threshold,
            self.high_water_mark - self.backtrack_threshold,
            cond1, cond2, cond3, is_backtrack
        )

        if is_backtrack:
            # User went back - but they've continued speaking past the backtrack point.
            # best_index is where the matching WINDOW starts, not necessarily where
            # the first transcript word matches. We need to find where the first
            # transcript word actually matches within the window.
            first_word = self._normalize_word(transcript_words[0])
            transcript_start_offset = 0
            for offset in range(min(self.window_size, len(self.words) - best_index)):
                if self._word_matches(first_word, self.words[best_index + offset]):
                    transcript_start_offset = offset
                    break

            # The actual transcript start in the script
            actual_start = best_index + transcript_start_offset
            # Position after speaking all transcript words
            adjusted_position = min(
                actual_start + len(transcript_words),
                len(self.words) - 1 if self.words else 0
            )

            old_pos = self.optimistic_position
            words_in_range = self.words[adjusted_position:min(
                adjusted_position+3, len(self.words))]
            debug_log.log_server_position_update(
                old_pos, adjusted_position, words_in_range,
                f"BACKTRACK best_idx={best_index} + transcript_len={len(transcript_words)}"
            )

            self.optimistic_position = adjusted_position
            self.current_word_index = adjusted_position
            self.high_water_mark = adjusted_position
            # Keep transcript to continue from here
            self.last_transcription = transcription
            # Disable skip logic for next 5 words to prevent matching old transcript remnants
            self.skip_disabled_count = 5
            # Clear expansion state - we're at a new position, any in-progress expansion is invalid
            self._clear_expansion_state()
            return adjusted_position, True

        # Check for forward jump - user skipped ahead in the script
        # position_diff < 0 means best_index > optimistic_position (user is ahead)
        is_forward_jump = (
            position_diff < -self.backtrack_threshold and
            best_index > self.high_water_mark
        )

        if is_forward_jump:
            # User jumped forward - adjust to where they actually are
            # Find where the first transcript word actually matches within the window
            first_word = self._normalize_word(transcript_words[0])
            transcript_start_offset = 0
            for offset in range(min(self.window_size, len(self.words) - best_index)):
                if self._word_matches(first_word, self.words[best_index + offset]):
                    transcript_start_offset = offset
                    break

            actual_start = best_index + transcript_start_offset
            adjusted_position = min(
                actual_start + len(transcript_words),
                len(self.words) - 1 if self.words else 0
            )

            old_pos = self.optimistic_position
            words_in_range = self.words[adjusted_position:min(
                adjusted_position+3, len(self.words))]
            debug_log.log_server_position_update(
                old_pos, adjusted_position, words_in_range,
                f"FORWARD_JUMP best_idx={best_index} + transcript_len={len(transcript_words)}"
            )

            self.optimistic_position = adjusted_position
            self.current_word_index = adjusted_position
            self.high_water_mark = adjusted_position
            self.last_transcription = transcription
            # Disable skip logic for next 5 words to prevent matching old transcript remnants
            self.skip_disabled_count = 5
            # Clear expansion state - we're at a new position, any in-progress expansion is invalid
            self._clear_expansion_state()
            # Return True for is_backtrack to trigger UI update (it's really a "jump")
            return adjusted_position, True

        if position_diff > 5:
            # Optimistic got too far ahead - pull back
            # Also adjust for transcript length
            adjusted_position = min(
                best_index + len(transcript_words),
                len(self.words) - 1 if self.words else 0
            )
            old_pos = self.optimistic_position
            words_in_range = self.words[adjusted_position:min(
                adjusted_position+3, len(self.words))]
            debug_log.log_server_position_update(
                old_pos, adjusted_position, words_in_range,
                f"PULL_BACK best_idx={best_index} + transcript_len={len(transcript_words)}"
            )
            self.optimistic_position = adjusted_position
            self.current_word_index = adjusted_position
            self.last_transcription = transcription
            # Clear expansion state - we're at a new position, any in-progress expansion is invalid
            self._clear_expansion_state()

        elif position_diff < -5:
            # Optimistic fell behind - catch up
            adjusted_position = min(
                best_index + len(transcript_words),
                len(self.words) - 1 if self.words else 0
            )
            old_pos = self.optimistic_position
            words_in_range = self.words[adjusted_position:min(
                adjusted_position+3, len(self.words))]
            debug_log.log_server_position_update(
                old_pos, adjusted_position, words_in_range,
                f"CATCH_UP best_idx={best_index} + transcript_len={len(transcript_words)}"
            )
            self.optimistic_position = adjusted_position
            self.current_word_index = adjusted_position
            self.high_water_mark = max(self.high_water_mark, adjusted_position)
            self.last_transcription = transcription
            # Clear expansion state - we're at a new position, any in-progress expansion is invalid
            self._clear_expansion_state()

        return self.optimistic_position, False

    def _word_to_line_index(self, word_index: int) -> int:
        """Convert a word index to a line index."""
        if word_index >= len(self.word_to_line):
            return len(self.lines) - 1
        return self.word_to_line[word_index]

    def current_position(self) -> ScriptPosition:
        """Get the current position without updating."""
        raw_index = self._speakable_to_raw_index(self.current_word_index)
        return ScriptPosition(
            word_index=raw_index,
            line_index=self._word_to_line_index(self.current_word_index),
            confidence=0.0,
            speakable_index=self.current_word_index
        )

    def reset(self):
        """Reset tracking to the beginning of the script."""
        self.current_word_index = 0
        self.high_water_mark = 0
        self.recent_matches = []
        # Reset optimistic state
        self.optimistic_position = 0
        self.last_transcription = ""
        self.words_since_validation = 0
        self.needs_validation = False
        self.skip_disabled_count = 0
        # Reset expansion state
        self._clear_expansion_state()

    def jump_to(self, word_index: int):
        """Jump to a specific position in the script."""
        word_index = max(0, min(word_index, len(
            self.words) - 1)) if self.words else 0
        self.current_word_index = word_index
        self.high_water_mark = word_index
        self.recent_matches = [word_index]
        # Sync optimistic state
        self.optimistic_position = word_index
        self.last_transcription = ""
        self.words_since_validation = 0
        self.needs_validation = False
        self.skip_disabled_count = 0
        # Clear expansion state - we're at a new position, any in-progress expansion is invalid
        self._clear_expansion_state()

    def get_display_lines(
        self,
        past_lines: int = 1,
        future_lines: int = 10
    ) -> Tuple[List[ScriptLine], int, int]:
        """
        Get lines to display around the current position.

        Args:
            past_lines: Number of lines before current to show
            future_lines: Number of lines after current to show

        Returns:
            Tuple of (lines_to_display, current_line_index_in_list, current_word_offset)
        """
        current_line = self._word_to_line_index(self.current_word_index)

        start_line = max(0, current_line - past_lines)
        end_line = min(len(self.lines), current_line + future_lines + 1)

        display_lines = self.lines[start_line:end_line]
        current_in_display = current_line - start_line

        # Calculate word offset within current line
        if current_line < len(self.lines):
            line = self.lines[current_line]
            word_offset = self.current_word_index - line.word_start_index
        else:
            word_offset = 0

        return display_lines, current_in_display, word_offset

    @property
    def progress(self) -> float:
        """Get overall progress through the script (0.0 to 1.0)."""
        total_raw = self.parsed_script.total_raw_tokens
        if total_raw == 0:
            return 0.0
        raw_index = self._speakable_to_raw_index(self.current_word_index)
        return raw_index / total_raw

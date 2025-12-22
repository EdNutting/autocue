"""
Expansion matching for numbers and punctuation in speech tracking.

Handles dynamic matching of spoken words to expandable tokens like:
- Numbers: "100" -> "one hundred", "a hundred", "one zero zero"
- Punctuation: "/" -> "slash", "or", "forward slash"

Tracks which expansions are still valid as words are matched, and
determines when an expansion is complete.
"""


from rapidfuzz import fuzz

from .script_parser import ParsedScript, SpeakableWord, normalize_word


class ExpansionMatcher:
    """
    Manages matching of spoken words to expandable tokens.

    Expandable tokens (numbers, punctuation) can be spoken in multiple ways.
    This class tracks which expansions are still valid as the user speaks,
    filtering out non-matching alternatives word by word.

    Example for "100":
      - User says "one" -> filters to ["one hundred"], ["one zero zero"]
      - User says "hundred" -> matches complete expansion ["one", "hundred"]
      - Position advances past "100"
    """

    def __init__(self, parsed_script: ParsedScript) -> None:
        """
        Initialize the expansion matcher.

        Args:
            parsed_script: The parsed script containing speakable words
        """
        self.parsed_script: ParsedScript = parsed_script

        # Dynamic expansion matching state
        self.active_expansions: list[list[str]] = []
        self.expansion_match_position: int = 0

    def get_first_words(self, speakable_idx: int) -> list[str]:
        """
        Get all possible FIRST words that could start matching at a position.

        For expandable tokens, returns the first word of each possible expansion.
        For regular words, returns just that word.

        Example for "100": returns ["one", "a"] (from "one hundred", "a hundred")

        Args:
            speakable_idx: Index in the speakable words list

        Returns:
            List of possible first words (lowercase)
        """
        if speakable_idx >= len(self.parsed_script.speakable_words):
            return []

        sw: SpeakableWord = self.parsed_script.speakable_words[speakable_idx]

        if sw.is_expansion and sw.all_expansions:
            # Get the first word from each expansion
            first_words: list[str] = []
            for exp in sw.all_expansions:
                if exp:
                    word: str = exp[0].lower()
                    if word not in first_words:
                        first_words.append(word)
            return first_words

        # For regular words, just return the word itself
        return [sw.text]

    def start(self, speakable_idx: int) -> bool:
        """
        Initialize expansion matching state for an expandable token.

        Call this when starting to match at a position that might be expandable.

        Args:
            speakable_idx: Index in the speakable words list

        Returns:
            True if this is an expandable token with expansions
        """
        if speakable_idx >= len(self.parsed_script.speakable_words):
            return False

        sw: SpeakableWord = self.parsed_script.speakable_words[speakable_idx]

        if sw.is_expansion and sw.all_expansions:
            self.active_expansions = [exp[:]
                                      for exp in sw.all_expansions]  # Copy
            self.expansion_match_position = 0
            return True

        self.active_expansions = []
        self.expansion_match_position = 0
        return False

    def filter_by_word(self, spoken_word: str) -> bool:
        """
        Filter active expansions to those matching the spoken word.

        Call this for each word spoken while matching an expansion.
        Filters out expansions that don't match at the current position.

        Args:
            spoken_word: The word spoken by the user

        Returns:
            True if at least one expansion still matches
        """
        if not self.active_expansions:
            return False

        spoken_norm: str = normalize_word(spoken_word)
        if not spoken_norm:
            return False

        pos: int = self.expansion_match_position
        remaining: list[list[str]] = []

        for exp in self.active_expansions:
            if pos < len(exp):
                exp_word: str = exp[pos].lower()
                # Check for exact or fuzzy match
                if spoken_norm == exp_word or fuzz.ratio(spoken_norm, exp_word) >= 75:
                    remaining.append(exp)

        if remaining:
            self.active_expansions = remaining
            self.expansion_match_position += 1
            return True

        return False

    def is_complete(self) -> bool:
        """
        Check if any active expansion has been fully matched.

        Returns:
            True if an expansion was completely matched
        """
        if not self.active_expansions:
            return False

        pos: int = self.expansion_match_position
        return any(pos >= len(exp) for exp in self.active_expansions)

    def clear(self) -> None:
        """Clear the expansion matching state."""
        self.active_expansions = []
        self.expansion_match_position = 0

    def clone(self) -> "ExpansionMatcher":
        """Clone the expansion matcher state."""
        result = ExpansionMatcher(self.parsed_script)
        result.active_expansions = [xs.copy() for xs in self.active_expansions]
        result.expansion_match_position = self.expansion_match_position
        return result

    @property
    def is_active(self) -> bool:
        """Check if currently matching an expansion."""
        return len(self.active_expansions) > 0

    @property
    def remaining_count(self) -> int:
        """Get the number of remaining valid expansions."""
        return len(self.active_expansions)

    @property
    def match_position(self) -> int:
        """Get the current position within the expansion being matched."""
        return self.expansion_match_position

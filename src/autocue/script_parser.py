"""
Script parsing module that handles three representations of script text:
1. Raw tokens - tokens as they appear in rendered HTML (after Markdown processing)
2. Speakable words - words as they would be spoken (with punctuation expanded)
3. HTML rendering - with word indices mapping back to raw tokens

This ensures the speech tracker and UI highlighting stay in sync even when
punctuation is spoken aloud (e.g., "&" as "and", "<" as "less than").
"""

import re
from dataclasses import dataclass
from typing import List, Dict, Optional
from html.parser import HTMLParser

from .number_expander import is_number_token, get_number_expansions


# Punctuation that gets spoken as words
# Maps punctuation strings to a list of possible spoken forms
# Each form is itself a list of words (to handle multi-word expansions)
# The FIRST entry is the "primary" expansion used for position tracking
# Note: Characters like # * _ are excluded because they're typically
# used for Markdown formatting and don't appear in rendered output
PUNCTUATION_EXPANSIONS: Dict[str, List[List[str]]] = {
    "&": [["and"], ["ampersand"]],
    "<": [["less", "than"]],
    ">": [["greater", "than"]],
    "<=": [["less", "than", "or", "equal"]],
    ">=": [["greater", "than", "or", "equal"]],
    "/": [["slash"], ["or"], ["forward", "slash"]],
    "\\": [["backslash"], ["back", "slash"]],
    "~": [["approximately"], ["tilde"], ["about"]],
    "@": [["at"]],
    "+": [["plus"]],
    "-": [["minus"], ["dash"], ["hyphen"]],
    "=": [["equals"], ["equal"], ["is"]],
    "%": [["percent"]],
    "^": [["caret"], ["to", "the", "power"], ["to", "the", "power", "of"], ["xor"], ["ex", "or"], ["exor"], ["exo"], ["x", "or"]],
    "|": [["pipe"], ["or"]],
    "*": [["times"], ["multiply"], ["multiplied"]],
}

# Punctuation that should be silently dropped (not spoken)
# These are punctuation marks that don't get vocalized
SILENT_PUNCTUATION = frozenset([
    ',', '.', '!', '?', ';', ':', '"', "'", '(', ')', '[', ']', '{', '}',
    '—', '–', '…', '"', '"', ''', ''', '«', '»',
])


@dataclass
class RawToken:
    """A token as it appears in the rendered HTML output."""
    text: str  # Original text (e.g., "&", "hello", "don't")
    index: int  # Position in the raw token list

    def __repr__(self) -> str:
        return f"RawToken({self.index}: '{self.text}')"


@dataclass
class SpeakableWord:
    """A word as it would be spoken.

    For expandable tokens (numbers, punctuation), this represents the ENTIRE token
    with a single position. The tracker handles matching variable-length expansions
    dynamically by filtering possible expansions as words are spoken.
    """
    text: str  # The spoken/normalized form (e.g., "and" for "&", "dont" for "don't")
    raw_token_index: int  # Maps back to the RawToken that produced this
    is_expansion: bool = False  # True if this is an expandable token (number/punctuation)
    # For expandable tokens, store all possible expansions for dynamic matching
    all_expansions: Optional[List[List[str]]] = None

    def __repr__(self) -> str:
        if self.is_expansion and self.all_expansions:
            return f"SpeakableWord('{self.text}' -> raw[{self.raw_token_index}] expansions={len(self.all_expansions)})"
        return f"SpeakableWord('{self.text}' -> raw[{self.raw_token_index}])"


@dataclass
class ParsedScript:
    """Complete parsed representation of a script."""
    raw_text: str  # Original script text
    raw_tokens: List[RawToken]  # Tokens as they appear in rendered HTML
    speakable_words: List[SpeakableWord]  # Words as spoken (for matching)
    # Map raw_token_index -> speakable_word indices
    raw_to_speakable: Dict[int, List[int]]
    # Map speakable_word_index -> raw_token_index
    speakable_to_raw: Dict[int, int]

    @property
    def total_raw_tokens(self) -> int:
        return len(self.raw_tokens)

    @property
    def total_speakable_words(self) -> int:
        return len(self.speakable_words)

    def get_raw_token(self, speakable_index: int) -> Optional[RawToken]:
        """Get the raw token that produced a given speakable word."""
        if speakable_index < 0 or speakable_index >= len(self.speakable_words):
            return None
        raw_idx = self.speakable_to_raw.get(speakable_index)
        if raw_idx is None or raw_idx >= len(self.raw_tokens):
            return None
        return self.raw_tokens[raw_idx]


def normalize_word(word: str) -> str:
    """Normalize a word for matching (lowercase, strip punctuation).

    This is used for comparing spoken words to script words.
    """
    return re.sub(r'[^\w\s]', '', word.lower()).strip()


def strip_surrounding_punctuation(token: str) -> str:
    """Strip leading and trailing punctuation from a token.

    This preserves internal punctuation (like commas in "1,000" or periods in "3.14")
    but removes surrounding quotes, commas, periods, etc.

    Examples:
        "1100," -> "1100"
        '"hello"' -> "hello"
        "100." -> "100"
        "1,000" -> "1,000" (comma preserved - it's internal)
        "3.14" -> "3.14" (period preserved - it's internal)
    """
    # Strip leading punctuation (quotes, brackets, etc.)
    while token and token[0] in '"\'"([{<':
        token = token[1:]
    # Strip trailing punctuation (quotes, commas, periods, brackets, etc.)
    while token and token[-1] in '"\'".,;:!?)]}>\'"':
        token = token[:-1]
    return token


def should_expand_punctuation(token: str) -> Optional[List[str]]:
    """Check if a token should be expanded to spoken words.

    Returns the PRIMARY expansion (first in the list) or None if no expansion needed.
    The primary expansion is used for position tracking in the speakable words list.
    """
    # First check for exact multi-character matches (e.g., "<=", ">=")
    if token in PUNCTUATION_EXPANSIONS:
        # Return first (primary) expansion
        return PUNCTUATION_EXPANSIONS[token][0]

    # Check if the entire token is a single punctuation character
    stripped = token.strip()
    if len(stripped) == 1 and stripped in PUNCTUATION_EXPANSIONS:
        # Return first (primary) expansion
        return PUNCTUATION_EXPANSIONS[stripped][0]

    return None


def get_all_expansions(token: str) -> Optional[List[List[str]]]:
    """Get all possible spoken expansions for a punctuation or number token.

    Returns a list of all possible expansions (each is a list of words),
    or None if the token has no expansions.

    Example: get_all_expansions("/") returns [["slash"], ["or"], ["forward", "slash"]]
    Example: get_all_expansions("100") returns [["one", "hundred"], ["a", "hundred"], ...]
    """
    # Check punctuation first
    if token in PUNCTUATION_EXPANSIONS:
        return PUNCTUATION_EXPANSIONS[token]

    stripped = token.strip()
    if len(stripped) == 1 and stripped in PUNCTUATION_EXPANSIONS:
        return PUNCTUATION_EXPANSIONS[stripped]

    # Check for number expansions
    number_expansions = get_number_expansions(token)
    if number_expansions:
        return number_expansions

    return None


def get_expansion_first_words(token: str) -> Optional[List[str]]:
    """Get the first word of each possible expansion for a punctuation token.

    This is useful for matching - if a spoken word matches any of these,
    it could be the start of an expansion for this token.

    Example: get_expansion_first_words("/") returns ["slash", "or", "forward"]
    """
    expansions = get_all_expansions(token)
    if expansions is None:
        return None
    return [exp[0] for exp in expansions]


def is_silent_punctuation(token: str) -> bool:
    """Check if a token is punctuation that should be silently dropped."""
    stripped = token.strip()
    # All characters must be silent punctuation
    return all(c in SILENT_PUNCTUATION for c in stripped) if stripped else True


class HTMLTextExtractor(HTMLParser):
    """Extract text content from HTML, preserving word boundaries."""

    def __init__(self):
        super().__init__()
        self.tokens: List[str] = []

    def handle_data(self, data):
        """Extract words from text content."""
        # Split on whitespace to get individual words
        words = data.split()
        for word in words:
            if word.strip():
                self.tokens.append(word)


def parse_script(text: str, rendered_html: Optional[str] = None) -> ParsedScript:
    """Parse script into raw tokens and speakable words.

    If rendered_html is provided, tokens are extracted from the HTML content
    (this is the preferred mode as it matches what appears in the UI).
    Otherwise, tokens are extracted from the raw text.

    Args:
        text: The raw script text
        rendered_html: Optional pre-rendered HTML (from Markdown processing)

    Returns:
        ParsedScript with all representations and mappings
    """
    raw_tokens: List[RawToken] = []
    speakable_words: List[SpeakableWord] = []
    raw_to_speakable: Dict[int, List[int]] = {}
    speakable_to_raw: Dict[int, int] = {}

    # Extract tokens from HTML if provided, otherwise from raw text
    if rendered_html:
        extractor = HTMLTextExtractor()
        extractor.feed(rendered_html)
        tokens = extractor.tokens
    else:
        # Fallback to raw text parsing
        tokens = []
        for line in text.split('\n'):
            tokens.extend(word for word in line.split() if word.strip())

    raw_index = 0
    speakable_index = 0

    for token in tokens:
        if not token.strip():
            continue

        # Create raw token
        raw_token = RawToken(
            text=token,
            index=raw_index
        )
        raw_tokens.append(raw_token)
        raw_to_speakable[raw_index] = []

        # Check for punctuation expansion
        expansion = should_expand_punctuation(token)

        # Strip surrounding punctuation for number detection
        # e.g., "1100," -> "1100", '"100"' -> "100"
        stripped_token = strip_surrounding_punctuation(token)

        if expansion:
            # Punctuation token - create ONE speakable word with all expansions
            # Get all possible expansions for dynamic matching
            all_exps = get_all_expansions(token)
            sw = SpeakableWord(
                text=expansion[0].lower(),  # Primary first word for display
                raw_token_index=raw_index,
                is_expansion=True,
                all_expansions=all_exps
            )
            speakable_words.append(sw)
            raw_to_speakable[raw_index].append(speakable_index)
            speakable_to_raw[speakable_index] = raw_index
            speakable_index += 1
        elif is_number_token(stripped_token):
            # Number token - create ONE speakable word with all expansions
            # The tracker handles matching variable-length expansions dynamically
            number_expansions = get_number_expansions(stripped_token)
            if number_expansions:
                sw = SpeakableWord(
                    text=number_expansions[0][0].lower(),  # Primary first word
                    raw_token_index=raw_index,
                    is_expansion=True,
                    all_expansions=number_expansions
                )
                speakable_words.append(sw)
                raw_to_speakable[raw_index].append(speakable_index)
                speakable_to_raw[speakable_index] = raw_index
                speakable_index += 1
            else:
                # Fallback: treat as normal word (shouldn't happen)
                normalized = normalize_word(token)
                if normalized:
                    sw = SpeakableWord(
                        text=normalized,
                        raw_token_index=raw_index,
                        is_expansion=False
                    )
                    speakable_words.append(sw)
                    raw_to_speakable[raw_index].append(speakable_index)
                    speakable_to_raw[speakable_index] = raw_index
                    speakable_index += 1
        elif is_silent_punctuation(token):
            # Pure punctuation - no speakable word, but still a raw token
            # (raw_to_speakable[raw_index] remains empty list)
            pass
        else:
            # Normal word - normalize and add
            normalized = normalize_word(token)
            if normalized:  # Skip if normalizes to empty
                sw = SpeakableWord(
                    text=normalized,
                    raw_token_index=raw_index,
                    is_expansion=False
                )
                speakable_words.append(sw)
                raw_to_speakable[raw_index].append(speakable_index)
                speakable_to_raw[speakable_index] = raw_index
                speakable_index += 1

        raw_index += 1

    return ParsedScript(
        raw_text=text,
        raw_tokens=raw_tokens,
        speakable_words=speakable_words,
        raw_to_speakable=raw_to_speakable,
        speakable_to_raw=speakable_to_raw
    )


def get_speakable_word_list(parsed: ParsedScript) -> List[str]:
    """Get list of speakable words (for tracker matching)."""
    return [sw.text for sw in parsed.speakable_words]


def speakable_to_raw_index(parsed: ParsedScript, speakable_idx: int) -> int:
    """Convert a speakable word index to a raw token index.

    This is used when the tracker matches at speakable_idx and we need
    to highlight the corresponding raw token in the UI.

    When speakable_idx is past the end (i.e., script is complete),
    returns len(raw_tokens) to indicate "past the end".
    """
    if speakable_idx < 0:
        return 0
    if speakable_idx >= len(parsed.speakable_words):
        # Past the end - return count of raw tokens (past-the-end index)
        return len(parsed.raw_tokens)
    return parsed.speakable_to_raw.get(speakable_idx, 0)

"""
Number expansion module for converting written numbers to spoken forms.

This module handles various number formats and generates all plausible
spoken alternatives, following the same pattern as PUNCTUATION_EXPANSIONS.

Supported formats:
- Integers: 100, 1000, 1000000
- Comma-separated: 1,100, 1,000,000
- Decimals: 3.07, 0.5, 0.33
- Ordinals: 1st, 2nd, 3rd, 23rd
- Mixed alphanumeric: M3, 4K, 100GB, 4.05GHz

Units are ONLY expanded when attached to numbers (not standalone).
"""

import re
from re import Pattern

from num2words import num2words

# Regex patterns for detecting number types
PATTERNS: dict[str, Pattern[str]] = {
    # Pure integers: 100, 1000, 1000000
    'integer': re.compile(r'^-?\d+$'),

    # Comma-separated integers: 1,100, 1,000,000
    'comma_integer': re.compile(r'^-?\d{1,3}(,\d{3})+$'),

    # Decimals: 3.07, 0.3, 0.33
    'decimal': re.compile(r'^-?\d+\.\d+$'),

    # Ordinals: 1st, 2nd, 3rd, 23rd, 101st
    'ordinal': re.compile(r'^(\d+)(st|nd|rd|th)$', re.IGNORECASE),

    # Mixed alphanumeric prefix: M3, V8 (letter(s) then number)
    'prefix_mixed': re.compile(r'^([A-Za-z]+)(\d+(?:\.\d+)?)$'),

    # Mixed alphanumeric suffix: 4K, 100GB, 4.05GHz (number then letters)
    'suffix_mixed': re.compile(r'^(\d+(?:\.\d+)?)([A-Za-z]+)$'),

    # Rate units: 100GB/s, 60fps, 1000MB/s (number + unit + "/" + unit)
    'rate_unit': re.compile(r'^(\d+(?:\.\d+)?)([A-Za-z]+)/([A-Za-z]+)$'),
}


# Common fractions mapped to spoken alternatives
# Only include very common fractions as specified
COMMON_FRACTIONS: dict[str, list[list[str]]] = {
    '0.5': [['half'], ['one', 'half'], ['a', 'half']],
    '0.50': [['half'], ['one', 'half'], ['a', 'half']],
    '0.25': [['quarter'], ['one', 'quarter'], ['a', 'quarter']],
    '0.33': [['third'], ['one', 'third'], ['a', 'third']],
    '0.333': [['third'], ['one', 'third'], ['a', 'third']],
    '0.1': [['tenth'], ['one', 'tenth'], ['a', 'tenth']],
    '0.10': [['tenth'], ['one', 'tenth'], ['a', 'tenth']],
    '0.75': [['three', 'quarters']],
    '0.2': [['fifth'], ['one', 'fifth'], ['a', 'fifth']],
    '0.20': [['fifth'], ['one', 'fifth'], ['a', 'fifth']],
}


# Unit abbreviations and their spoken forms (only used when attached to numbers)
UNIT_EXPANSIONS: dict[str, list[list[str]]] = {
    # Data storage
    'k': [['k'], ['thousand']],
    'kb': [['k', 'b'], ['kilobytes'], ['kilobyte']],
    'mb': [['m', 'b'], ['megabytes'], ['megabyte'], ['megs']],
    'gb': [['g', 'b'], ['gigabytes'], ['gigabyte'], ['gigs']],
    'tb': [['t', 'b'], ['terabytes'], ['terabyte']],
    'pb': [['p', 'b'], ['petabytes'], ['petabyte']],

    # Frequency
    'hz': [['h', 'z'], ['hertz']],
    'khz': [['k', 'h', 'z'], ['kilohertz']],
    'mhz': [['m', 'h', 'z'], ['megahertz']],
    'ghz': [['g', 'h', 'z'], ['gigahertz']],

    # Distance
    'm': [['m'], ['metres'], ['meters']],
    'km': [['k', 'm'], ['kilometres'], ['kilometers']],
    'cm': [['c', 'm'], ['centimetres'], ['centimeters']],
    'mm': [['m', 'm'], ['millimetres'], ['millimeters']],
    'mi': [['m', 'i'], ['miles'], ['mile']],
    'ft': [['f', 't'], ['feet'], ['foot']],
    'in': [['i', 'n'], ['inches'], ['inch']],
    'yd': [['y', 'd'], ['yards'], ['yard']],

    # Time
    's': [['s'], ['seconds'], ['second']],
    'ms': [['m', 's'], ['milliseconds'], ['millisecond']],
    'ns': [['n', 's'], ['nanoseconds'], ['nanosecond']],
    'us': [['u', 's'], ['microseconds'], ['microsecond']],
    'min': [['min'], ['minutes'], ['minute']],
    'hr': [['h', 'r'], ['hours'], ['hour']],
    'hrs': [['h', 'r', 's'], ['hours']],

    # Speed
    'mph': [['m', 'p', 'h'], ['miles', 'per', 'hour']],
    'kph': [['k', 'p', 'h'], ['kilometres', 'per', 'hour'], ['kilometers', 'per', 'hour']],
    'fps': [['f', 'p', 's'], ['frames', 'per', 'second']],
    'bps': [['b', 'p', 's'], ['bits', 'per', 'second']],
    'mbps': [['m', 'b', 'p', 's'], ['megabits', 'per', 'second']],
    'gbps': [['g', 'b', 'p', 's'], ['gigabits', 'per', 'second']],

    # Weight
    'kg': [['k', 'g'], ['kilograms'], ['kilos']],
    'g': [['g'], ['grams'], ['gram']],
    'mg': [['m', 'g'], ['milligrams'], ['milligram']],
    'lb': [['l', 'b'], ['pounds'], ['pound']],
    'lbs': [['l', 'b', 's'], ['pounds']],
    'oz': [['o', 'z'], ['ounces'], ['ounce']],

    # Volume
    'l': [['l'], ['litres'], ['liters']],
    'ml': [['m', 'l'], ['millilitres'], ['milliliters']],

    # Temperature
    'c': [['c'], ['celsius'], ['degrees', 'celsius']],
    'f': [['f'], ['fahrenheit'], ['degrees', 'fahrenheit']],

    # Other
    'px': [['p', 'x'], ['pixels'], ['pixel']],
    'db': [['d', 'b'], ['decibels'], ['decibel']],
    'w': [['w'], ['watts'], ['watt']],
    'kw': [['k', 'w'], ['kilowatts'], ['kilowatt']],
    'mw': [['m', 'w'], ['megawatts'], ['megawatt']],
    'v': [['v'], ['volts'], ['volt']],
    'a': [['a'], ['amps'], ['amperes']],
    'ma': [['m', 'a'], ['milliamps'], ['milliamperes']],
}


# Digit to word mapping
DIGIT_WORDS: dict[str, str] = {
    '0': 'zero', '1': 'one', '2': 'two', '3': 'three', '4': 'four',
    '5': 'five', '6': 'six', '7': 'seven', '8': 'eight', '9': 'nine'
}


def is_number_token(token: str) -> bool:
    """Check if a token contains a number pattern that should be expanded.

    Returns True for:
    - Pure integers (100, 1000)
    - Comma-separated integers (1,100)
    - Decimals (3.07, 0.5)
    - Ordinals (1st, 2nd, 23rd)
    - Mixed alphanumeric (M3, 4K, 100GB)

    Returns False for:
    - Regular words
    - Pure punctuation
    """
    stripped = token.strip()
    if not stripped:
        return False

    return any(pattern.match(stripped) for pattern in PATTERNS.values())


def _digit_by_digit(num: int) -> list[str]:
    """Convert number to digit-by-digit pronunciation.

    Args:
        num: Integer to convert

    Returns:
        List of words for each digit

    Examples:
        100 -> ["one", "zero", "zero"]
        1234 -> ["one", "two", "three", "four"]
    """
    return [DIGIT_WORDS[d] for d in str(abs(num))]


def _digits_as_words(digit_str: str, use_oh: bool = False) -> list[str]:
    """Convert a string of digits to spoken words.

    Args:
        digit_str: String of digits (e.g., "07", "33")
        use_oh: If True, use "oh" for zero

    Returns:
        List of words

    Examples:
        "07" with use_oh=False -> ["zero", "seven"]
        "07" with use_oh=True -> ["oh", "seven"]
    """
    result = []
    for d in digit_str:
        if d == '0' and use_oh:
            result.append('oh')
        else:
            result.append(DIGIT_WORDS[d])
    return result


def _num2words_to_list(num: int, ordinal: bool = False) -> list[str]:
    """Convert number using num2words and return as word list.

    Args:
        num: Integer to convert
        ordinal: If True, convert to ordinal form (e.g., "first", "second")

    Returns:
        List of words representing the number
    """
    words: str
    if ordinal:
        words = num2words(num, to='ordinal')
    else:
        words = num2words(num)
    # num2words uses hyphens for compound words like "twenty-one"
    # Also strip commas and other punctuation from words
    words = words.replace('-', ' ').replace(',', '')
    return words.split()


def expand_integer(num: int) -> list[list[str]]:
    """Expand an integer to all spoken alternatives.

    Args:
        num: Integer to expand (e.g., 100, 1100)

    Returns:
        List of alternatives, each is a list of words

    Examples:
        100 -> [["one", "hundred"], ["a", "hundred"], ["one", "zero", "zero"]]
        1100 -> [["one", "thousand", "one", "hundred"], ["eleven", "hundred"],
                 ["one", "one", "zero", "zero"]]
    """
    alternatives: list[list[str]] = []
    abs_num: int = abs(num)

    # Primary: num2words cardinal form
    primary: list[str] = _num2words_to_list(abs_num)
    if num < 0:
        primary = ['minus'] + primary
    alternatives.append(primary)

    # For positive numbers, add common alternative forms
    if num > 0:
        # Alternative with "a" instead of "one" for certain numbers
        if 100 <= abs_num < 200 and primary[0] == 'one':
            alt: list[str] = ['a'] + primary[1:]
            if alt not in alternatives:
                alternatives.append(alt)
        elif 1000 <= abs_num < 2000 and primary[0] == 'one':
            alt = ['a'] + primary[1:]
            if alt not in alternatives:
                alternatives.append(alt)

        # "Eleven hundred" style for 1100-9900 (multiples of 100)
        if 1100 <= abs_num <= 9999 and abs_num % 100 == 0:
            hundreds: int = abs_num // 100
            hundreds_words: list[str] = _num2words_to_list(hundreds)
            alt = hundreds_words + ['hundred']
            if alt not in alternatives:
                alternatives.append(alt)

        # "Twelve hundred" style for non-multiples like 1200, 1500, etc.
        if 1100 <= abs_num <= 9999:
            hundreds = abs_num // 100
            remainder: int = abs_num % 100
            if remainder > 0:
                hundreds_words = _num2words_to_list(hundreds)
                remainder_words: list[str] = _num2words_to_list(remainder)
                alt = hundreds_words + ['hundred'] + remainder_words
                if alt not in alternatives and hundreds >= 11:
                    alternatives.append(alt)

    # Digit-by-digit pronunciation for any number
    digits: list[str] = _digit_by_digit(abs_num)
    if num < 0:
        digits = ['minus'] + digits
    if digits not in alternatives:
        alternatives.append(digits)

    return alternatives


def expand_decimal(num_str: str) -> list[list[str]]:
    """Expand a decimal number to all spoken alternatives.

    Args:
        num_str: Decimal string (e.g., "3.07", "0.5", "0.33")

    Returns:
        List of alternatives, each is a list of words

    Examples:
        "3.07" -> [["three", "point", "zero", "seven"],
                   ["three", "point", "oh", "seven"]]
        "0.3" -> [["zero", "point", "three"], ["point", "three"],
                  ["oh", "point", "three"]]
        "0.5" -> [["zero", "point", "five"], ["point", "five"],
                  ["half"], ["one", "half"], ["a", "half"]]
    """
    alternatives: list[list[str]] = []

    # Handle negative
    is_negative: bool = num_str.startswith('-')
    if is_negative:
        num_str = num_str[1:]

    # Split into integer and decimal parts
    parts: list[str] = num_str.split('.')
    int_part: str = parts[0]
    dec_part: str = parts[1]

    # Get integer part as words
    int_num: int = int(int_part)
    int_words: list[str]
    if int_num == 0:
        int_words = ['zero']
    else:
        int_words = _num2words_to_list(int_num)

    # Standard "X point Y Z" form (digit by digit after point)
    dec_words: list[str] = _digits_as_words(dec_part)
    standard: list[str] = int_words + ['point'] + dec_words
    if is_negative:
        standard = ['minus'] + standard
    alternatives.append(standard)

    # "oh" variant for zeros in decimal: "three point oh seven"
    dec_words_oh: list[str] = _digits_as_words(dec_part, use_oh=True)
    if dec_words_oh != dec_words:
        oh_variant: list[str] = int_words + ['point'] + dec_words_oh
        if is_negative:
            oh_variant = ['minus'] + oh_variant
        if oh_variant not in alternatives:
            alternatives.append(oh_variant)

    # For leading zero decimals (0.xxx)
    if int_num == 0 and not is_negative:
        # Omit leading zero: "point three" instead of "zero point three"
        no_zero: list[str] = ['point'] + dec_words
        if no_zero not in alternatives:
            alternatives.append(no_zero)

        # "oh point three" variant
        oh_start: list[str] = ['oh', 'point'] + dec_words
        if oh_start not in alternatives:
            alternatives.append(oh_start)

    # Check for common fraction equivalents (only for positive numbers)
    if not is_negative and num_str in COMMON_FRACTIONS:
        for fraction_alt in COMMON_FRACTIONS[num_str]:
            if fraction_alt not in alternatives:
                alternatives.append(fraction_alt)

    return alternatives


def expand_ordinal(token: str) -> list[list[str]]:
    """Expand an ordinal number to spoken form.

    Args:
        token: Ordinal string (e.g., "1st", "2nd", "23rd")

    Returns:
        List of alternatives (ordinals typically have one form)

    Examples:
        "1st" -> [["first"]]
        "2nd" -> [["second"]]
        "23rd" -> [["twenty", "third"]]
    """
    match: re.Match[str] | None = PATTERNS['ordinal'].match(token.strip())
    if not match:
        return []

    num: int = int(match.group(1))
    ordinal_words: list[str] = _num2words_to_list(num, ordinal=True)
    return [ordinal_words]


def _expand_unit_suffix(suffix: str) -> list[list[str]]:
    """Expand a unit suffix to possible spoken forms.

    Args:
        suffix: Unit abbreviation (e.g., "gb", "ghz", "k")

    Returns:
        List of alternatives, defaults to spelling out letters
    """
    suffix_lower: str = suffix.lower()

    if suffix_lower in UNIT_EXPANSIONS:
        return UNIT_EXPANSIONS[suffix_lower]

    # Default: spell out each letter
    return [list(suffix_lower)]


def _expand_number_part(num_str: str) -> list[list[str]]:
    """Expand just the number portion of a mixed token.

    Args:
        num_str: Number string which may be integer or decimal

    Returns:
        List of alternatives for the number part
    """
    if '.' in num_str:
        return expand_decimal(num_str)
    else:
        return expand_integer(int(num_str))


def expand_mixed_alphanumeric(token: str) -> list[list[str]]:
    """Expand mixed alphanumeric tokens.

    Args:
        token: Mixed token (e.g., "M3", "4K", "100GB", "4.05GHz")

    Returns:
        List of alternatives

    Examples:
        "M3" -> [["m", "three"]]
        "4K" -> [["four", "k"], ["four", "thousand"]]
        "100GB" -> [["one", "hundred", "g", "b"], ["one", "hundred", "gigabytes"]]
    """
    stripped: str = token.strip()
    alternatives: list[list[str]] = []

    # Check prefix pattern: M3, V8
    prefix_match: re.Match[str] | None = PATTERNS['prefix_mixed'].match(
        stripped)
    if prefix_match:
        letters: str = prefix_match.group(1).lower()
        num_str: str = prefix_match.group(2)

        # Only spell out short prefixes (1-2 chars) like "M3", "V8"
        # Keep longer prefixes as words like "word1" -> ["word", "one"]
        letter_words: list[str]
        if len(letters) <= 2:
            letter_words = list(letters)
        else:
            letter_words = [letters]

        # Expand the number part
        num_expansions: list[list[str]] = _expand_number_part(num_str)

        for num_exp in num_expansions:
            alt: list[str] = letter_words + num_exp
            if alt not in alternatives:
                alternatives.append(alt)

        return alternatives

    # Check suffix pattern: 4K, 100GB, 4.05GHz
    suffix_match: re.Match[str] | None = PATTERNS['suffix_mixed'].match(
        stripped)
    if suffix_match:
        num_str = suffix_match.group(1)
        suffix: str = suffix_match.group(2)

        # Expand the number part
        num_expansions = _expand_number_part(num_str)

        # Expand the suffix (could be abbreviation)
        suffix_expansions: list[list[str]] = _expand_unit_suffix(suffix)

        for num_exp in num_expansions:
            for suffix_exp in suffix_expansions:
                alt = num_exp + suffix_exp
                if alt not in alternatives:
                    alternatives.append(alt)

        return alternatives

    return []


def expand_rate_unit(token: str) -> list[list[str]]:
    """Expand rate unit tokens like 100GB/s, 60fps, 1000MB/s.

    Args:
        token: Rate unit token (e.g., "100GB/s", "1000MB/s")

    Returns:
        List of alternatives

    Examples:
        "100GB/s" -> [["one", "hundred", "g", "b", "per", "s"],
                      ["one", "hundred", "gigabytes", "per", "second"]]
    """
    stripped: str = token.strip()
    alternatives: list[list[str]] = []

    rate_match: re.Match[str] | None = PATTERNS['rate_unit'].match(stripped)
    if not rate_match:
        return []

    num_str: str = rate_match.group(1)
    first_unit: str = rate_match.group(2)
    second_unit: str = rate_match.group(3)

    # Expand the number part
    num_expansions: list[list[str]] = _expand_number_part(num_str)

    # Expand both units
    first_unit_expansions: list[list[str]] = _expand_unit_suffix(first_unit)
    second_unit_expansions: list[list[str]] = _expand_unit_suffix(second_unit)

    for num_exp in num_expansions:
        for first_exp in first_unit_expansions:
            for second_exp in second_unit_expansions:
                alt: list[str] = num_exp + first_exp + ['per'] + second_exp
                if alt not in alternatives:
                    alternatives.append(alt)

    return alternatives


def get_number_expansions(token: str) -> list[list[str]] | None:
    """Get all possible spoken expansions for a number token.

    This is the main entry point, analogous to get_all_expansions() for punctuation.

    Args:
        token: A token that may contain a number

    Returns:
        List of alternatives if token is a number, None otherwise

    Examples:
        "100" -> [["one", "hundred"], ["a", "hundred"], ["one", "zero", "zero"]]
        "1st" -> [["first"]]
        "4K" -> [["four", "k"], ["four", "thousand"]]
        "hello" -> None
    """
    stripped = token.strip()
    if not stripped:
        return None

    # Try ordinal first (most specific pattern with suffix)
    if PATTERNS['ordinal'].match(stripped):
        return expand_ordinal(stripped)

    # Try comma-separated integer
    if PATTERNS['comma_integer'].match(stripped):
        num = int(stripped.replace(',', ''))
        return expand_integer(num)

    # Try decimal
    if PATTERNS['decimal'].match(stripped):
        return expand_decimal(stripped)

    # Try pure integer
    if PATTERNS['integer'].match(stripped):
        return expand_integer(int(stripped))

    # Try mixed alphanumeric (prefix or suffix)
    if PATTERNS['prefix_mixed'].match(stripped) or PATTERNS['suffix_mixed'].match(stripped):
        return expand_mixed_alphanumeric(stripped)

    # Try rate units (100GB/s, 1000MB/s)
    if PATTERNS['rate_unit'].match(stripped):
        return expand_rate_unit(stripped)

    return None


def get_number_expansion_first_words(token: str) -> list[str] | None:
    """Get the first word of each possible expansion for a number token.

    This is useful for matching - if a spoken word matches any of these,
    it could be the start of an expansion for this token.

    Args:
        token: A token that may contain a number

    Returns:
        List of unique first words from all expansions, or None if not a number

    Example:
        get_number_expansion_first_words("100") returns ["one", "a"]
    """
    expansions: list[list[str]] | None = get_number_expansions(token)
    if expansions is None:
        return None
    # Get unique first words
    first_words: list[str] = []
    for exp in expansions:
        if exp and exp[0] not in first_words:
            first_words.append(exp[0])
    return first_words

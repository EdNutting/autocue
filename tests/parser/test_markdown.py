"""
Tests for Markdown handling in script parsing.
"""

import markdown

from src.autocue.script_parser import ParsedScript, parse_script


class TestMarkdownHandling:
    """Tests for Markdown handling in script parsing."""

    def test_markdown_bullets_not_treated_as_minus(self) -> None:
        """Markdown bullet markers (-) should not become 'minus' words."""
        script: str = """Here is a list:

- First item
- Second item
- Third item

End of list."""

        # Render to HTML like the app does
        html: str = markdown.markdown(
            script, extensions=['nl2br', 'sane_lists'])
        parsed: ParsedScript = parse_script(script, html)

        # Get all speakable words
        words: list[str] = [sw.text for sw in parsed.speakable_words]

        # "minus" should NOT appear from bullet markers
        # (only from explicit minus like "5 - 3")
        assert "minus" not in words or words.count("minus") == 0

        # The actual content words should be present
        assert "first" in words
        assert "item" in words
        assert "second" in words

    def test_literal_minus_in_content_expands(self) -> None:
        """Literal '-' in content (not bullet) should expand to 'minus'."""
        script: str = "The answer is 5 - 3 = 2"
        html: str = markdown.markdown(
            script, extensions=['nl2br', 'sane_lists'])
        parsed: ParsedScript = parse_script(script, html)

        words: list[str] = [sw.text for sw in parsed.speakable_words]

        # The '-' between 5 and 3 should expand to "minus"
        assert "minus" in words

    def test_markdown_headers_not_tokenized(self) -> None:
        """Markdown header markers (#) should not appear as tokens."""
        script: str = """# Main Title

## Section One

Some content here.

### Subsection

More content."""

        html: str = markdown.markdown(
            script, extensions=['nl2br', 'sane_lists'])
        parsed: ParsedScript = parse_script(script, html)

        # Get raw token texts
        raw_texts: list[str] = [rt.text for rt in parsed.raw_tokens]

        # No token should be just "#" or start with "#"
        for text in raw_texts:
            assert text != "#"
            assert not text.startswith("#")

    def test_bold_and_italic_content_preserved(self) -> None:
        """Bold and italic content should be extracted without formatting markers."""
        script: str = "This has **bold text** and *italic text* in it."
        html: str = markdown.markdown(
            script, extensions=['nl2br', 'sane_lists'])
        parsed: ParsedScript = parse_script(script, html)

        words: list[str] = [sw.text for sw in parsed.speakable_words]

        # Content words should be present
        assert "bold" in words
        assert "text" in words
        assert "italic" in words

        # Formatting markers should not be words
        for word in words:
            assert "**" not in word
            assert word != "*"

# Copyright © 2025 Ed Nutting
# SPDX-License-Identifier: MIT
# See LICENSE file for details

"""
Tests for Markdown handling in script parsing.
"""

import markdown

from src.autocue.script_parser import (
    ParsedScript,
    SpeakableWord,
    parse_script,
    strip_frontmatter,
)


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

        # Find the expansion words (should include the "-" expansion)
        expansion_words: list[SpeakableWord] = [
            sw for sw in parsed.speakable_words if sw.is_expansion]

        # Should have at least one expansion word with "minus" in its expansions
        has_minus: bool = any(
            any("minus" in exp for exp in sw.all_expansions)
            for sw in expansion_words
        )
        assert has_minus, "Expected '-' to have 'minus' as an expansion"

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


class TestFrontmatterStripping:
    """Tests for YAML frontmatter stripping from Markdown scripts."""

    def test_strip_basic_frontmatter(self) -> None:
        """Basic YAML frontmatter should be removed."""
        script: str = "---\ntitle: My Script\nauthor: Someone\n---\nHello world."
        result: str = strip_frontmatter(script)
        assert result == "Hello world."

    def test_strip_frontmatter_preserves_body(self) -> None:
        """Content after frontmatter should be fully preserved."""
        script: str = "---\nkey: value\n---\nFirst line.\n\nSecond line."
        result: str = strip_frontmatter(script)
        assert result == "First line.\n\nSecond line."

    def test_no_frontmatter_unchanged(self) -> None:
        """Text without frontmatter should be returned unchanged."""
        script: str = "Hello world.\n\nThis is a script."
        result: str = strip_frontmatter(script)
        assert result == script

    def test_frontmatter_must_start_at_beginning(self) -> None:
        """Frontmatter delimiters not at the start should be left alone."""
        script: str = "Some text\n---\ntitle: Not frontmatter\n---\nMore text."
        result: str = strip_frontmatter(script)
        assert result == script

    def test_triple_dash_in_body_not_stripped(self) -> None:
        """A --- divider in the body (after frontmatter) should not be stripped."""
        script: str = "---\ntitle: Test\n---\nContent here.\n\n---\n\nMore content."
        result: str = strip_frontmatter(script)
        assert result == "Content here.\n\n---\n\nMore content."

    def test_empty_frontmatter(self) -> None:
        """Frontmatter with no fields should still be stripped."""
        script: str = "---\n---\nBody text."
        result: str = strip_frontmatter(script)
        assert result == "Body text."

    def test_frontmatter_with_windows_line_endings(self) -> None:
        """Frontmatter with CRLF line endings should be stripped."""
        script: str = "---\r\ntitle: Test\r\n---\r\nBody text."
        result: str = strip_frontmatter(script)
        assert result == "Body text."

    def test_frontmatter_not_rendered_as_words(self) -> None:
        """Frontmatter fields should not appear as speakable words."""
        script: str = "---\ntitle: My Script\nauthor: Someone\n---\nHello world."
        cleaned: str = strip_frontmatter(script)
        html: str = markdown.markdown(
            cleaned, extensions=['nl2br', 'sane_lists'])
        parsed: ParsedScript = parse_script(cleaned, html)
        words: list[str] = [sw.text for sw in parsed.speakable_words]

        assert "hello" in words
        assert "world" in words
        # Frontmatter content should not be present
        assert "title" not in words
        assert "author" not in words
        assert "someone" not in words

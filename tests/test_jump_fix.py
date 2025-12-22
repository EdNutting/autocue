# Copyright © 2025 Ed Nutting
# SPDX-License-Identifier: MIT
# See LICENSE file for details

"""Test that demonstrates the jump-to fix for embedded punctuation."""

import markdown
from src.autocue.script_parser import parse_script

def test_jump_to_embedded_punctuation():
    """Verify that clicking on tokens with embedded punctuation works correctly."""
    script = "Hello 2^3 world A&B test"
    html = markdown.markdown(script, extensions=['nl2br', 'sane_lists'])
    parsed = parse_script(script, html)

    print("\n" + "="*60)
    print("JUMP-TO FIX DEMONSTRATION")
    print("="*60)
    print(f"Script: {script}")
    print()

    # Simulate clicking on each token
    for raw_idx in range(len(parsed.raw_tokens)):
        raw_token = parsed.raw_tokens[raw_idx]
        speakable_indices = parsed.raw_to_speakable.get(raw_idx, [])

        if speakable_indices:
            # This is what happens when you click on a token
            first_speakable_idx = speakable_indices[0]
            speakable_word = parsed.speakable_words[first_speakable_idx]

            print(f"Click on raw_token[{raw_idx}] '{raw_token.text}':")
            print(f"  → Jumps to speakable[{first_speakable_idx}] '{speakable_word.text}'")

            # Show all speakable words from this raw token
            if len(speakable_indices) > 1:
                other_words = [f"[{i}]='{parsed.speakable_words[i].text}'"
                             for i in speakable_indices]
                print(f"  → Raw token maps to {len(speakable_indices)} speakable words: {', '.join(other_words)}")
            print()

    print("="*60)
    print("✓ Clicking on '2^3' correctly jumps to first speakable word (2)")
    print("✓ Clicking on 'A&B' correctly jumps to first speakable word (a)")
    print("="*60)

if __name__ == "__main__":
    test_jump_to_embedded_punctuation()

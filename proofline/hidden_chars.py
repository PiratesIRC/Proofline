"""Local check for characters a reader cannot see: invisible format characters and unusual spaces.

LanguageTool does not flag these (measured on 6.8 with a zero-width space and a thin space), so
Proofline adds its own matches, shown in the popup like any other issue and turned off like a rule.

Rich web editors put invisible placeholder characters into their own text, and Chromium passes
them on to UI Automation (measured 2026-10-25 with Slate's markup in Edge 156: four U+FEFF came
through). Flagging those would show issues nobody typed, so the rules are:
- Never flagged: U+FEFF (Slate, used by Discord; Quill guards around embeds), U+2060 (CKEditor 5
  fills the caret position with seven), U+00A0 (browsers insert it for repeated and trailing
  spaces), U+200C/U+200D (emoji sequences, Persian and Indic spelling).
- Flagged only inside a word, with a letter or digit on both sides: zero-width space (Lexical and
  ProseMirror put one beside widgets and at the caret), soft hyphen, direction marks. Inside a
  word they are pasted text that breaks search, not an editor placeholder.
- Flagged anywhere: bidirectional embedding, override and isolate controls, which can make text
  display in a different order than it is stored, and unusual spaces.
"""

from __future__ import annotations

import re
import unicodedata

from proofline.lt_client import Match

INVISIBLE_RULE = "PROOFLINE_INVISIBLE_CHARACTER"
UNUSUAL_SPACE_RULE = "PROOFLINE_UNUSUAL_SPACE"
HIDDEN_RULES = frozenset({INVISIBLE_RULE, UNUSUAL_SPACE_RULE})
CATEGORY = "Hidden characters"
CATEGORY_ID = "PROOFLINE_HIDDEN"

IN_WORD_CODEPOINTS = (
    0x00AD,  # soft hyphen
    0x180E,  # Mongolian vowel separator
    0x200B,  # zero width space
    0x200E, 0x200F,  # left-to-right / right-to-left mark
    *range(0x2061, 0x2065),  # invisible math operators
)
ANYWHERE_CODEPOINTS = (
    *range(0x202A, 0x202F),  # bidirectional embeddings and overrides
    *range(0x2066, 0x206A),  # bidirectional isolates
)
UNUSUAL_SPACE_CODEPOINTS = (0x1680, *range(0x2000, 0x200B), 0x202F, 0x205F, 0x3000)


def _char_class(codepoints: tuple[int, ...]) -> str:
    return "[" + "".join(re.escape(chr(c)) for c in codepoints) + "]+"


IN_WORD_RUN = re.compile(r"(?<=[^\W_])" + _char_class(IN_WORD_CODEPOINTS) + r"(?=[^\W_])")
ANYWHERE_RUN = re.compile(_char_class(ANYWHERE_CODEPOINTS))
UNUSUAL_SPACE_RUN = re.compile(_char_class(UNUSUAL_SPACE_CODEPOINTS))


def codepoint_label(text: str) -> str:
    """'[U+200B]' per character, so the popup can show what cannot be seen."""
    return "".join(f"[U+{ord(c):04X}]" for c in text)


def _describe(text: str) -> str:
    names = []
    for char in dict.fromkeys(text):  # distinct, in order
        name = unicodedata.name(char, "unnamed character").lower()
        names.append(f"{name} (U+{ord(char):04X})")
    return ", ".join(names)


def _invisible_match(start: int, run: str) -> Match:
    count = "An invisible character" if len(run) == 1 else f"{len(run)} invisible characters"
    return Match(
        start, len(run),
        f"{count}: {_describe(run)}. It can break search, links and copied text.",
        "Invisible character", ("",), INVISIBLE_RULE, CATEGORY, run, CATEGORY_ID,
    )


def _space_match(start: int, run: str) -> Match:
    kind = "an unusual space" if len(run) == 1 else f"{len(run)} unusual spaces"
    return Match(
        start, len(run),
        f"This is {kind}: {_describe(run)}, not a normal space. It can break search and line wrapping.",
        "Unusual space", (" " * len(run),), UNUSUAL_SPACE_RULE, CATEGORY, run, CATEGORY_ID,
    )


def hidden_matches(text: str) -> tuple[Match, ...]:
    """One match per run of invisible characters or unusual spaces, in text order."""
    found = [_invisible_match(m.start(), m.group(0))
             for pattern in (IN_WORD_RUN, ANYWHERE_RUN) for m in pattern.finditer(text)]
    found += [_space_match(m.start(), m.group(0)) for m in UNUSUAL_SPACE_RUN.finditer(text)]
    return tuple(sorted(found, key=lambda match: match.offset))


def is_hidden_match(match: Match) -> bool:
    return match.rule_id in HIDDEN_RULES


def merge_matches(server: tuple[Match, ...], local: tuple[Match, ...]) -> tuple[Match, ...]:
    """Server and local matches together, ordered by position in the text."""
    return tuple(sorted(server + local, key=lambda match: match.offset))

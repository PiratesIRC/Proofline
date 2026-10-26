"""Mark the words an AI rewording changed, as HTML for the card's option buttons."""

from __future__ import annotations

import html
import re
from difflib import SequenceMatcher

_TOKEN = re.compile(r"\S+|\s+")


def changed_words_html(original: str, rewritten: str) -> str:
    """rewritten, escaped, with each run of new or changed words in <b>; spaces between changes join them."""
    old, new = _TOKEN.findall(original), _TOKEN.findall(rewritten)
    flags: list[bool] = []
    for tag, _i1, _i2, j1, j2 in SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        flags.extend([tag != "equal"] * (j2 - j1))
    for k in range(1, len(new) - 1):
        if new[k].isspace() and flags[k - 1] and flags[k + 1]:
            flags[k] = True
    return "".join(_runs(new, flags))


def _runs(tokens: list[str], flags: list[bool]) -> list[str]:
    parts: list[str] = []
    k = 0
    while k < len(tokens):
        if not flags[k] or tokens[k].isspace():
            parts.append(html.escape(tokens[k]))
            k += 1
            continue
        end = k
        while end + 1 < len(tokens) and flags[end + 1]:
            end += 1
        while tokens[end].isspace():  # a run never ends in a space; the first token is a word
            end -= 1
        parts.append("<b>" + "".join(html.escape(t) for t in tokens[k:end + 1]) + "</b>")
        k = end + 1
    return parts

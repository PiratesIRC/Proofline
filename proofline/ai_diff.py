"""Compare an AI rewording with the original: changed words as HTML for the card's option buttons,
and word-level hunks for the rewrite rows in the popup."""

from __future__ import annotations

import html
import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher

_TOKEN = re.compile(r"\S+|\s+")
MAX_DIFF_TOKENS = 6000  # words plus the spaces between them, per side; more is not compared
# The comparison's work grows with the number of (old position, new position) pairs that hold the
# same word. Ordinary prose of the longest allowed length stays far below this; above it the
# words that repeat most are left out of the lining-up (difflib's own shortcut for common items).
MAX_SAME_WORD_PAIRS = 20_000


def _opcodes(old: list[str], new: list[str]) -> list[tuple[str, int, int, int, int]]:
    """How old becomes new, in bounded time whatever the two texts hold.

    The text being compared with comes from an AI server, so its shape cannot be trusted: before
    these limits one answer could keep the app busy for minutes (the cost was cubic in the number
    of repeated tokens). Whitespace tokens are never used to line the two up: the single space
    sits between every pair of words. Two texts too long to compare count as changed throughout.
    """
    if len(old) > MAX_DIFF_TOKENS or len(new) > MAX_DIFF_TOKENS:
        return [("replace", 0, len(old), 0, len(new))]
    repetitive = _same_word_pairs(old, new) > MAX_SAME_WORD_PAIRS
    return SequenceMatcher(str.isspace, old, new, autojunk=repetitive).get_opcodes()


def _same_word_pairs(old: list[str], new: list[str]) -> int:
    counts = Counter(token for token in new if not token.isspace())
    return sum(counts[token] for token in old)


def changed_words_html(original: str, rewritten: str) -> str:
    """rewritten, escaped, with each run of new or changed words in <b>; spaces between changes join them."""
    old, new = _TOKEN.findall(original), _TOKEN.findall(rewritten)
    flags: list[bool] = []
    for tag, _i1, _i2, j1, j2 in _opcodes(old, new):
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


MERGE_GAP_WORDS = 2  # hunks with fewer unchanged words than this between them become one row


@dataclass(frozen=True)
class Hunk:
    """original[start:end] becomes replacement."""

    start: int
    end: int
    replacement: str


def word_hunks(original: str, rewritten: str) -> tuple[Hunk, ...]:
    """The changes from original to rewritten, one per run of changed words, in text order.

    Hunks fewer than MERGE_GAP_WORDS unchanged words apart are merged, so a row reads as a phrase.
    An insertion takes the word before it (or after, at the start) so every hunk covers some text.
    """
    old, new = _TOKEN.findall(original), _TOKEN.findall(rewritten)
    spans = [(i1, i2, j1, j2) for tag, i1, i2, j1, j2
             in _opcodes(old, new) if tag != "equal"]
    merged = _merge(spans, old)
    old_at, new_at = _starts(old), _starts(new)
    hunks = []
    for span in merged:
        i1, i2, j1, j2 = _widen_insertion(span, old) if span[0] == span[1] else span
        if i1 < i2:
            hunks.append(_trimmed(original, Hunk(old_at[i1], old_at[i2], rewritten[new_at[j1]:new_at[j2]])))
    return tuple(hunks)


def _trimmed(original: str, hunk: Hunk) -> Hunk:
    """Drop whitespace that both sides start or end with, so a row never flags a bare space."""
    start, end, replacement = hunk.start, hunk.end, hunk.replacement
    while end > start and replacement and original[end - 1] == replacement[-1] and replacement[-1].isspace():
        end, replacement = end - 1, replacement[:-1]
    while end > start and replacement and original[start] == replacement[0] and replacement[0].isspace():
        start, replacement = start + 1, replacement[1:]
    return Hunk(start, end, replacement)


def _widen_insertion(span: tuple[int, int, int, int], old: list[str]) -> tuple[int, int, int, int]:
    """Take in the nearest unchanged word before the insertion (after it, at the start of the text)."""
    i1, i2, j1, j2 = span
    before = [k for k in range(i1) if not old[k].isspace()]
    if before:
        shift = i1 - before[-1]
        return i1 - shift, i2, j1 - shift, j2
    after = [k for k in range(i2, len(old)) if not old[k].isspace()]
    if after:
        shift = after[0] + 1 - i2
        return i1, i2 + shift, j1, j2 + shift
    return span


def changed_word_share(original: str, hunks: tuple[Hunk, ...]) -> float:
    """The share of original's words inside a hunk, 0.0 to 1.0."""
    total = len(original.split())
    if not total:
        return 0.0
    return sum(len(original[h.start:h.end].split()) for h in hunks) / total


def _merge(spans: list[tuple[int, int, int, int]], old: list[str]) -> list[tuple[int, int, int, int]]:
    merged: list[tuple[int, int, int, int]] = []
    for span in spans:
        if merged:
            p1, p2, q1, _q2 = merged[-1]
            between = [t for t in old[p2:span[0]] if not t.isspace()]
            if len(between) < MERGE_GAP_WORDS:
                merged[-1] = (p1, span[1], q1, span[3])
                continue
        merged.append(span)
    return merged


def _starts(tokens: list[str]) -> list[int]:
    """Character offset of each token, plus the end of the text."""
    starts = [0]
    for token in tokens:
        starts.append(starts[-1] + len(token))
    return starts

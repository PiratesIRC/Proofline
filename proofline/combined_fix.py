"""Several fixes in one field applied as one replacement (Fix all, Accept all AI suggestions)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from proofline.ai_jobs import is_ai_match
from proofline.lt_client import Match

FIX_ALL_RULE_ID = "PROOFLINE_FIX_ALL"
FIX_ALL_CATEGORY = "Fix all"

Fix = tuple[Match, str]  # a match and the replacement chosen for it


def non_overlapping(fixes: Iterable[Fix]) -> tuple[Fix, ...]:
    """fixes in text order, without any that overlap an earlier one (the next check finds those again)."""
    kept: list[Fix] = []
    for match, replacement in sorted(fixes, key=lambda fix: (fix[0].offset, fix[0].length)):
        if kept and match.offset < kept[-1][0].offset + kept[-1][0].length:
            continue
        kept.append((match, replacement))
    return tuple(kept)


def first_suggestions(matches: Iterable[Match]) -> tuple[Fix, ...]:
    """Fix all: each LanguageTool issue with its first suggestion. AI findings have their own Accept all."""
    return non_overlapping((m, m.replacements[0]) for m in matches if m.replacements and not is_ai_match(m))


def combined_match(text: str, fixes: Sequence[Fix], rule_id: str, category: str) -> tuple[Match, str] | None:
    """One match spanning the first to the last fix, and text for that span with every fix made.

    fixes must be in text order and must not overlap (non_overlapping()). None when there are none.
    """
    if not fixes:
        return None
    start, end = fixes[0][0].offset, max(m.offset + m.length for m, _ in fixes)
    parts, position = [], start
    for match, replacement in fixes:
        parts.append(text[position:match.offset] + replacement)
        position = match.offset + match.length
    replacement = "".join(parts) + text[position:end]
    span = Match(start, end - start, "", "", (replacement,), rule_id, category, text[start:end], category)
    return span, replacement

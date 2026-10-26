"""Combining AI findings with LanguageTool's, and moving them across a fix Proofline applied."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

from proofline.lt_client import Match
from proofline.replace_request import ReplaceRequest


@dataclass(frozen=True)
class PendingEdit:
    """A correction Proofline sent: the text it expects the field to hold once it is applied."""

    field_id: tuple[int, ...]
    old_text: str
    new_text: str
    offset: int
    length: int
    replacement: str

    @classmethod
    def from_request(cls, request: ReplaceRequest) -> PendingEdit:
        old = request.text
        new = old[:request.offset] + request.replacement + old[request.offset + request.length:]
        return cls(request.field_id, old, new, request.offset, request.length, request.replacement)


def merge_with_ai(languagetool: tuple[Match, ...], ai: Iterable[Match], dictionary: Iterable[str]) -> tuple[Match, ...]:
    """LanguageTool's matches plus the AI findings that overlap none of them and are not dictionary words."""
    words = {word.strip().casefold() for word in dictionary if word.strip()}
    kept = [m for m in ai
            if m.error_text.strip().casefold() not in words and not any(_overlaps(m, lt) for lt in languagetool)]
    return tuple(sorted((*languagetool, *kept), key=lambda m: (m.offset, m.length)))


def moved_matches(matches: Iterable[Match], edit: PendingEdit, new_text: str) -> tuple[Match, ...]:
    """matches as they sit in new_text after edit; ones overlapping the edit or no longer matching are dropped."""
    delta = len(edit.replacement) - edit.length
    end = edit.offset + edit.length
    moved = []
    for match in matches:
        if match.offset + match.length <= edit.offset:
            candidate = match
        elif match.offset >= end:
            candidate = replace(match, offset=match.offset + delta)
        else:
            continue
        if new_text[candidate.offset:candidate.offset + candidate.length] == candidate.error_text:
            moved.append(candidate)
    return tuple(moved)


def _overlaps(a: Match, b: Match) -> bool:
    return a.offset < b.offset + b.length and b.offset < a.offset + a.length

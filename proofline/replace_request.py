"""The data passed from the popup to the monitor thread when the user picks a correction."""

from __future__ import annotations

from dataclasses import dataclass

from proofline.ai_jobs import is_ai_match
from proofline.lt_client import Match
from proofline.text_snapshot import FieldSnapshot


class ReplaceError(Exception):
    """A correction could not be applied safely; the message is shown to the user."""


@dataclass(frozen=True)
class ReplaceRequest:
    field_id: tuple[int, ...]
    window_title: str
    text: str
    offset: int
    length: int
    error_text: str
    replacement: str
    from_ai: bool = False  # an AI finding or rewrite (counted as an AI rephrase, not a correction)

    @classmethod
    def build(cls, snapshot: FieldSnapshot, match: Match, replacement: str) -> ReplaceRequest:
        return cls(
            field_id=snapshot.field_id,
            window_title=snapshot.window_title,
            text=snapshot.text,
            offset=match.offset,
            length=match.length,
            error_text=match.error_text,
            replacement=replacement,
            from_ai=is_ai_match(match),
        )

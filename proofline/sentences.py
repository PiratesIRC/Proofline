"""Find the sentence holding a text offset, for AI Rephrase.

A simple rule-based splitter: a sentence ends after . ! ? or an ellipsis (plus closing quotes
or brackets) when whitespace or the line end follows, and every line break ends one. It splits
after abbreviations such as "e.g."; the card shows the sentence it picked, so the user sees that.
Offsets are Python string indices, the same as LanguageTool matches use here.
"""

from __future__ import annotations

LINE_BREAKS = "\n\r"
SENTENCE_ENDINGS = ".!?…"
CLOSERS = "\"')]”’"


def sentence_span(text: str, offset: int) -> tuple[int, int] | None:
    """Start and end of the trimmed sentence holding offset; None when that is blank."""
    offset = max(0, min(offset, len(text)))
    line_start = max(text.rfind(c, 0, offset) for c in LINE_BREAKS) + 1
    line_end = min((i for i in (text.find(c, offset) for c in LINE_BREAKS) if i != -1), default=len(text))
    spans = [span for span in _sentences(text, line_start, line_end) if text[span[0]:span[1]].strip()]
    for start, end in spans:
        if offset <= end:
            return _trimmed(text, start, end)
    return _trimmed(text, *spans[-1]) if spans else None


def _sentences(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """Consecutive spans covering text[start:end], split just after each sentence ending."""
    spans = []
    i = start
    while i < end:
        if text[i] in SENTENCE_ENDINGS:
            j = i + 1
            while j < end and text[j] in CLOSERS:
                j += 1
            if j == end or text[j].isspace():
                spans.append((start, j))
                start = j
            i = j
        else:
            i += 1
    spans.append((start, end))
    return spans


def _trimmed(text: str, start: int, end: int) -> tuple[int, int] | None:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return (start, end) if end > start else None

"""Find the earlier messages quoted in an email reply or forward, so only new text is checked.

A mail editor hands over the whole message body as one text: what the user is typing and,
under it, the conversation being answered. Proofline sees plain text only (no quote
formatting), so the quoted part is found by the lines mail programs put in front of it:

- a header block: "From:" then "Sent:" or "Date:" on the next lines (Outlook, new Outlook,
  Outlook on the web, forwards in most programs), also in German, French, Spanish, Dutch,
  Italian and Portuguese;
- a separator line: "-----Original Message-----", "---------- Forwarded message ---------",
  "-------- Forwarded Message --------";
- an attribution line: "On <date>, <name> wrote:" (Gmail, Thunderbird, Apple Mail).

Everything from a header block or separator to the end of the text is quoted: those programs
put the reply above it. An attribution line is different, because Thunderbird by default puts
the reply BELOW the quote. So after "On ... wrote:" the rest counts as quoted only when the
user has typed something above that line; otherwise only the lines that start with ">" do.
A wrong guess must never hide the user's own text from the checker.

Nothing here touches Windows APIs. Ranges are Python string indices, start inclusive, end
exclusive, in order and not overlapping.
"""

from __future__ import annotations

import re

Range = tuple[int, int]

HEADER_LOOKAHEAD_LINES = 4  # "Sent:" must follow "From:" within this many non-empty lines
ATTRIBUTION_MAX_CHARS = 200
_FROM_WORDS = ("From", "Von", "De", "Van", "Da")
_SENT_WORDS = ("Sent", "Date", "Gesendet", "Datum", "Envoyé", "Enviado", "Enviado el", "Enviada em",
               "Verzonden", "Inviato", "Fecha", "Data")
_LABEL = r"^[ \t>*]*(?:{words})[ \t]*:"
FROM_LINE = re.compile(_LABEL.format(words="|".join(_FROM_WORDS)) + r"[ \t]*\S", re.IGNORECASE)
SENT_LINE = re.compile(_LABEL.format(words="|".join(re.escape(w) for w in _SENT_WORDS)), re.IGNORECASE)
SEPARATOR_LINE = re.compile(
    r"^[ \t>]*-{2,}[ \t]*(?:Original Message|Forwarded message|Ursprüngliche Nachricht|Weitergeleitete Nachricht|"
    r"Message d'origine|Mensaje original|Oorspronkelijk bericht|Messaggio originale|Mensagem original)"
    r"[ \t]*-{2,}[ \t]*$",
    re.IGNORECASE,
)
RULE_LINE = re.compile(r"^[ \t]*[_\-]{8,}[ \t]*$")  # the line Outlook draws above its header block
ATTRIBUTION_LINE = re.compile(
    r"^[ \t]*(?:On|Am|Le|El|Op|Il|Em)\b.{4," + str(ATTRIBUTION_MAX_CHARS) + r"}\b"
    r"(?:wrote|a écrit|escribió|ha scritto|escreveu|(?:schrieb|schreef)(?:[ \t][^:]{1,80})?)[ \t]*:[ \t]*$",
    re.IGNORECASE,
)
QUOTE_PREFIX_LINE = re.compile(r"^[ \t]*>")


def quoted_ranges(text: str) -> tuple[Range, ...]:
    """The parts of text that are earlier messages; () when none is found."""
    lines = _lines(text)
    for index, (start, line) in enumerate(lines):
        if SEPARATOR_LINE.match(line) or _starts_header_block(lines, index):
            return ((_back_over_rule(lines, index), len(text)),)
        if ATTRIBUTION_LINE.match(line):
            if text[:start].strip():  # the user typed above it: the reply is on top
                return ((start, len(text)),)
            return _prefixed_ranges(lines[index + 1:], first=(start, start + len(line)))
    return ()


def checked_part(text: str, ranges: tuple[Range, ...]) -> str:
    """The text to send for checking: cut where the quoted part runs to the end, so the
    earlier messages are not sent at all. Offsets in what is left stay the same."""
    if ranges and ranges[-1][1] >= len(text):
        return text[:ranges[-1][0]]
    return text


def in_ranges(offset: int, ranges: tuple[Range, ...]) -> bool:
    return any(start <= offset < end for start, end in ranges)


def _lines(text: str) -> list[tuple[int, str]]:
    """Each line with the index where it starts; line ends are \\n, \\r\\n, \\r or the vertical tab
    Word uses for a soft line break."""
    lines, start = [], 0
    for match in re.finditer(r"\r\n|[\n\r\v]", text):
        lines.append((start, text[start:match.start()]))
        start = match.end()
    lines.append((start, text[start:]))
    return lines


def _starts_header_block(lines: list[tuple[int, str]], index: int) -> bool:
    if not FROM_LINE.match(lines[index][1]):
        return False
    following = [line for _start, line in lines[index + 1:] if line.strip()][:HEADER_LOOKAHEAD_LINES]
    return any(SENT_LINE.match(line) for line in following)


def _back_over_rule(lines: list[tuple[int, str]], index: int) -> int:
    """Where the quoted part starts: the header line, or the ruled line just above it."""
    previous = index - 1
    while previous >= 0 and not lines[previous][1].strip():
        previous -= 1
    if previous >= 0 and RULE_LINE.match(lines[previous][1]):
        return lines[previous][0]
    return lines[index][0]


def _prefixed_ranges(lines: list[tuple[int, str]], first: Range) -> tuple[Range, ...]:
    """The attribution line, then each run of lines that start with ">"."""
    ranges = [first]
    for start, line in lines:
        if not QUOTE_PREFIX_LINE.match(line):
            continue
        end = start + len(line)
        if start - ranges[-1][1] <= 2:  # only a line break between them: one range
            ranges[-1] = (ranges[-1][0], end)
        else:
            ranges.append((start, end))
    return tuple(ranges)

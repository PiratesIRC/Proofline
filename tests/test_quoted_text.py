"""Earlier messages in a reply or forward are found and left out of the check; date and time
boxes are skipped."""

from dataclasses import replace

import pytest
from factories import snapshot

from proofline.checker import GrammarChecker, cache_key
from proofline.config import Config
from proofline.field_filters import (
    REASON_DATE_TIME,
    REASON_NUMBERS_ONLY,
    text_skip_reason,
)
from proofline.lt_client import Match
from proofline.quoted_text import checked_part, in_ranges, quoted_ranges

NEW = "Thanks, I will sent it tomorow.\n\n"
OUTLOOK = ("From: Dana Example <dana@lt.example>\nSent: Monday, November 16, 2026 9:14 AM\n"
           "To: Sam Example <sam@lt.example>\nSubject: RE: Budget\n\nCan you sent the the file?\n")


def quoted_text(text):
    return "".join(text[start:end] for start, end in quoted_ranges(text))


# ----- header blocks ---------------------------------------------------------

def test_outlook_header_block_starts_the_quoted_part():
    text = NEW + OUTLOOK
    assert quoted_ranges(text) == ((len(NEW), len(text)),)
    assert checked_part(text, quoted_ranges(text)) == NEW


def test_outlook_reply_with_nothing_typed_yet_checks_nothing():
    text = "\n\n" + OUTLOOK
    assert checked_part(text, quoted_ranges(text)).strip() == ""


def test_the_ruled_line_above_the_header_belongs_to_the_quote():
    text = NEW + "________________________________\n" + OUTLOOK
    assert checked_part(text, quoted_ranges(text)) == NEW


@pytest.mark.parametrize("line_end", ["\r\n", "\r", "\v"])
def test_other_line_ends_are_understood(line_end):
    text = (NEW + OUTLOOK).replace("\n", line_end)
    assert checked_part(text, quoted_ranges(text)) == NEW.replace("\n", line_end)


@pytest.mark.parametrize(("sender", "sent"), [
    ("Von: Dana Example", "Gesendet: Montag, 16. November 2026 09:14"),
    ("De : Dana Example", "Envoyé : lundi 16 novembre 2026 09:14"),
    ("De: Dana Example", "Enviado el: lunes, 16 de noviembre de 2026 9:14"),
    ("Van: Dana Example", "Verzonden: maandag 16 november 2026 09:14"),
    ("Da: Dana Example", "Inviato: lunedì 16 novembre 2026 09:14"),
    ("From: Dana Example", "Date: Mon, 16 Nov 2026 09:14:00 -0600"),
])
def test_header_blocks_in_other_languages_and_forwards(sender, sent):
    text = f"{NEW}{sender}\n{sent}\nSubject: x\n\nold text\n"
    assert checked_part(text, quoted_ranges(text)) == NEW


def test_new_outlook_puts_a_blank_line_between_header_lines():
    text = NEW + "From: Dana Example <dana@lt.example>\n\nSent: Monday, November 16, 2026 9:14 AM\n\nTo: Sam\n\nold\n"
    assert checked_part(text, quoted_ranges(text)) == NEW


@pytest.mark.parametrize("text", [
    "From: the desk of Dana\nI think we should go.\nIt were good.\n",  # no Sent or Date line follows
    "The parcel is from: Berlin\nSent: yesterday\n",  # "from:" is not at the start of its line
    "From:\nSent: nothing\n",  # an empty From line, as in a form the user is filling in
    "Notes from the meeting. We sent the file on Monday.\n",
])
def test_ordinary_text_is_not_taken_for_a_header_block(text):
    assert quoted_ranges(text) == ()


# ----- separator lines -------------------------------------------------------

@pytest.mark.parametrize("separator", [
    "-----Original Message-----",
    "---------- Forwarded message ---------",
    "-------- Forwarded Message --------",
    "-----Ursprüngliche Nachricht-----",
])
def test_separator_lines_start_the_quoted_part(separator):
    text = f"{NEW}{separator}\nold text with a eror\n"
    assert checked_part(text, quoted_ranges(text)) == NEW


def test_a_plain_row_of_dashes_is_not_a_separator():
    assert quoted_ranges("First part\n----------\nSecond part with a eror\n") == ()


# ----- attribution lines -----------------------------------------------------

ATTRIBUTION = "On Mon, Nov 16, 2026 at 9:14 AM Dana Example <dana@lt.example> wrote:"


def test_reply_typed_above_an_attribution_line_cuts_the_rest():
    text = f"{NEW}{ATTRIBUTION}\n\nold text with a eror\n"
    assert checked_part(text, quoted_ranges(text)) == NEW


def test_reply_below_the_quote_is_still_checked():
    """Thunderbird's default: nothing above the attribution line, the reply under the quote."""
    reply = "\nMy anser is yes.\n"
    text = f"{ATTRIBUTION}\n> old text with a eror\n> more\n{reply}"
    ranges = quoted_ranges(text)
    assert checked_part(text, ranges) == text  # nothing is cut off the end
    assert quoted_text(text) == f"{ATTRIBUTION}\n> old text with a eror\n> more"
    assert not in_ranges(text.index("anser"), ranges)
    assert in_ranges(text.index("eror"), ranges)


def test_unmarked_quote_under_an_attribution_line_is_checked_rather_than_guessed():
    text = f"{ATTRIBUTION}\nold text with a eror\n\nMy anser is yes.\n"
    assert quoted_text(text) == ATTRIBUTION
    assert not in_ranges(text.index("anser"), quoted_ranges(text))


@pytest.mark.parametrize("line", [
    "Am 16.11.2026 um 09:14 schrieb Dana Example:",
    "Le lun. 16 nov. 2026 à 09:14, Dana Example a écrit :",
    "El lun, 16 nov 2026 a las 9:14, Dana Example escribió:",
    "Op ma 16 nov 2026 om 09:14 schreef Dana Example:",
])
def test_attribution_lines_in_other_languages(line):
    text = f"{NEW}{line}\nold\n"
    assert checked_part(text, quoted_ranges(text)) == NEW


@pytest.mark.parametrize("text", [
    "On Monday I wrote the report.\nIt were long.\n",
    "On the whole, she wrote: yes.\nFine.\n",  # the colon is not at the end of the line
    "Only one line",
    "",
])
def test_ordinary_text_is_not_taken_for_an_attribution(text):
    assert quoted_ranges(text) == ()


# ----- checker ---------------------------------------------------------------

class RecordingClient:
    def __init__(self, sent):
        self.sent = sent

    def check(self, text):
        self.sent.append(text)
        return tuple(Match(text.index(word), len(word), "m", "s", ("x",), "R", "C", word)
                     for word in ("tomorow", "eror", "anser") if word in text)


def run_check(qtbot, text, config=None):
    config = config or Config(server_url="http://lan-server:8081/v2/check")
    sent = []
    checker = GrammarChecker(lambda: config, lambda _config: RecordingClient(sent))
    with qtbot.waitSignal(checker.checked) as blocker:
        checker.check(snapshot(text=text))
    return sent, [match.error_text for match in blocker.args[1]]


def test_only_the_new_text_is_sent_to_the_server(qtbot):
    sent, found = run_check(qtbot, f"{NEW}{OUTLOOK}Another eror here.\n")
    assert sent == [NEW]
    assert found == ["tomorow"]


def test_nothing_is_sent_when_only_the_quote_is_there(qtbot):
    sent, found = run_check(qtbot, "\n\n" + OUTLOOK)
    assert sent == [] and found == []


def test_issues_inside_marked_quote_lines_are_dropped_but_the_reply_below_is_kept(qtbot):
    text = f"{ATTRIBUTION}\n> old text with a eror\n\nMy anser is yes.\n"
    sent, found = run_check(qtbot, text)
    assert sent == [text]
    assert found == ["anser"]


def test_turned_off_checks_the_whole_text(qtbot):
    config = Config(server_url="http://lan-server:8081/v2/check", skip_quoted_replies=False)
    text = f"{NEW}{OUTLOOK}Another eror here.\n"
    sent, found = run_check(qtbot, text, config)
    assert sent == [text]
    assert found == ["tomorow", "eror"]


def test_the_setting_is_on_by_default_and_part_of_the_cache_key():
    config = Config()
    assert config.skip_quoted_replies is True
    assert cache_key(config, "x") != cache_key(replace(config, skip_quoted_replies=False), "x")


# ----- date and time boxes ---------------------------------------------------

@pytest.mark.parametrize("text", [
    "Mon 11/23/2026", "8:00 AM", "8:00 PM", "11/23/2026 8:00 AM", "Monday, November 23, 2026",
    "November 23, 2026 at 2:30 PM", "23rd Nov 2026", "Thu 3 Dec", "2026-11-23T14:30Z", "9:00 a.m.",
    "Sept 5 to Sept 9", "14:30 UTC", " Fri 1/2/2026 ",
])
def test_a_date_or_time_alone_is_not_checked(text):
    assert text_skip_reason(text) == REASON_DATE_TIME


@pytest.mark.parametrize("text", [
    "Meet me at 8:00 AM", "Call Sam on Mon 11/23", "I have 2 apples", "May 5 is fine with me", "Room 12b",
    "The 3rd may work", "v2 of the plan",
])
def test_prose_with_a_date_in_it_is_still_checked(text):
    assert text_skip_reason(text) == ""


def test_a_long_run_of_dates_is_checked_as_text():
    assert text_skip_reason("Mon 11/23/2026 Tue 11/24/2026 Wed 11/25/2026 Thu 11/26/2026") == ""


def test_numbers_only_and_plain_words_keep_their_old_answers():
    assert text_skip_reason("1234 5678") == REASON_NUMBERS_ONLY
    assert text_skip_reason("Monday") == ""  # no digit: left to the other rules
    assert text_skip_reason("") == ""

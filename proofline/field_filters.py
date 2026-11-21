"""Decide whether a focused text field should be skipped by the checker.

A field is skipped when it is an address bar, a dropdown (combo box), a search box, a
numeric/spinner control, a user name or email field, looks sensitive (passwords, card numbers,
tokens) based on its UIA name, placeholder and automation id, or holds only numbers. A document
control's name is ignored by the label rules (an Outlook message body is named after its subject).
Nothing here touches Windows APIs, so it can be
unit tested anywhere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

ADDRESS_BAR_CLASS_MARKERS = (
    "UrlBar-UrlField",  # Vivaldi
    "OmniboxViewViews",  # Chrome and Edge views omnibox
    "Chrome_OmniboxView",  # older Chrome omnibox
    "urlbar-input",  # Firefox
)
ADDRESS_BAR_AUTOMATION_ID = "urlbar-input"
SPINNER_CONTROL_TYPE = "SpinnerControl"
COMBO_BOX_CONTROL_TYPE = "ComboBoxControl"
COMBO_BOX_CLASS_MARKER = "combobox"  # Win32 REComboBox20W (Outlook reminder snooze), web combobox inputs
DOCUMENT_CONTROL_TYPE = "DocumentControl"

REASON_ADDRESS_BAR = "address bar"
REASON_DROPDOWN = "dropdown (combo box)"
REASON_SEARCH = "search field"
REASON_NUMERIC = "numeric field"
REASON_NUMBERS_ONLY = "numeric field (numbers only)"
REASON_DATE_TIME = "date or time field"
REASON_ACCOUNT_PREFIX = "account field"
DATE_TIME_MAX_CHARS = 40
WORD_PATTERN = re.compile(r"[^\W\d_]+")  # runs of letters
_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
           "november", "december")
# Full names, three-letter forms ("mon", "nov"), the other usual short forms, AM/PM, ordinal endings
# ("23rd"), time zone marks and the joining words a date-and-time box shows.
DATE_TIME_WORDS = frozenset({
    *_DAYS, *(day[:3] for day in _DAYS), "tues", "thur", "thurs",
    *_MONTHS, *(month[:3] for month in _MONTHS), "sept",
    "am", "pm", "a", "p", "m", "st", "nd", "rd", "th", "utc", "gmt", "z", "t", "at", "to",
})
REASON_SENSITIVE_PREFIX = "sensitive field"

_WORD_START = r"(?<![a-z0-9])"
_WORD_END = r"(?![a-z0-9])"
_SEP = r"[\s_-]?"

# Each phrase is a regex fragment. Word boundaries are added around the whole
# alternation so "pin" never matches inside "spinning" or "pinned".
_SENSITIVE_PHRASES = (
    rf"pass{_SEP}(?:words?|codes?|phrases?)",
    rf"one{_SEP}time{_SEP}code",
    r"otp",
    rf"verification{_SEP}code",
    rf"security{_SEP}code",
    rf"auth(?:entication)?{_SEP}code",
    rf"(?:enter|secure|access|sms|login|sign{_SEP}in|backup|recovery|time{_SEP}based){_SEP}code",
    rf"(?:2fa|mfa)(?:{_SEP}code)?",
    r"pin",
    r"cvv|cvc|csc",
    rf"card{_SEP}number",
    r"credit" + _SEP + r"card",
    r"debit" + _SEP + r"card",
    rf"card{_SEP}no",
    rf"cc{_SEP}(?:number|num|csc|cvc|exp(?:iry|iration)?)",
    rf"exp(?:iry|iration){_SEP}date",
    rf"routing{_SEP}number",
    rf"account{_SEP}number",
    r"iban",
    r"ssn",
    rf"social{_SEP}security",
    rf"tax{_SEP}id",
    rf"(?:api|access|secret){_SEP}key",
    rf"client{_SEP}secret",
    r"token",
)
# A search box: "search" as a word in the name, help text or UIA type ("search box" in
# Chromium and Firefox for <input type=search>), or a camelCase part of an id or class
# ("SearchEditBox", "txtSearch"). "Research" and "researchNotes" do not match.
SEARCH_WORD_PATTERN = re.compile(_WORD_START + "search", re.IGNORECASE)
SEARCH_ID_PATTERN = re.compile(r"(?<![A-Za-z])[Ss]earch|Search|SEARCH")

SENSITIVE_PATTERN = re.compile(
    _WORD_START + "(?:" + "|".join(_SENSITIVE_PHRASES) + ")" + _WORD_END,
    re.IGNORECASE,
)
# Sign-in identifiers: user names and email addresses. Also matched against the class name,
# because web forms often carry it only there ("form-control-email").
_ACCOUNT_PHRASES = (
    rf"user{_SEP}names?",
    rf"user{_SEP}ids?",
    rf"(?:log{_SEP}in|log{_SEP}on|sign{_SEP}in){_SEP}(?:names?|ids?)",
    # "Email body", "Email message" and the like are where people write prose.
    rf"e{_SEP}mails?(?!{_SEP}(?:body|message|text|content|draft|reply|signature|template|subject))",
)
# camelCase word starts in an id or class ("txtPassword", "APIKey"): a space is put there before
# matching, so "Password" and "Key" start words. Labels and help text are matched as written.
CAMEL_CASE_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
ACCOUNT_PATTERN = re.compile(
    _WORD_START + "(?:" + "|".join(_ACCOUNT_PHRASES) + ")" + _WORD_END,
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FieldTraits:
    """UIA properties of a focused editable field, as read from the desktop."""

    control_type: str
    class_name: str
    name: str
    help_text: str
    automation_id: str
    has_range_value: bool
    localized_control_type: str = ""


def skip_reason(traits: FieldTraits) -> str:
    """Return why the field should not be checked, or "" to allow checking."""
    if _is_address_bar(traits):
        return REASON_ADDRESS_BAR
    if _is_dropdown(traits):
        return REASON_DROPDOWN
    if _is_numeric(traits):
        return REASON_NUMERIC
    if traits.control_type == DOCUMENT_CONTROL_TYPE:
        # A document's name is its title (an Outlook body is named after the email subject), not a
        # field label; its help text, automation id and class are still checked.
        traits = replace(traits, name="")
    if _is_search(traits):
        return REASON_SEARCH
    phrase = _sensitive_phrase(traits)
    if phrase:
        return f"{REASON_SENSITIVE_PREFIX} ({phrase})"
    phrase = _account_phrase(traits)
    if phrase:
        return f"{REASON_ACCOUNT_PREFIX} ({phrase})"
    return ""


def text_skip_reason(text: str) -> str:
    """Return why the field's current text should not be checked, or "" to allow checking.

    Text with at least one digit and no letters (IP addresses, amounts, dates, codes, phone
    numbers) is not prose.
    """
    if not any(ch.isdigit() for ch in text):
        return ""
    if not any(ch.isalpha() for ch in text):
        return REASON_NUMBERS_ONLY
    return REASON_DATE_TIME if _is_date_or_time(text) else ""


def _is_date_or_time(text: str) -> bool:
    """True for a short text that is only a date, a time or both: "Mon 11/23/2026", "8:00 AM",
    "November 23, 2026 at 2:30 PM", "23rd Nov 2026" (a date or time box in a meeting form).
    Every word in it must be a day name, a month name or one of the few words such boxes use."""
    text = text.strip()
    if len(text) > DATE_TIME_MAX_CHARS:
        return False
    words = WORD_PATTERN.findall(text.casefold())
    return all(word in DATE_TIME_WORDS for word in words)


def _is_dropdown(traits: FieldTraits) -> bool:
    if traits.control_type == COMBO_BOX_CONTROL_TYPE:
        return True
    return COMBO_BOX_CLASS_MARKER in traits.class_name.casefold()


def _is_address_bar(traits: FieldTraits) -> bool:
    class_name = traits.class_name.casefold()
    if any(marker.casefold() in class_name for marker in ADDRESS_BAR_CLASS_MARKERS):
        return True
    return ADDRESS_BAR_AUTOMATION_ID in traits.automation_id.casefold()


def _is_search(traits: FieldTraits) -> bool:
    if any(SEARCH_WORD_PATTERN.search(text) for text in (traits.name, traits.help_text, traits.localized_control_type)):
        return True
    return any(SEARCH_ID_PATTERN.search(text) for text in (traits.automation_id, traits.class_name))


def _is_numeric(traits: FieldTraits) -> bool:
    return traits.has_range_value or traits.control_type == SPINNER_CONTROL_TYPE


def _sensitive_phrase(traits: FieldTraits) -> str:
    """Return the first sensitive phrase found in name, help text or automation id."""
    for text in (traits.name, traits.help_text, *_id_forms(traits.automation_id)):
        match = SENSITIVE_PATTERN.search(text)
        if match:
            return match.group(0).lower()
    return ""


def _account_phrase(traits: FieldTraits) -> str:
    """Return the first user name or email phrase found in the label, help text, id or class."""
    for text in (traits.name, traits.help_text, *_id_forms(traits.automation_id), *_id_forms(traits.class_name)):
        match = ACCOUNT_PATTERN.search(text)
        if match:
            return match.group(0).lower()
    return ""


def _id_forms(text: str) -> tuple[str, str]:
    """An id or class as written, then split at camelCase boundaries. Both are matched: the split
    finds "txtPassword", and the original still finds "passWord" (split into "pass Word")."""
    return text, CAMEL_CASE_BOUNDARY.sub(" ", text)

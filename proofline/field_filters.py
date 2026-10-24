"""Decide whether a focused text field should be skipped by the checker.

A field is skipped when it is an address bar, a numeric/spinner control, or
looks sensitive (passwords, card numbers, tokens) based on its UIA name,
placeholder and automation id. Nothing here touches Windows APIs, so it can be
unit tested anywhere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ADDRESS_BAR_CLASS_MARKERS = (
    "UrlBar-UrlField",  # Vivaldi
    "OmniboxViewViews",  # Chrome and Edge views omnibox
    "Chrome_OmniboxView",  # older Chrome omnibox
    "urlbar-input",  # Firefox
)
ADDRESS_BAR_AUTOMATION_ID = "urlbar-input"
SPINNER_CONTROL_TYPE = "SpinnerControl"

REASON_ADDRESS_BAR = "address bar"
REASON_NUMERIC = "numeric field"
REASON_SENSITIVE_PREFIX = "sensitive field"

_WORD_START = r"(?<![a-z0-9])"
_WORD_END = r"(?![a-z0-9])"
_SEP = r"[\s_-]?"

# Each phrase is a regex fragment. Word boundaries are added around the whole
# alternation so "pin" never matches inside "spinning" or "pinned".
_SENSITIVE_PHRASES = (
    r"passwords?|passcodes?|passphrases?",
    rf"one{_SEP}time{_SEP}code",
    r"otp",
    rf"verification{_SEP}code",
    rf"security{_SEP}code",
    rf"auth(?:entication)?{_SEP}code",
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
SENSITIVE_PATTERN = re.compile(
    _WORD_START + "(?:" + "|".join(_SENSITIVE_PHRASES) + ")" + _WORD_END,
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


def skip_reason(traits: FieldTraits) -> str:
    """Return why the field should not be checked, or "" to allow checking."""
    if _is_address_bar(traits):
        return REASON_ADDRESS_BAR
    if _is_numeric(traits):
        return REASON_NUMERIC
    phrase = _sensitive_phrase(traits)
    if phrase:
        return f"{REASON_SENSITIVE_PREFIX} ({phrase})"
    return ""


def _is_address_bar(traits: FieldTraits) -> bool:
    class_name = traits.class_name.casefold()
    if any(marker.casefold() in class_name for marker in ADDRESS_BAR_CLASS_MARKERS):
        return True
    return ADDRESS_BAR_AUTOMATION_ID in traits.automation_id.casefold()


def _is_numeric(traits: FieldTraits) -> bool:
    return traits.has_range_value or traits.control_type == SPINNER_CONTROL_TYPE


def _sensitive_phrase(traits: FieldTraits) -> str:
    """Return the first sensitive phrase found in name, help text or automation id."""
    for text in (traits.name, traits.help_text, traits.automation_id):
        match = SENSITIVE_PATTERN.search(text)
        if match:
            return match.group(0).lower()
    return ""

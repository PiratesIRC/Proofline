"""Filtering of LanguageTool matches by personal dictionary words and session ignores."""

from __future__ import annotations

from collections.abc import Iterable

from proofline.lt_client import Match

SPELLING_CATEGORY_IDS = frozenset({"TYPOS"})
SPELLING_RULE_MARKERS = ("MORFOLOGIK", "HUNSPELL", "SPELLER")


def is_spelling_match(match: Match) -> bool:
    """Return True when the match is a spelling issue, by category or by rule id."""
    if match.category_id in SPELLING_CATEGORY_IDS:
        return True
    rule_id = match.rule_id.upper()
    return any(marker in rule_id for marker in SPELLING_RULE_MARKERS)


def ignore_key(match: Match) -> tuple[str, str]:
    """Return the key used to ignore a match: its rule id and flagged text."""
    return (match.rule_id, match.error_text)


def _normalise_word(word: str) -> str:
    return word.strip().casefold()


def _is_dictionary_word(match: Match, folded_words: frozenset[str]) -> bool:
    return is_spelling_match(match) and _normalise_word(match.error_text) in folded_words


def filter_matches(
    matches: tuple[Match, ...],
    dictionary: Iterable[str] = (),
    ignored: Iterable[tuple[str, str]] = (),
) -> tuple[Match, ...]:
    """Drop spelling matches whose text is in the dictionary and matches whose key is ignored.

    Dictionary comparison is case-insensitive. Order is preserved and the inputs are not modified.
    """
    folded_words = frozenset(word for word in map(_normalise_word, dictionary) if word)
    ignored_keys = frozenset(ignored)
    return tuple(
        match
        for match in matches
        if not _is_dictionary_word(match, folded_words) and ignore_key(match) not in ignored_keys
    )

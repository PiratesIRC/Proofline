from factories import issue_match

from proofline.combined_fix import (
    FIX_ALL_RULE_ID,
    combined_match,
    first_suggestions,
    non_overlapping,
)
from proofline.lt_client import Match

TEXT = "Thsi are a tset."
THSI = Match(0, 4, "Spelling", "", ("This", "Thai"), "MORFOLOGIK_RULE_EN_US", "Typos", "Thsi", "TYPOS")
ARE = Match(5, 3, "Did you mean 'is'?", "", ("is",), "PLURAL_VERB", "Grammar", "are", "GRAMMAR")
TSET = Match(11, 4, "Spelling", "", ("test",), "MORFOLOGIK_RULE_EN_US", "Typos", "tset", "TYPOS")


def test_first_suggestions_takes_each_issues_first_fix_in_text_order():
    assert first_suggestions((TSET, ARE, THSI)) == ((THSI, "This"), (ARE, "is"), (TSET, "test"))


def test_first_suggestions_leaves_out_ai_findings_and_issues_without_a_fix():
    no_fix = Match(5, 3, "m", "", (), "RULE", "Grammar", "are", "GRAMMAR")
    assert first_suggestions((THSI, no_fix, issue_match("tset", offset=11, replacement="test"))) == ((THSI, "This"),)


def test_overlapping_fixes_keep_the_earlier_and_at_one_start_the_shorter():
    wide = Match(0, 8, "m", "", ("This is",), "RULE", "Grammar", "Thsi are", "GRAMMAR")
    assert non_overlapping(((ARE, "is"), (wide, "This is"), (THSI, "This"))) == ((THSI, "This"), (ARE, "is"))
    assert non_overlapping(((wide, "This is"), (ARE, "is"))) == ((wide, "This is"),)


def test_combined_match_spans_first_to_last_fix_with_every_fix_made():
    span, replacement = combined_match(TEXT, first_suggestions((THSI, ARE, TSET)), FIX_ALL_RULE_ID, "Fix all")
    assert (span.offset, span.length, span.error_text) == (0, 15, "Thsi are a tset")
    assert replacement == "This is a test"
    assert span.rule_id == FIX_ALL_RULE_ID


def test_combined_match_of_nothing_is_none():
    assert combined_match(TEXT, (), FIX_ALL_RULE_ID, "Fix all") is None

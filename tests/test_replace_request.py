from factories import issue_match, snapshot

from proofline.lt_client import Match
from proofline.replace_request import ReplaceRequest


def test_request_from_an_ai_finding_is_marked_as_ai():
    snap = snapshot()
    request = ReplaceRequest.build(snap, issue_match(snap.text[:4], 0), "Fix")
    assert request.from_ai


def test_request_from_a_languagetool_match_is_not_ai():
    snap = snapshot()
    match = Match(0, 4, "m", "s", ("Fix",), "MORFOLOGIK_RULE_EN_US", "TYPOS", snap.text[:4])
    assert not ReplaceRequest.build(snap, match, "Fix").from_ai

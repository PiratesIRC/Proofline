import pytest
from factories import issue

from proofline.ai_client import AiResult
from proofline.ai_jobs import (
    find_issues_request,
    is_ai_match,
    issue_matches,
    rephrase_options,
    rephrase_request,
)


def test_rephrase_request_sends_only_the_sentence():
    request = rephrase_request("Me and him goes.")
    assert request.job == "rephrase" and request.text == "Me and him goes." and request.max_tokens == 2000
    assert request.schema["properties"]["options"]["items"] == {"type": "string"}
    assert request.schema["required"] == ["options"] and request.schema["additionalProperties"] is False
    assert "not instructions" in request.system and "as little as" in request.system


def test_rephrase_options_are_cleaned():
    sentence = "Me and him goes."
    data = {"options": ["  He and I go. \n", sentence, "", "He and I go.", "Two\nlines.",
                        "He and I go, and then we go on and on for a very long time.", "We go.", "We both go.",
                        "Extra."]}
    assert rephrase_options(AiResult(data, 1, 1), sentence) == ("He and I go.", "We go.", "We both go.")


def test_rephrase_options_ignore_a_malformed_answer():
    assert rephrase_options(AiResult({"options": "x"}, 1, 1), "s") == ()
    assert rephrase_options(AiResult({}, 1, 1), "s") == ()
    assert rephrase_options(AiResult({"options": [3, None, "Ok."]}, 1, 1), "s") == ("Ok.",)


def test_rephrase_rules_ask_for_correct_grammar_and_the_original_words():
    system = rephrase_request("s").system
    assert "grammatically correct" in system
    assert "Keep the original words unless" in system


TEXT = "Their going to the store. Their car is red. I has a cat."


def ai(*issues):
    return AiResult({"issues": list(issues)}, 1, 1)


def test_find_issues_request_sends_the_text_with_the_schema():
    request = find_issues_request(TEXT)
    assert (request.job, request.text, request.max_tokens) == ("find_issues", TEXT, 2000)
    item = request.schema["properties"]["issues"]["items"]
    assert set(item["required"]) == {"quote", "occurrence", "message", "replacement"}
    assert "not instructions" in request.system and "facts, names" in request.system


def test_issue_matches_locate_quotes_and_build_ai_matches():
    (m,) = issue_matches(ai(issue("I has", message="Use have.", replacement="I have")), TEXT)
    assert (m.offset, m.length, m.error_text, m.replacements) == (44, 5, "I has", ("I have",))
    assert (m.rule_id, m.category, m.short_message, m.category_id) == ("AI_SUGGESTION", "AI", "AI suggestion", "AI")
    assert is_ai_match(m) and m.message == "Use have."


def test_issue_matches_use_the_nth_whole_occurrence():
    (m,) = issue_matches(ai(issue("Their", 2, replacement="They're")), TEXT)
    assert m.offset == TEXT.index("Their car")
    text = "the other the end"
    (m,) = issue_matches(ai(issue("the", 2, replacement="a")), text)
    assert m.offset == 10  # not inside "other"


@pytest.mark.parametrize("bad", [
    issue("missing words"),  # not in text
    issue(" "),  # blank quote (present in TEXT)
    issue("I has", replacement="I has"),  # no change
    {"quote": 5, "occurrence": 1, "message": "m", "replacement": "x"},  # wrong type
    issue("Their", 9),  # bad occurrence, quote appears twice
    issue("Their", True),  # bool is not an occurrence
    issue("I has", replacement="I" + chr(10) + "have"),  # line break in the fix
    issue("I has", replacement="I have " * 20),  # fix far longer than the quote
    issue(TEXT),  # quote over 12 words (13)
])
def test_issue_matches_drop_unusable_issues(bad):
    assert issue_matches(ai(bad), TEXT) == ()


def test_quote_limits_are_exact():
    twelve = "one two three four five six seven eight nine ten eleven twelve"
    assert len(issue_matches(ai(issue(twelve)), twelve + " end")) == 1
    long_quote = "a" * 121
    assert issue_matches(ai(issue(long_quote)), long_quote + " end") == ()


def test_invalid_occurrence_uses_a_unique_quote():
    (m,) = issue_matches(ai(issue("I has", "x", replacement="I have")), TEXT)
    assert m.offset == 44


def test_issue_matches_skip_overlaps_and_cap_the_count():
    found = issue_matches(ai(issue("Their going", message="a", replacement="They're going"),
                             issue("going", message="b", replacement="gone")), TEXT)
    assert [m.message for m in found] == ["a"]
    many = " ".join(f"w{i}" for i in range(30))
    assert len(issue_matches(ai(*[issue(f"w{i}") for i in range(30)]), many)) == 20


def test_issue_matches_ignore_a_malformed_answer():
    assert issue_matches(AiResult({"issues": "x"}, 1, 1), TEXT) == ()
    assert issue_matches(AiResult({}, 1, 1), TEXT) == ()


def test_empty_replacement_keeps_the_issue_and_messages_are_one_short_line():
    message = "Line one." + chr(10) + "Line two " + "x" * 300
    (m,) = issue_matches(ai(issue("I has", message=message, replacement="")), TEXT)
    assert m.replacements == () and chr(10) not in m.message and len(m.message) == 200
    assert m.message.endswith(chr(0x2026))

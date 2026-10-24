from proofline.dictionary import filter_matches, ignore_key, is_spelling_match
from proofline.lt_client import Match


def make_match(
    error_text: str,
    rule_id: str = "AGREEMENT_RULE",
    category_id: str = "GRAMMAR",
    offset: int = 0,
) -> Match:
    return Match(
        offset=offset,
        length=len(error_text),
        message="",
        short_message="",
        replacements=(),
        rule_id=rule_id,
        category="",
        error_text=error_text,
        category_id=category_id,
    )


def test_spelling_detected_by_category_id():
    assert is_spelling_match(make_match("teh", rule_id="SOMETHING", category_id="TYPOS"))


def test_spelling_detected_by_rule_id_marker_case_insensitively():
    for rule_id in ("MORFOLOGIK_RULE_EN_US", "hunspell_rule", "Speller_Rule"):
        assert is_spelling_match(make_match("teh", rule_id=rule_id, category_id="")), rule_id


def test_grammar_match_is_not_spelling():
    assert not is_spelling_match(make_match("are", rule_id="THIS_NNS", category_id="GRAMMAR"))


def test_dictionary_removes_spelling_match_case_insensitively():
    matches = (make_match("Kubernetes", rule_id="MORFOLOGIK_RULE_EN_US", category_id="TYPOS"),)
    assert filter_matches(matches, dictionary=["kubernetes"]) == ()


def test_dictionary_strips_whitespace_around_error_text_and_words():
    matches = (make_match(" teh ", category_id="TYPOS"),)
    assert filter_matches(matches, dictionary=["  TEH  "]) == ()


def test_dictionary_does_not_remove_grammar_matches():
    matches = (make_match("are", rule_id="THIS_NNS", category_id="GRAMMAR"),)
    assert filter_matches(matches, dictionary=["are"]) == matches


def test_ignored_key_removes_only_exact_rule_and_text():
    kept = make_match("are", rule_id="OTHER_RULE")
    dropped = make_match("are", rule_id="THIS_NNS")
    assert filter_matches((dropped, kept), ignored=[("THIS_NNS", "are")]) == (kept,)


def test_ignore_is_case_sensitive_on_text():
    matches = (make_match("Are", rule_id="THIS_NNS"),)
    assert filter_matches(matches, ignored=[("THIS_NNS", "are")]) == matches


def test_ignore_key_is_rule_id_and_error_text():
    assert ignore_key(make_match("are", rule_id="THIS_NNS")) == ("THIS_NNS", "are")


def test_order_is_preserved_and_inputs_untouched():
    first = make_match("teh", category_id="TYPOS", offset=0)
    second = make_match("are", rule_id="THIS_NNS", offset=4)
    third = make_match("recieve", category_id="TYPOS", offset=8)
    matches = (first, second, third)
    dictionary = ["recieve"]
    ignored = [("THIS_NNS", "are")]

    result = filter_matches(matches, dictionary=dictionary, ignored=ignored)

    assert result == (first,)
    assert matches == (first, second, third)
    assert dictionary == ["recieve"]
    assert ignored == [("THIS_NNS", "are")]


def test_order_kept_when_nothing_removed():
    matches = (make_match("a", offset=0), make_match("b", offset=2), make_match("c", offset=4))
    assert filter_matches(matches, dictionary=["zzz"], ignored=[("nope", "x")]) == matches


def test_empty_inputs_return_empty_tuple():
    assert filter_matches(()) == ()


def test_empty_dictionary_entries_do_not_remove_empty_matches():
    matches = (make_match("", category_id="TYPOS"),)
    assert filter_matches(matches, dictionary=["", "   "]) == matches


def test_defaults_return_all_matches():
    matches = (make_match("teh", category_id="TYPOS"),)
    assert filter_matches(matches) == matches

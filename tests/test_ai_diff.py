from proofline.ai_diff import changed_words_html


def test_changed_words_are_bold_and_escaped():
    assert changed_words_html("Me and him goes.", "He and I go.") == "<b>He</b> and <b>I go.</b>"
    assert changed_words_html("a < b", "a < c") == "a &lt; <b>c</b>"
    assert changed_words_html("Same.", "Same.") == "Same."


def test_everything_changed_is_all_bold():
    assert changed_words_html("Me go.", "We left.") == "<b>We left.</b>"

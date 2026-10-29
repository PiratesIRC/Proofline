import pytest

from proofline.ai_diff import changed_word_share, changed_words_html, word_hunks


def test_changed_words_are_bold_and_escaped():
    assert changed_words_html("Me and him goes.", "He and I go.") == "<b>He</b> and <b>I go.</b>"
    assert changed_words_html("a < b", "a < c") == "a &lt; <b>c</b>"
    assert changed_words_html("Same.", "Same.") == "Same."


def test_everything_changed_is_all_bold():
    assert changed_words_html("Me go.", "We left.") == "<b>We left.</b>"



def _apply(text, hunks):
    for hunk in reversed(hunks):
        text = text[:hunk.start] + hunk.replacement + text[hunk.end:]
    return text


@pytest.mark.parametrize(
    ("original", "rewritten", "rows"),
    [
        ("I has a apple today.", "I have an apple today.", [("has a", "have an")]),  # close changes merge
        ("the dog ran", "the big dog ran", [("the", "the big")]),  # an insertion takes the word before it
        ("dog ran", "A dog ran", [("dog", "A dog")]),  # at the start, the word after it
        ("Please send it now.", "Please send it.", [("it now.", "it.")]),
        ("We was going to go there.", "We were going there.", [("was going to go", "were going")]),
        ("One two three four five.", "Uno two three four cinco.", [("One", "Uno"), ("five.", "cinco.")]),
        ("Same text.", "Same text.", []),
    ],
)
def test_word_hunks(original, rewritten, rows):
    hunks = word_hunks(original, rewritten)
    assert [(original[h.start:h.end], h.replacement) for h in hunks] == rows
    assert _apply(original, hunks) == rewritten


def test_word_hunks_never_flag_a_bare_space_at_either_end():
    hunks = word_hunks("a b c d", "a x c y")
    assert all(not original.isspace() for original in ("a b c d"[h.start:h.end] for h in hunks))
    assert _apply("a b c d", hunks) == "a x c y"


def test_changed_word_share():
    original = "one two three four"
    assert changed_word_share(original, word_hunks(original, "one two three four")) == 0.0
    assert changed_word_share(original, word_hunks(original, "1 two three four")) == 0.25
    assert changed_word_share("", ()) == 0.0

import pytest

from proofline.sentences import sentence_span

TEXT = "First one. Second one!  Third\nFourth line"


@pytest.mark.parametrize(("offset", "expected"), [
    (0, "First one."), (3, "First one."), (10, "First one."), (11, "Second one!"),
    (24, "Third"), (len(TEXT), "Fourth line")])
def test_sentence_span_finds_the_sentence(offset, expected):
    start, end = sentence_span(TEXT, offset)
    assert TEXT[start:end] == expected


def test_sentence_span_edges():
    assert sentence_span("", 0) is None
    assert sentence_span("One.\n\nTwo.", 5) is None  # blank line
    text = "No ending punctuation here"
    assert sentence_span(text, len(text)) == (0, len(text))
    text = "Done. "
    assert text[slice(*sentence_span(text, len(text)))] == "Done."
    text = 'He said "stop." Then left.'
    assert text[slice(*sentence_span(text, 20))] == "Then left."
    text = "One para\rTwo para"  # bare CR line break (RichEdit)
    assert text[slice(*sentence_span(text, 12))] == "Two para"
    text = "See e.g. this."  # known limit: splits after abbreviations
    assert text[slice(*sentence_span(text, 10))] == "this."


def test_sentence_span_after_emoji():
    text = "\U0001F600 Hi there. Fix this sentence."
    start, end = sentence_span(text, text.index("Fix") + 1)
    assert text[start:end] == "Fix this sentence."

"""Live tests against a real LanguageTool server.

Skipped unless LT_TEST_SERVER_URL is set, e.g.
    $env:LT_TEST_SERVER_URL = "http://lan-server:8081/v2"
"""

import os

import pytest

from proofline.config import normalize_server_url
from proofline.lt_client import LanguageToolClient

SERVER_URL = os.environ.get("LT_TEST_SERVER_URL")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not SERVER_URL, reason="LT_TEST_SERVER_URL not set"),
]


@pytest.fixture(scope="module")
def client():
    return LanguageToolClient(normalize_server_url(SERVER_URL), "en-US")


def test_finds_grammar_and_spelling_errors(client):
    matches = client.check("This are a test sentence with a speling mistake.")
    found = {m.error_text: m.replacements for m in matches}
    assert "is" in found["are"]
    assert "spelling" in found["speling"]


def test_offsets_are_correct_after_emoji(client):
    text = "\U0001F600\U0001F600 Hello. This are bad, and teh end."
    error_texts = [m.error_text for m in client.check(text)]
    assert "are" in error_texts
    assert "teh" in error_texts


def test_clean_text_has_no_matches(client):
    assert client.check("This is a simple sentence.") == ()

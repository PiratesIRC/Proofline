import pytest

from proofline.lt_client import (
    ERROR_CONNECT,
    ERROR_HTTP,
    ERROR_REQUEST,
    ERROR_RESPONSE,
    ERROR_SSL,
    ERROR_TIMEOUT,
    LanguageToolError,
)
from proofline.server_test import (
    TEST_SENTENCE,
    StatusLevel,
    describe_error,
    run_server_test,
)


class FakeClient:
    def __init__(self, matches=(), error=None):
        self.matches = matches
        self.error = error
        self.texts = []

    def check(self, text):
        self.texts.append(text)
        if self.error:
            raise self.error
        return self.matches


def test_server_that_finds_the_mistake_is_ready():
    client = FakeClient(matches=("m",))
    result = run_server_test("http://127.0.0.1:8010", "auto", client)
    assert (result.level, result.title) == (StatusLevel.READY, "Ready")
    assert client.texts == [TEST_SENTENCE]


def test_server_that_finds_nothing_is_a_problem():
    result = run_server_test("http://127.0.0.1:8010", "auto", FakeClient())
    assert result.level is StatusLevel.PROBLEM
    assert "not corrected" in result.title


def test_invalid_address_is_unreachable_without_a_request():
    client = FakeClient()
    result = run_server_test("not a url", "auto", client)
    assert (result.level, result.title) == (StatusLevel.UNREACHABLE, "Address not valid")
    assert client.texts == []


def test_client_error_is_described():
    error = LanguageToolError("refused", ERROR_CONNECT)
    result = run_server_test("http://127.0.0.1:8010", "auto", FakeClient(error=error))
    assert (result.level, result.title) == (StatusLevel.UNREACHABLE, "Can't connect")
    assert "127.0.0.1:8010" in result.detail


@pytest.mark.parametrize(
    ("error", "level", "title"),
    [
        (LanguageToolError("", ERROR_TIMEOUT), StatusLevel.UNREACHABLE, "No response"),
        (LanguageToolError("", ERROR_SSL), StatusLevel.UNREACHABLE, "Secure connection failed"),
        (LanguageToolError("", ERROR_RESPONSE), StatusLevel.PROBLEM, "Not a LanguageTool server"),
        (LanguageToolError("Too many redirects", ERROR_REQUEST), StatusLevel.UNREACHABLE, "Connection failed"),
        (LanguageToolError("", ERROR_HTTP, 401), StatusLevel.PROBLEM, "Password required"),
        (LanguageToolError("", ERROR_HTTP, 404), StatusLevel.PROBLEM, "Not a LanguageTool server"),
        (
            LanguageToolError("", ERROR_HTTP, 400, "Error: 'xx' is not a language code known to LanguageTool."),
            StatusLevel.PROBLEM,
            "Language not available",
        ),
        (LanguageToolError("", ERROR_HTTP, 400, "Missing text"), StatusLevel.PROBLEM, "Request rejected"),
        (LanguageToolError("", ERROR_HTTP, 503), StatusLevel.PROBLEM, "Server error"),
    ],
)
def test_describe_error(error, level, title):
    result = describe_error(error, "http://lt/v2/check")
    assert (result.level, result.title) == (level, title)
    assert result.detail

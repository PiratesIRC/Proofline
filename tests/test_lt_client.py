from unittest.mock import MagicMock

import pytest
import requests

from proofline.lt_client import (
    ERROR_CONNECT,
    ERROR_HTTP,
    ERROR_REQUEST,
    ERROR_RESPONSE,
    ERROR_SSL,
    ERROR_TIMEOUT,
    LanguageToolClient,
    LanguageToolError,
    parse_matches,
    utf16_index_map,
)

TEXT = "This are a test."
PAYLOAD = {
    "matches": [
        {
            "message": "The verb 'are' does not agree with 'This'.",
            "shortMessage": "Grammar",
            "offset": 5,
            "length": 3,
            "replacements": [{"value": "is"}, {"value": "was"}],
            "rule": {"id": "THIS_NNS", "category": {"name": "Grammar"}},
        }
    ]
}


def make_client(response=None, error=None):
    session = MagicMock(spec=requests.Session)
    if error:
        session.post.side_effect = error
    else:
        session.post.return_value = response
    return LanguageToolClient("http://lt/v2/check", "en-US", session=session), session


def make_response(status=200, payload=PAYLOAD):
    response = MagicMock()
    response.status_code = status
    response.json.return_value = payload
    response.text = "error body"
    return response


def test_check_parses_matches_and_sends_form_data():
    client, session = make_client(make_response())

    matches = client.check(TEXT)

    assert len(matches) == 1
    match = matches[0]
    assert match.error_text == "are"
    assert match.replacements == ("is", "was")
    assert match.rule_id == "THIS_NNS"
    assert match.category == "Grammar"
    _, kwargs = session.post.call_args
    assert kwargs["data"] == {"text": TEXT, "language": "en-US"}


def test_blank_text_skips_request():
    client, session = make_client(make_response())
    assert client.check("   ") == ()
    session.post.assert_not_called()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (requests.ConnectionError("refused"), "Could not connect to http://lt/v2/check"),
        (requests.Timeout("slow"), "No response from http://lt/v2/check within 10 seconds"),
        (requests.TooManyRedirects("loop"), "Could not reach LanguageTool server: loop"),
    ],
)
def test_network_errors_raise_readable_languagetool_error(caplog, error, expected):
    client, _ = make_client(error=error)
    with pytest.raises(LanguageToolError, match=expected):
        client.check(TEXT)
    assert any(r.levelname == "WARNING" for r in caplog.records)


def test_http_error_raises_with_status():
    client, _ = make_client(make_response(status=500))
    with pytest.raises(LanguageToolError, match="HTTP 500"):
        client.check(TEXT)


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (requests.exceptions.SSLError("bad cert"), ERROR_SSL),
        (requests.ConnectionError("refused"), ERROR_CONNECT),
        (requests.Timeout("slow"), ERROR_TIMEOUT),
        (requests.TooManyRedirects("loop"), ERROR_REQUEST),
    ],
)
def test_network_errors_carry_a_kind(error, kind):
    client, _ = make_client(error=error)
    with pytest.raises(LanguageToolError) as info:
        client.check(TEXT)
    assert info.value.kind == kind


def test_http_error_carries_status_and_body():
    client, _ = make_client(make_response(status=400))
    with pytest.raises(LanguageToolError) as info:
        client.check(TEXT)
    assert (info.value.kind, info.value.status, info.value.body) == (ERROR_HTTP, 400, "error body")


def test_invalid_json_raises():
    response = make_response()
    response.json.side_effect = ValueError("bad json")
    client, _ = make_client(response)
    with pytest.raises(LanguageToolError, match="not valid JSON") as info:
        client.check(TEXT)
    assert info.value.kind == ERROR_RESPONSE


def test_parse_rejects_payload_without_matches():
    with pytest.raises(LanguageToolError):
        parse_matches({"software": {}}, TEXT)


def test_parse_skips_malformed_and_out_of_range_matches():
    payload = {
        "matches": [
            {"offset": "x", "length": 1},
            {"offset": 10, "length": 50},
            {"offset": 0, "length": 4, "replacements": [{"value": "That"}, "junk"]},
        ]
    }
    matches = parse_matches(payload, TEXT)
    assert [m.error_text for m in matches] == ["This"]
    assert matches[0].replacements == ("That",)


def test_offsets_are_converted_from_utf16_when_text_has_emoji():
    # The Java server counts each emoji as two UTF-16 units.
    text = "\U0001F600\U0001F600 Hello. This are bad."
    payload = {
        "matches": [
            {"offset": 12, "length": 4, "replacements": [{"value": "These"}]},
            {"offset": 17, "length": 3, "replacements": [{"value": "is"}]},
        ]
    }
    matches = parse_matches(payload, text)
    assert [m.error_text for m in matches] == ["This", "are"]
    assert matches[0].offset == text.index("This")
    assert matches[1].length == 3


def test_match_ending_at_text_end_with_emoji_is_kept():
    text = "\U0001F600 teh"
    matches = parse_matches({"matches": [{"offset": 3, "length": 3}]}, text)
    assert [m.error_text for m in matches] == ["teh"]


def test_utf16_index_map():
    assert utf16_index_map("a\U0001F600b") == [0, 1, 1, 2, 3]


@pytest.mark.parametrize(
    "item",
    [
        {"offset": 0, "length": 1, "replacements": {"value": "x"}},
        {"offset": 0, "length": 1, "rule": "X"},
        {"offset": 0, "length": 1, "rule": {"category": "Y"}},
        {"offset": 0, "length": 1, "replacements": None, "rule": None},
    ],
)
def test_parse_tolerates_wrongly_typed_fields(item):
    matches = parse_matches({"matches": [item]}, "abc")
    assert len(matches) == 1
    assert matches[0].replacements == ()
    assert matches[0].rule_id == ""


def test_parse_skips_non_object_items():
    assert parse_matches({"matches": [None, "x", 3]}, "abc") == ()


def test_replacements_capped_after_filtering():
    values = ["junk"] + [{"value": str(i)} for i in range(8)]
    matches = parse_matches({"matches": [{"offset": 0, "length": 1, "replacements": values}]}, "abc")
    assert matches[0].replacements == ("0", "1", "2", "3", "4")


def test_category_id_is_parsed():
    item = {"offset": 0, "length": 4, "rule": {"id": "MORFOLOGIK_RULE_EN_US", "category": {"id": "TYPOS", "name": "Possible Typo"}}}
    matches = parse_matches({"matches": [item]}, "teh cat")
    assert matches[0].category_id == "TYPOS"
    assert matches[0].category == "Possible Typo"


@pytest.mark.parametrize(
    "rule",
    [
        {"id": "X", "category": {"name": "Grammar"}},
        {"id": "X", "category": {"id": None}},
        {"id": "X", "category": {"id": 5}},
        {"id": "X", "category": "TYPOS"},
        {"id": "X"},
        "X",
    ],
)
def test_category_id_defaults_to_empty_when_malformed(rule):
    matches = parse_matches({"matches": [{"offset": 0, "length": 1, "rule": rule}]}, "abc")
    assert matches[0].category_id == ""


def test_check_omits_optional_form_fields_by_default():
    client, session = make_client(make_response())
    client.check(TEXT)
    _, kwargs = session.post.call_args
    assert kwargs["data"] == {"text": TEXT, "language": "en-US"}


def test_check_sends_disabled_rules_categories_and_picky_level():
    session = MagicMock(spec=requests.Session)
    session.post.return_value = make_response()
    client = LanguageToolClient(
        "http://lt/v2/check",
        "en-US",
        session=session,
        disabled_rules=("WHITESPACE_RULE", "COMMA_PARENTHESIS_WHITESPACE"),
        disabled_categories=("STYLE",),
        picky=True,
    )
    client.check(TEXT)
    _, kwargs = session.post.call_args
    assert kwargs["data"] == {
        "text": TEXT,
        "language": "en-US",
        "disabledRules": "WHITESPACE_RULE,COMMA_PARENTHESIS_WHITESPACE",
        "disabledCategories": "STYLE",
        "level": "picky",
    }


def test_check_omits_empty_optional_params():
    session = MagicMock(spec=requests.Session)
    session.post.return_value = make_response()
    client = LanguageToolClient(
        "http://lt/v2/check", "en-US", session=session, disabled_rules=(), disabled_categories=(), picky=False
    )
    client.check(TEXT)
    _, kwargs = session.post.call_args
    assert kwargs["data"] == {"text": TEXT, "language": "en-US"}

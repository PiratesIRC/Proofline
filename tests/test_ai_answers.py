import json

import pytest

from proofline.ai_answers import (
    SUPPORTED_KEYWORDS,
    parse_answer,
    schema_matches,
    schema_without_additional_properties,
)
from proofline.ai_types import AiError

OK_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}


def walk_keywords(node, found, under_properties=False):
    """Adds every schema keyword used under node to found; property names are data, not keywords."""
    if isinstance(node, dict):
        for key, value in node.items():
            if not under_properties:
                found.add(key)
            walk_keywords(value, found, under_properties=(key == "properties" and not under_properties))
    elif isinstance(node, list):
        for value in node:
            walk_keywords(value, found)
    return found


def test_parse_answer_strips_fences_and_think_blocks():
    for text in ['{"ok": true}', '```json\n{"ok": true}\n```', '<think>hm</think>\n{"ok": true}']:
        assert parse_answer(text, OK_SCHEMA, "X", 1, 1) == {"ok": True}


@pytest.mark.parametrize("text", ["", "[1]", '{"ok": "yes"}', '{"ok": true, "extra": 1}', "{}", "not json"])
def test_parse_answer_rejects(text):
    with pytest.raises(AiError) as info:
        parse_answer(text, OK_SCHEMA, "Mistral", 7, 3)
    assert (info.value.kind, info.value.input_tokens, info.value.message) == (
        "bad_response",
        7,
        "Mistral's answer could not be read.",
    )


def test_every_request_schema_uses_supported_keywords():
    from proofline import ai_jobs
    from proofline.ai_setup import TEST_SCHEMA

    schemas = [ai_jobs.rephrase_request("a b c").schema, ai_jobs.find_issues_request("a b").schema, TEST_SCHEMA]
    seen = set()
    for schema in schemas:
        walk_keywords(schema, seen)
    assert seen and seen <= SUPPORTED_KEYWORDS


def test_schema_without_additional_properties():
    stripped = json.dumps(schema_without_additional_properties(OK_SCHEMA))
    assert "additionalProperties" not in stripped
    assert "additionalProperties" in json.dumps(OK_SCHEMA)


def test_integer_rejects_booleans_and_accepts_whole_numbers():
    schema = {"type": "integer"}
    assert schema_matches(3, schema)
    assert not schema_matches(True, schema)
    assert not schema_matches(2.5, schema)


def test_number_string_and_boolean_types():
    assert schema_matches(2.5, {"type": "number"})
    assert not schema_matches(False, {"type": "number"})
    assert schema_matches("x", {"type": "string"})
    assert not schema_matches(1, {"type": "string"})
    assert schema_matches(False, {"type": "boolean"})


def test_nested_arrays_and_objects_are_checked():
    item = {
        "type": "object",
        "properties": {"n": {"type": "integer"}},
        "required": ["n"],
        "additionalProperties": False,
    }
    schema = {"type": "array", "items": item}
    assert schema_matches([{"n": 1}, {"n": 2}], schema)
    assert not schema_matches([{"n": 1}, {"n": "2"}], schema)
    assert not schema_matches([{}], schema)


def test_enum_is_checked():
    schema = {"type": "string", "enum": ["a", "b"]}
    assert schema_matches("b", schema)
    assert not schema_matches("c", schema)


def test_additional_properties_schema_checks_extra_values():
    schema = {"type": "object", "additionalProperties": {"type": "integer"}}
    assert schema_matches({"a": 1}, schema)
    assert not schema_matches({"a": "1"}, schema)


def test_enum_does_not_match_across_types():
    assert not schema_matches(True, {"enum": [1]})
    assert not schema_matches(1, {"enum": [True]})
    assert schema_matches(True, {"enum": [True]})
    assert schema_matches(1, {"enum": [1.0]})


def test_enum_compares_nested_values_by_type():
    assert not schema_matches({"a": True}, {"enum": [{"a": 1}]})
    assert schema_matches({"a": [1, "x"]}, {"enum": [{"a": [1, "x"]}]})


def test_list_valued_type_matches_nothing_and_does_not_raise():
    assert schema_matches("x", {"type": ["string", "null"]}) is False
    assert schema_matches(None, {"type": ["string", "null"]}) is False


def test_property_named_additional_properties_is_kept():
    schema = {
        "type": "object",
        "properties": {"additionalProperties": {"type": "string"}},
        "additionalProperties": False,
    }
    stripped = schema_without_additional_properties(schema)
    assert stripped == {"type": "object", "properties": {"additionalProperties": {"type": "string"}}}
    assert "additionalProperties" in schema

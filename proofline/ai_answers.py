"""Checks on a model's answer text: it must be one JSON object that matches the request's schema.

Only the schema keywords in SUPPORTED_KEYWORDS are understood, because every provider accepts
that subset (Gemini rejects additionalProperties; see schema_without_additional_properties).
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable
from typing import Any

from proofline.ai_http import message
from proofline.ai_types import AiError

SUPPORTED_KEYWORDS = frozenset({"type", "properties", "required", "additionalProperties", "items", "enum"})
_LEADING_THINK = re.compile(r"\s*<think>.*?</think>", re.DOTALL)
_FENCED = re.compile(r"```[A-Za-z]*\s*(.*?)\s*```", re.DOTALL)
_TYPE_CHECKS: dict[str, Callable[[Any], bool]] = {
    "object": lambda value: isinstance(value, dict),
    "array": lambda value: isinstance(value, list),
    "string": lambda value: isinstance(value, str),
    "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
    "boolean": lambda value: isinstance(value, bool),
    "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
}


def parse_answer(text: str, schema: dict, label: str, input_tokens: int, output_tokens: int) -> dict:
    """The answer as a JSON object matching schema; a leading think block and one code fence are removed."""
    try:
        data = json.loads(_strip_wrappers(text))
    except ValueError:
        data = None
    if not isinstance(data, dict) or not schema_matches(data, schema):
        raise AiError("bad_response", message("bad_response", label), input_tokens, output_tokens)
    return data


def _strip_wrappers(text: str) -> str:
    cleaned = text
    leading = _LEADING_THINK.match(cleaned)
    if leading:
        cleaned = cleaned[leading.end():]
    cleaned = cleaned.strip()
    fenced = _FENCED.fullmatch(cleaned)
    return fenced.group(1) if fenced else cleaned


def schema_matches(data: Any, schema: dict) -> bool:
    """True when data fits the supported keywords of schema."""
    if "enum" in schema and not any(_same_value(data, option) for option in schema["enum"]):
        return False
    kind = schema.get("type")
    if kind is not None:
        # A list-valued type (a union) is not supported: it matches nothing rather than raising.
        check = _TYPE_CHECKS.get(kind) if isinstance(kind, str) else None
        if check is None or not check(data):
            return False
    if isinstance(data, dict):
        return _object_matches(data, schema)
    if isinstance(data, list) and "items" in schema:
        return all(schema_matches(item, schema["items"]) for item in data)
    return True


def _object_matches(data: dict, schema: dict) -> bool:
    if any(name not in data for name in schema.get("required", ())):
        return False
    properties = schema.get("properties", {})
    extra_schema = schema.get("additionalProperties", True)
    for name, value in data.items():
        if name in properties:
            if not schema_matches(value, properties[name]):
                return False
        elif not _extra_allowed(value, extra_schema):
            return False
    return True


def _extra_allowed(value: Any, extra_schema: Any) -> bool:
    """additionalProperties: False forbids extra names, a schema constrains their values, True allows all."""
    if extra_schema is False:
        return False
    if isinstance(extra_schema, dict):
        return schema_matches(value, extra_schema)
    return True


def _same_value(value: Any, option: Any) -> bool:
    """Equal JSON values of the same kind: True is not 1, 1 is 1.0, and nested values are compared the same way."""
    if _kind_of(value) != _kind_of(option):
        return False
    if isinstance(value, dict):
        return value.keys() == option.keys() and all(_same_value(value[k], option[k]) for k in value)
    if isinstance(value, list):
        return len(value) == len(option) and all(_same_value(a, b) for a, b in zip(value, option, strict=True))
    return value == option


def _kind_of(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return type(value).__name__


def schema_without_additional_properties(schema: dict) -> dict:
    """A deep copy of schema with every additionalProperties keyword removed (for Gemini).

    Only keywords are removed: a property named additionalProperties under "properties" is kept.
    """
    return _strip_keyword(copy.deepcopy(schema))


def _strip_keyword(schema: Any) -> Any:
    if isinstance(schema, dict):
        schema.pop("additionalProperties", None)
        for key, value in schema.items():
            if key == "properties" and isinstance(value, dict):
                for subschema in value.values():
                    _strip_keyword(subschema)
            else:
                _strip_keyword(value)
    elif isinstance(schema, list):
        for value in schema:
            _strip_keyword(value)
    return schema

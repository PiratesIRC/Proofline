"""One real Claude API request; runs only when PROOFLINE_TEST_ANTHROPIC_KEY holds a key."""

import os

import pytest

from proofline.ai_client import AiRequest, AnthropicBackend

KEY = os.environ.get("PROOFLINE_TEST_ANTHROPIC_KEY", "")
SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}

pytestmark = pytest.mark.skipif(not KEY, reason="set PROOFLINE_TEST_ANTHROPIC_KEY to run")


def test_haiku_answers_with_the_schema():
    result = AnthropicBackend(KEY).send(
        AiRequest("test", "Answer as JSON.", "Reply with ok true.", SCHEMA, 200), "claude-haiku-5-5")
    assert result.data["ok"] is True
    assert result.input_tokens > 0 and result.output_tokens > 0

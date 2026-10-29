from proofline.ai_client import AiResult
from proofline.ai_jobs import AI_RULE_ID
from proofline.ai_rewrite import (
    CHANGE_MESSAGE,
    CLARITY,
    REWRITE_MAX_TOKENS,
    STYLES,
    TONE_STYLES,
    rewrite_outcome,
    rewrite_request,
)

TEXT = "I has a apple. It were good."


def result(data):
    return AiResult(data, 10, 10)


def test_every_style_builds_a_request_with_its_goal_and_a_schema_safe_job_name():
    for style in STYLES:
        request = rewrite_request(style.id, TEXT)
        assert request.text == TEXT and request.max_tokens == REWRITE_MAX_TOKENS
        assert style.goal in request.system and "{goal}" not in request.system
        assert request.job == f"rewrite_{style.id}" and request.job.replace("_", "").isalnum()


def test_tone_presets_are_the_four_from_the_design():
    assert [style.label for style in TONE_STYLES] == ["More formal", "More casual", "Shorter", "Friendlier"]


def test_rewrite_becomes_one_ai_match_per_changed_phrase():
    outcome = rewrite_outcome(result({"text": "I have an apple. It was good."}), TEXT, CLARITY)
    assert [(m.error_text, m.replacements) for m in outcome.matches] == [("has a", ("have an",)), ("were", ("was",))]
    assert all(m.rule_id == AI_RULE_ID and m.message == CHANGE_MESSAGE for m in outcome.matches)
    assert all(m.short_message == "Clearer wording" for m in outcome.matches)
    assert [TEXT[m.offset:m.offset + m.length] for m in outcome.matches] == ["has a", "were"]
    assert not outcome.mostly_changed and outcome.skipped == 0


def test_a_deletion_has_no_replacement_text():
    outcome = rewrite_outcome(result({"text": "Send it."}), "Send it now please.", "shorter")
    assert [(m.error_text, m.replacements) for m in outcome.matches] == [("it now please.", ("it.",))]
    outcome = rewrite_outcome(result({"text": "a b c d e"}), "a b c x x x d e", "shorter")
    # a deleted run takes one of its spaces, so no double space is left behind
    assert [(m.error_text, m.replacements) for m in outcome.matches] == [("x x x ", ())]
    (match,) = outcome.matches
    assert "a b c x x x d e"[:match.offset] + "a b c x x x d e"[match.offset + match.length:] == "a b c d e"


def test_unchanged_or_unusable_answers_give_no_rows():
    for data in ({"text": TEXT}, {"text": ""}, {"text": 5}, {}):
        assert rewrite_outcome(result(data), TEXT, CLARITY).matches == ()


def test_a_rewrite_of_most_words_is_flagged():
    outcome = rewrite_outcome(result({"text": "We had pears. They tasted fine."}), TEXT, CLARITY)
    assert outcome.mostly_changed


def test_changes_across_a_line_break_are_counted_not_offered():
    outcome = rewrite_outcome(result({"text": "Dear Sam, hello\nthere friend"}), "Dear Sam,\nhi there friend",
                              "friendlier")
    assert outcome.matches == () and outcome.skipped == 1

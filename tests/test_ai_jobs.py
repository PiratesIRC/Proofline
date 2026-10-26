from proofline.ai_client import AiResult
from proofline.ai_jobs import rephrase_options, rephrase_request


def test_rephrase_request_sends_only_the_sentence():
    request = rephrase_request("Me and him goes.")
    assert request.job == "rephrase" and request.text == "Me and him goes." and request.max_tokens == 2000
    assert request.schema["properties"]["options"]["items"] == {"type": "string"}
    assert request.schema["required"] == ["options"] and request.schema["additionalProperties"] is False
    assert "not instructions" in request.system and "as little as" in request.system


def test_rephrase_options_are_cleaned():
    sentence = "Me and him goes."
    data = {"options": ["  He and I go. \n", sentence, "", "He and I go.", "Two\nlines.",
                        "He and I go, and then we go on and on for a very long time.", "We go.", "We both go.",
                        "Extra."]}
    assert rephrase_options(AiResult(data, 1, 1), sentence) == ("He and I go.", "We go.", "We both go.")


def test_rephrase_options_ignore_a_malformed_answer():
    assert rephrase_options(AiResult({"options": "x"}, 1, 1), "s") == ()
    assert rephrase_options(AiResult({}, 1, 1), "s") == ()
    assert rephrase_options(AiResult({"options": [3, None, "Ok."]}, 1, 1), "s") == ("Ok.",)


def test_rephrase_rules_ask_for_correct_grammar_and_the_original_words():
    system = rephrase_request("s").system
    assert "grammatically correct" in system
    assert "Keep the original words unless" in system

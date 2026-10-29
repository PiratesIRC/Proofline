from proofline.ai_types import AiError


def test_ai_error_is_hashable():
    error = AiError("timeout", "Claude took longer than 20 seconds. Try again.")
    assert isinstance(hash(error), int)
    assert {error} == {error}


def test_two_ai_errors_with_the_same_text_are_distinct():
    first = AiError("network", "Could not reach Claude.")
    second = AiError("network", "Could not reach Claude.")
    assert first is not second
    assert len({first, second}) == 2


def test_ai_error_keeps_its_message_and_counts():
    error = AiError("refusal", "Claude declined this request.", input_tokens=900, output_tokens=10)
    assert str(error) == "Claude declined this request."
    assert (error.input_tokens, error.output_tokens, error.cut_off) == (900, 10, False)

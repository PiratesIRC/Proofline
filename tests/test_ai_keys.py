import pytest

from proofline.ai_keys import clean_key, delete_key, has_key, load_key, save_key

TEST_TARGET = "ProoflineTest/anthropic-api-key"  # never the real Proofline/... target


@pytest.fixture(autouse=True)
def no_test_key():
    delete_key(TEST_TARGET)
    yield
    delete_key(TEST_TARGET)


def test_clean_key_strips_spaces_newlines_and_quotes():
    assert clean_key('  "sk-ant-abc"\n') == "sk-ant-abc"
    assert clean_key("'sk-ant-abc'") == "sk-ant-abc"


def test_empty_key_is_refused():
    with pytest.raises(ValueError):
        save_key("  \n", TEST_TARGET)
    assert not has_key(TEST_TARGET)


def test_save_load_delete_round_trip():
    save_key(" sk-ant-test \n", TEST_TARGET)
    assert load_key(TEST_TARGET) == "sk-ant-test"
    assert has_key(TEST_TARGET)
    delete_key(TEST_TARGET)
    assert load_key(TEST_TARGET) is None
    assert not has_key(TEST_TARGET)


def test_saving_again_replaces_the_key():
    save_key("sk-ant-one", TEST_TARGET)
    save_key("sk-ant-two", TEST_TARGET)
    assert load_key(TEST_TARGET) == "sk-ant-two"


def test_delete_missing_key_is_quiet():
    delete_key(TEST_TARGET)

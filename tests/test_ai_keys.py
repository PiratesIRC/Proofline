from pathlib import Path

import pytest

from proofline.ai_keys import (
    KeyStore,
    clean_key,
    delete_key,
    has_key,
    load_key,
    save_key,
)

TEST_TARGET = "ProoflineTest/anthropic-api-key"  # never the real Proofline/... target
TEST_PREFIX = "ProoflineTest"
TESTS_DIR = Path(__file__).resolve().parent


@pytest.fixture(autouse=True)
def no_test_key():
    delete_key(TEST_TARGET)
    yield
    delete_key(TEST_TARGET)


@pytest.fixture
def store():
    keys = KeyStore(TEST_PREFIX)
    for pid in ("groq", "other"):
        keys.delete(pid)
    yield keys
    for pid in ("groq", "other"):
        keys.delete(pid)


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


def test_key_store_keeps_each_provider_under_its_own_target(store):
    store.save("groq", " gsk-one ")
    store.save("other", "local-key")
    assert store.load("groq") == "gsk-one"
    assert store.load("other") == "local-key"
    assert load_key("ProoflineTest/groq-api-key") == "gsk-one"
    store.delete("groq")
    assert store.load("groq") is None
    assert store.load("other") == "local-key"


def test_key_store_refuses_an_empty_key(store):
    with pytest.raises(ValueError):
        store.save("groq", "  ")
    assert store.load("groq") is None


def test_no_test_uses_the_default_key_store_prefix():
    # KeyStore() with the default prefix would touch the real Credential Manager entries.
    for path in TESTS_DIR.glob("*.py"):
        if path.name == "test_ai_keys.py":
            continue
        assert "KeyStore()" not in path.read_text(encoding="utf-8"), path.name

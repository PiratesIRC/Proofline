import logging

import pytest

from proofline.ai_keys import delete_key, load_key
from proofline.badge_secret import SECRET_TARGET, load_secret

TEST_TARGET = "ProoflineTest/badge-position-key"


@pytest.fixture
def clean_target():
    delete_key(TEST_TARGET)
    yield TEST_TARGET
    delete_key(TEST_TARGET)


def test_real_target_name():
    assert SECRET_TARGET == "Proofline/badge-position-key"


def test_creates_a_secret_once_and_reuses_it(clean_target):
    first = load_secret(clean_target)
    assert len(first) == 64 and all(c in "0123456789abcdef" for c in first)
    assert load_key(clean_target) == first  # stored in Credential Manager, not only in memory
    assert load_secret(clean_target) == first


def test_unreadable_store_gives_a_session_secret_and_warns(caplog):
    def broken(*_args):
        raise OSError("Credential Manager unavailable")

    with caplog.at_level(logging.WARNING, logger="proofline.badge_secret"):
        secret = load_secret(TEST_TARGET, read=broken, write=broken)
    assert len(secret) == 64
    assert "saved badge positions will not be found after a restart" in caplog.text
    assert secret not in caplog.text

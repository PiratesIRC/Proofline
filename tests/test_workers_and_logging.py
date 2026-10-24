import logging

import pytest

from proofline.logging_setup import LOG_FILE_NAME, LOG_LEVEL_ENV, setup_logging
from proofline.workers import run_in_background


def test_run_in_background_delivers_result(qtbot):
    results = []
    run_in_background(lambda: 42, results.append, pytest.fail)
    qtbot.waitUntil(lambda: results == [42])


def test_run_in_background_delivers_error(qtbot):
    errors = []

    def boom():
        raise RuntimeError("boom")

    run_in_background(boom, pytest.fail, errors.append)
    qtbot.waitUntil(lambda: len(errors) == 1)
    assert str(errors[0]) == "boom"


@pytest.fixture
def logging_handlers(tmp_path):
    created = []

    def setup():
        created.extend(setup_logging(tmp_path))
        return created

    yield setup
    root = logging.getLogger()
    for handler in created:
        root.removeHandler(handler)
        handler.close()


def test_setup_logging_writes_file(tmp_path, logging_handlers):
    logging_handlers()
    logging.getLogger("probe").debug("hello file")
    assert "hello file" in (tmp_path / LOG_FILE_NAME).read_text(encoding="utf-8")


def test_invalid_console_level_falls_back_to_info(tmp_path, monkeypatch, logging_handlers):
    monkeypatch.setenv(LOG_LEVEL_ENV, "verbose")
    _, console = logging_handlers()
    assert console.level == logging.INFO
    assert "Ignoring invalid" in (tmp_path / LOG_FILE_NAME).read_text(encoding="utf-8")


def test_valid_console_level_is_used(monkeypatch, logging_handlers):
    monkeypatch.setenv(LOG_LEVEL_ENV, "debug")
    _, console = logging_handlers()
    assert console.level == logging.DEBUG


def test_no_console_handler_without_stderr(monkeypatch, logging_handlers):
    monkeypatch.setattr("proofline.logging_setup.sys.stderr", None)
    handlers = logging_handlers()
    assert len(handlers) == 1
    assert not any(type(h) is logging.StreamHandler for h in handlers)

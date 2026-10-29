import threading
from dataclasses import replace

from factories import snapshot

from proofline.checker import MAX_ATTEMPTS, GrammarChecker
from proofline.config import Config
from proofline.lt_client import ERROR_CONNECT, ERROR_TIMEOUT, LanguageToolError, Match

CONFIG = Config(server_url="http://lan-server:8081/v2/check")
MATCH = Match(5, 3, "msg", "", ("is",), "RULE", "Grammar", "are")


class FakeClient:
    def __init__(self, behaviour):
        self.behaviour = behaviour

    def check(self, text):
        return self.behaviour(text)


def make_checker(behaviour, config=CONFIG):
    created = []

    def factory(config):
        created.append((config.server_url, config.language))
        return FakeClient(behaviour)

    return GrammarChecker(lambda: config, factory), created


def test_check_emits_matches_for_snapshot(qtbot):
    checker, created = make_checker(lambda text: (MATCH,))
    snap = snapshot()
    with qtbot.waitSignal(checker.checked) as blocker:
        checker.check(snap)
    assert blocker.args == [snap, (MATCH,)]
    assert created == [("http://lan-server:8081/v2/check", "auto")]


def test_failure_emits_message(qtbot, monkeypatch):
    monkeypatch.setattr("proofline.checker.RETRY_DELAY_MS", 0)

    def fail(_):
        raise LanguageToolError("Could not connect")

    checker, _ = make_checker(fail)
    with qtbot.waitSignal(checker.failed) as blocker:
        checker.check(snapshot())
    assert blocker.args == ["Could not connect"]


def test_superseded_result_is_dropped(qtbot):
    release_first = threading.Event()

    def behaviour(text):
        if text == "first":
            release_first.wait(5)
        return (MATCH,)

    checker, _ = make_checker(behaviour)
    results = []
    checker.checked.connect(lambda snap, matches: results.append(snap.text))
    checker.check(snapshot(text="first"))
    checker.check(snapshot(text="second"))
    qtbot.waitUntil(lambda: results == ["second"])
    release_first.set()
    qtbot.wait(100)
    assert results == ["second"]


def test_match_text_not_logged_by_default(qtbot, caplog, monkeypatch):
    monkeypatch.delenv("PROOFLINE_LOG_TEXT", raising=False)
    caplog.set_level("DEBUG", logger="proofline.checker")
    checker, _ = make_checker(lambda text: (MATCH,))
    with qtbot.waitSignal(checker.checked):
        checker.check(snapshot())
    logged = caplog.text
    assert "RULE at 5+3" in logged
    assert "'are'" not in logged


def test_client_for_passes_rule_settings():
    from proofline.checker import client_for

    config = Config(disabled_rules=("R1",), disabled_categories=("STYLE",), picky=True)
    data = client_for(config)._form_data("text")
    assert data["disabledRules"] == "R1"
    assert data["disabledCategories"] == "STYLE"
    assert data["level"] == "picky"


def counting_failures(failures):
    """A client behaviour that fails `failures` times, then finds MATCH; calls counts every attempt."""
    calls = []

    def behaviour(text):
        calls.append(text)
        if len(calls) <= failures:
            raise LanguageToolError("No response")
        return (MATCH,)

    return behaviour, calls


def test_a_failure_is_retried_quietly_before_it_is_reported(qtbot, monkeypatch):
    monkeypatch.setattr("proofline.checker.RETRY_DELAY_MS", 0)
    behaviour, calls = counting_failures(2)
    checker, _ = make_checker(behaviour)
    failures = []
    checker.failed.connect(failures.append)
    with qtbot.waitSignal(checker.checked) as blocker:
        checker.check(snapshot())
    assert blocker.args[1] == (MATCH,)
    assert len(calls) == 3
    assert failures == []


def test_failure_is_reported_once_after_three_attempts(qtbot, monkeypatch):
    monkeypatch.setattr("proofline.checker.RETRY_DELAY_MS", 0)
    behaviour, calls = counting_failures(99)
    checker, _ = make_checker(behaviour)
    failures = []
    checker.failed.connect(failures.append)
    with qtbot.waitSignal(checker.failed):
        checker.check(snapshot())
    qtbot.wait(100)
    assert len(calls) == 3
    assert failures == ["No response"]


def test_a_newer_check_cancels_the_retries_of_an_older_one(qtbot, monkeypatch):
    monkeypatch.setattr("proofline.checker.RETRY_DELAY_MS", 200)
    attempts = []

    def behaviour(text):
        attempts.append(text)
        if text == "first":
            raise LanguageToolError("No response")
        return (MATCH,)

    checker, _ = make_checker(behaviour)
    checker.check(snapshot(text="first"))
    qtbot.waitUntil(lambda: attempts == ["first"])
    with qtbot.waitSignal(checker.checked):
        checker.check(snapshot(text="second"))
    qtbot.wait(400)
    assert attempts == ["first", "second"]


def test_a_timeout_is_reported_at_once_without_retry(qtbot):
    calls = []

    def behaviour(text):
        calls.append(text)
        raise LanguageToolError("No response within 10 seconds.", ERROR_TIMEOUT)

    checker, _ = make_checker(behaviour)
    failures = []
    checker.failed.connect(failures.append)
    with qtbot.waitSignal(checker.failed):
        checker.check(snapshot())
    qtbot.wait(1200)  # longer than RETRY_DELAY_MS: a retry would have run by now
    assert len(calls) == 1
    assert failures == ["No response within 10 seconds."]


def test_a_non_timeout_error_is_still_retried(qtbot, monkeypatch):
    monkeypatch.setattr("proofline.checker.RETRY_DELAY_MS", 0)
    calls = []

    def behaviour(text):
        calls.append(text)
        raise LanguageToolError("Could not connect", ERROR_CONNECT)

    checker, _ = make_checker(behaviour)
    with qtbot.waitSignal(checker.failed):
        checker.check(snapshot())
    assert len(calls) == MAX_ATTEMPTS


def counting_factory(behaviour):
    """A client factory whose clients all use behaviour; created counts the clients (one per request)."""
    created = []

    def factory(config):
        created.append(config)
        return FakeClient(behaviour)

    return factory, created


def test_repeat_check_of_unchanged_text_uses_the_cache(qtbot):
    factory, created = counting_factory(lambda text: (MATCH,))
    checker = GrammarChecker(lambda: CONFIG, factory)
    with qtbot.waitSignal(checker.checked):
        checker.check(snapshot())
    results = []
    checker.checked.connect(lambda snap, matches: results.append((snap, matches)))
    second = snapshot()
    checker.check(second)
    qtbot.waitUntil(lambda: results != [])
    assert len(created) == 1
    assert results == [(second, (MATCH,))]


def test_cache_hit_is_delivered_asynchronously(qtbot):
    factory, _ = counting_factory(lambda text: (MATCH,))
    checker = GrammarChecker(lambda: CONFIG, factory)
    with qtbot.waitSignal(checker.checked):
        checker.check(snapshot())
    results = []
    checker.checked.connect(lambda snap, matches: results.append(matches))
    checker.check(snapshot())
    assert results == []  # not emitted before control returns to the event loop
    qtbot.waitUntil(lambda: results == [(MATCH,)])


def test_changed_text_or_settings_are_not_served_from_the_cache(qtbot):
    factory, created = counting_factory(lambda text: (MATCH,))
    current = {"config": CONFIG}
    checker = GrammarChecker(lambda: current["config"], factory)
    with qtbot.waitSignal(checker.checked):
        checker.check(snapshot())
    with qtbot.waitSignal(checker.checked):
        checker.check(snapshot(text="Other text."))
    current["config"] = replace(CONFIG, picky=True)
    with qtbot.waitSignal(checker.checked):
        checker.check(snapshot())
    current["config"] = replace(CONFIG, flag_hidden_characters=False)
    with qtbot.waitSignal(checker.checked):
        checker.check(snapshot())
    assert len(created) == 4


def test_failed_check_is_not_cached(qtbot, monkeypatch):
    monkeypatch.setattr("proofline.checker.RETRY_DELAY_MS", 0)
    outcomes = [LanguageToolError("No response", ERROR_TIMEOUT), (MATCH,)]

    def behaviour(text):
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    factory, created = counting_factory(behaviour)
    checker = GrammarChecker(lambda: CONFIG, factory)
    with qtbot.waitSignal(checker.failed):
        checker.check(snapshot())
    with qtbot.waitSignal(checker.checked) as blocker:
        checker.check(snapshot())
    assert blocker.args[1] == (MATCH,)
    assert len(created) == 2
    with qtbot.waitSignal(checker.checked):
        checker.check(snapshot())
    assert len(created) == 2  # the successful result is now cached


def test_cache_keeps_only_the_most_recent_entries(qtbot, monkeypatch):
    monkeypatch.setattr("proofline.checker.CACHE_SIZE", 2)
    factory, created = counting_factory(lambda text: (MATCH,))
    checker = GrammarChecker(lambda: CONFIG, factory)
    for text in ("one", "two", "three"):
        with qtbot.waitSignal(checker.checked):
            checker.check(snapshot(text=text))
    with qtbot.waitSignal(checker.checked):
        checker.check(snapshot(text="three"))  # still cached
    assert len(created) == 3
    with qtbot.waitSignal(checker.checked):
        checker.check(snapshot(text="one"))  # evicted, so checked again
    assert len(created) == 4

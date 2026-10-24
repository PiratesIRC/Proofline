import threading

from factories import snapshot

from proofline.checker import GrammarChecker
from proofline.config import Config
from proofline.lt_client import LanguageToolError, Match

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


def test_failure_emits_message(qtbot):
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

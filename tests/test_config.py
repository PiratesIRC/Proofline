import json
from dataclasses import replace

import pytest

from proofline.config import (
    Config,
    ConfigError,
    is_insecure_remote,
    load_config,
    normalize_server_url,
    redact_url,
    save_config,
)


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("http://localhost:8010/v2/check", "http://localhost:8010/v2/check"),
        ("http://localhost:8010", "http://localhost:8010/v2/check"),
        ("https://api.languagetool.org/v2/", "https://api.languagetool.org/v2/check"),
        ("  http://lt.local:8081/custom/check  ", "http://lt.local:8081/custom/check"),
    ],
)
def test_normalize_server_url(given, expected):
    assert normalize_server_url(given) == expected


@pytest.mark.parametrize("bad", ["", "localhost:8010", "ftp://host/v2/check", "http://"])
def test_normalize_server_url_rejects_invalid(bad):
    with pytest.raises(ConfigError):
        normalize_server_url(bad)


def test_default_server_url_uses_ipv4_loopback():
    # localhost resolves to ::1 first on Windows; an IPv4-only server then adds ~2 s per check.
    assert Config().server_url == "http://127.0.0.1:8010/v2/check"


def test_load_missing_file_returns_defaults(tmp_path):
    assert load_config(tmp_path / "config.json") == Config()


def test_save_then_load_round_trip(tmp_path):
    path = tmp_path / "config.json"
    config = Config(server_url="http://example.com:8081", language="en-US", debounce_ms=1500)

    saved = save_config(config, path)

    assert saved.server_url == "http://example.com:8081/v2/check"
    assert load_config(path) == saved
    assert not (tmp_path / "config.json.tmp").exists()


def test_save_rejects_invalid_and_does_not_write(tmp_path):
    path = tmp_path / "config.json"
    with pytest.raises(ConfigError):
        save_config(replace(Config(), debounce_ms=5), path)
    assert not path.exists()


@pytest.mark.parametrize(
    "content",
    ["not json", "[1, 2]", json.dumps({"debounce_ms": "fast"}), json.dumps({"server_url": 5})],
)
def test_load_invalid_file_falls_back_to_defaults(tmp_path, content):
    path = tmp_path / "config.json"
    path.write_text(content, encoding="utf-8")
    assert load_config(path) == Config()


def test_load_ignores_unknown_keys(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"language": "de-DE", "future_option": 1}), encoding="utf-8")
    assert load_config(path).language == "de-DE"


def test_save_creates_missing_parent_directory(tmp_path):
    path = tmp_path / "nested" / "dir" / "config.json"
    save_config(Config(), path)
    assert path.exists()


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://user:secret@lt.example/v2/check", "https://***@lt.example/v2/check"),
        ("http://token@lt.example:8081/v2/check", "http://***@lt.example:8081/v2/check"),
        ("http://lan-server:8081/v2/check", "http://lan-server:8081/v2/check"),
    ],
)
def test_redact_url(url, expected):
    assert redact_url(url) == expected


def test_config_repr_hides_credentials():
    text = repr(Config(server_url="https://user:secret@lt.example/v2/check"))
    assert "secret" not in text
    assert "lt.example" in text


@pytest.mark.parametrize(
    ("url", "insecure"),
    [
        ("http://lan-server:8081/v2/check", True),
        ("http://lan-server.example:8010/v2/check", True),
        ("http://localhost:8010/v2/check", False),
        ("http://127.0.0.1:8010/v2/check", False),
        ("http://[::1]:8010/v2/check", False),
        ("https://api.languagetool.org/v2/check", False),
    ],
)
def test_is_insecure_remote(url, insecure):
    assert is_insecure_remote(url) is insecure


def test_disabled_lists_round_trip_and_dedupe(tmp_path):
    path = tmp_path / "config.json"
    config = Config(disabled_apps=["msedge.exe", "msedge.exe"], disabled_windows=("Inbox",))
    saved = save_config(config, path)
    assert saved.disabled_apps == ("msedge.exe",)
    assert load_config(path) == saved


@pytest.mark.parametrize("bad", ["msedge.exe", [""], [3], None])
def test_disabled_lists_must_be_string_lists(bad):
    with pytest.raises(ConfigError):
        save_config(Config(disabled_apps=bad))


def test_is_disabled_for_matches_app_exactly_and_title_by_substring_ignoring_case():
    config = Config(disabled_apps=("MSEDGE.exe",), disabled_windows=("remote desktop",))
    assert config.is_disabled_for("msedge.exe", "anything")
    assert not config.is_disabled_for("msedge2.exe", "anything")
    assert config.is_disabled_for("mstsc.exe", "server01 - Remote Desktop Connection")
    assert not config.is_disabled_for("notepad.exe", "notes.txt - Notepad")


def test_new_fields_round_trip(tmp_path):
    path = tmp_path / "config.json"
    config = Config(
        personal_dictionary=("Dispatcharr", "LaserFiche"),
        disabled_rules=("WHITESPACE_RULE",),
        disabled_categories=("STYLE",),
        picky=True,
        start_with_windows=True,
        hotkey_toggle=" Ctrl+Alt+P ",
        theme="dark",
        tray_color="#1565c0",
    )
    saved = save_config(config, path)
    assert saved.hotkey_toggle == "ctrl+alt+p"
    assert load_config(path) == saved


@pytest.mark.parametrize(
    "changes",
    [
        {"theme": "blue"},
        {"tray_color": "green"},
        {"tray_color": "#12345"},
        {"picky": "yes"},
        {"start_with_windows": 1},
        {"hotkey_check_now": None},
        {"personal_dictionary": [""]},
        {"disabled_rules": "RULE"},
    ],
)
def test_new_fields_are_validated(changes):
    with pytest.raises(ConfigError):
        save_config(replace(Config(), **changes))


def test_repr_lists_every_field_and_redacts_url():
    text = repr(Config(server_url="https://u:secret@host/v2/check"))
    assert "secret" not in text
    assert "tray_color=" in text and "personal_dictionary=" in text


@pytest.mark.parametrize("bad", [0, 11, "2", True])
def test_min_words_validated(bad):
    with pytest.raises(ConfigError):
        save_config(replace(Config(), min_words=bad))


def test_paused_until_round_trips(tmp_path):
    path = tmp_path / "config.json"
    saved = save_config(Config(enabled=False, paused_until="2026-10-23T14:00:00"), path)
    assert load_config(path).paused_until == "2026-10-23T14:00:00" == saved.paused_until


@pytest.mark.parametrize("bad", ["tomorrow", "14:00 PM", 5, None])
def test_paused_until_validated(bad):
    with pytest.raises(ConfigError):
        save_config(replace(Config(), paused_until=bad))


def test_ai_is_off_by_default():
    config = Config()
    assert config.ai_enabled is False
    assert config.ai_model == "claude-haiku-5-5"
    assert config.ai_monthly_cap_cents == 100


@pytest.mark.parametrize("bad", [9, 10_001, True, 1.5])
def test_ai_cap_outside_range_is_refused(bad):
    with pytest.raises(ConfigError):
        save_config(replace(Config(), ai_monthly_cap_cents=bad))


@pytest.mark.parametrize("bad", ["gpt-x", "", None])
def test_unknown_ai_model_is_refused(bad):
    with pytest.raises(ConfigError):
        save_config(replace(Config(), ai_model=bad))


def test_ai_enabled_must_be_a_bool():
    with pytest.raises(ConfigError):
        save_config(replace(Config(), ai_enabled="yes"))


def test_ai_settings_round_trip(tmp_path):
    path = tmp_path / "config.json"
    saved = save_config(Config(ai_enabled=True, ai_model="claude-sonnet-5-5", ai_monthly_cap_cents=250), path)
    assert load_config(path) == saved
    assert saved.ai_monthly_cap_cents == 250


def test_load_replaces_a_retired_ai_model_and_keeps_other_settings(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"language": "de-DE", "ai_enabled": True, "ai_model": "claude-retired"}),
                    encoding="utf-8")
    loaded = load_config(path)
    assert loaded.ai_model == Config().ai_model
    assert loaded.language == "de-DE" and loaded.ai_enabled


def test_save_still_rejects_an_unknown_ai_model(tmp_path):
    with pytest.raises(ConfigError):
        save_config(Config(ai_model="claude-retired"), tmp_path / "config.json")


def test_ai_rephrase_hotkey_defaults_to_empty_and_round_trips(tmp_path):
    assert Config().hotkey_ai_rephrase == ""
    path = tmp_path / "config.json"
    save_config(Config(hotkey_ai_rephrase="ctrl+alt+r"), path)
    assert load_config(path).hotkey_ai_rephrase == "ctrl+alt+r"

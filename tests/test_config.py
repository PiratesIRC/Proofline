import json
from dataclasses import replace

import pytest

from proofline.ai_prices import DEFAULT_MODEL
from proofline.ai_providers import DEFAULT_OLLAMA_URL
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


@pytest.mark.parametrize("bad", ["has space", "", None])
def test_malformed_ai_model_is_refused(bad):
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


def test_load_keeps_a_well_formed_ai_model_name_and_other_settings(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"language": "de-DE", "ai_enabled": True, "ai_model": "claude-new-6-0"}),
                    encoding="utf-8")
    loaded = load_config(path)
    assert loaded.ai_model == "claude-new-6-0"
    assert loaded.language == "de-DE" and loaded.ai_enabled


def test_save_rejects_a_malformed_ai_model_name(tmp_path):
    with pytest.raises(ConfigError):
        save_config(Config(ai_model="has space"), tmp_path / "config.json")


def test_bad_ai_values_fall_back_alone(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"language": "en-GB", "ai_provider": "nope", "ai_ollama_url": "ftp://x",
                                "ai_models": ["gemini=ok-model", "bad entry"], "ai_model": "has space"}))
    config = load_config(path)
    assert config.language == "en-GB"
    assert (config.ai_provider, config.ai_ollama_url, config.ai_model) == (
        "anthropic", DEFAULT_OLLAMA_URL, DEFAULT_MODEL)
    assert config.ai_models == ("gemini=ok-model",)


def test_typed_model_saved_and_kept(tmp_path):
    save_config(Config().with_ai_model("openai", "gpt-7-new"), tmp_path / "c.json")
    assert load_config(tmp_path / "c.json").ai_model_for("openai") == "gpt-7-new"
    assert Config().ai_model_for("openai") == "gpt-6-luna" and Config().ai_model_for("ollama") == ""


def test_bad_address_on_save_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError):
        save_config(Config(ai_other_url="ftp://x"), tmp_path / "c.json")


@pytest.mark.parametrize("field", ["ai_other_url", "ai_ollama_url"])
def test_repr_redacts_ai_addresses(field):
    text = repr(Config(**{field: "https://u:secret@h.example/v1"}))
    assert "secret" not in text and "h.example" in text


def test_ai_rephrase_hotkey_defaults_to_empty_and_round_trips(tmp_path):
    assert Config().hotkey_ai_rephrase == ""
    path = tmp_path / "config.json"
    save_config(Config(hotkey_ai_rephrase="ctrl+alt+r"), path)
    assert load_config(path).hotkey_ai_rephrase == "ctrl+alt+r"


def test_with_ai_model_replaces_the_same_provider_entry():
    config = Config().with_ai_model("groq", "openai/gpt-oss-20b").with_ai_model("groq", "openai/gpt-oss-120b")
    assert config.ai_models == ("groq=openai/gpt-oss-120b",)


def test_load_drops_a_repeated_provider_entry_keeping_the_first(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"ai_models": ["groq=openai/gpt-oss-20b", "groq=openai/gpt-oss-120b"]}),
                    encoding="utf-8")
    assert load_config(path).ai_models == ("groq=openai/gpt-oss-20b",)


def test_ai_address_for_by_provider():
    config = Config(ai_ollama_url="http://h:11434", ai_other_url="http://o:8000/v1")
    assert (config.ai_address_for("ollama"), config.ai_address_for("other"), config.ai_address_for("openai")) == (
        "http://h:11434", "http://o:8000/v1", "")


def test_ai_model_for_anthropic_is_ai_model():
    assert Config(ai_model="claude-sonnet-5-5").ai_model_for("anthropic") == "claude-sonnet-5-5"


def test_load_empty_ollama_url_falls_back_to_default(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"ai_ollama_url": ""}), encoding="utf-8")
    assert load_config(path).ai_ollama_url == DEFAULT_OLLAMA_URL


def test_other_key_address_defaults_to_empty_and_round_trips(tmp_path):
    assert Config().ai_other_key_address == ""
    path = tmp_path / "config.json"
    save_config(Config(ai_other_key_address="http://localhost:1234/v1"), path)
    assert load_config(path).ai_other_key_address == "http://localhost:1234/v1"


def test_other_key_address_is_validated_and_normalised(tmp_path):
    assert save_config(Config(ai_other_key_address="http://localhost:1234/v1/"),
                       tmp_path / "c.json").ai_other_key_address == "http://localhost:1234/v1"
    with pytest.raises(ConfigError):
        save_config(Config(ai_other_key_address="ftp://x"), tmp_path / "d.json")


def test_bad_other_key_address_on_load_falls_back_to_empty(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"ai_other_key_address": "ftp://x", "ai_other_url": "http://localhost:1234/v1"}),
                    encoding="utf-8")
    loaded = load_config(path)
    assert loaded.ai_other_key_address == "" and loaded.ai_other_url == "http://localhost:1234/v1"


def test_repr_redacts_other_key_address():
    text = repr(Config(ai_other_key_address="https://u:secret@h.example/v1"))
    assert "secret" not in text and "h.example" in text


def _write(tmp_path, data):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_new_installs_do_not_check_file_explorer():
    assert "explorer.exe" in Config().disabled_apps


def test_older_settings_file_gets_file_explorer_added_once(tmp_path):
    config = load_config(_write(tmp_path, {"disabled_apps": ["cmd.exe"]}))
    assert config.disabled_apps == ("cmd.exe", "explorer.exe")
    assert config.defaults_version == Config().defaults_version
    save_config(config, tmp_path / "config.json")
    assert load_config(tmp_path / "config.json").disabled_apps == ("cmd.exe", "explorer.exe")


def test_file_explorer_removed_after_the_upgrade_stays_removed(tmp_path):
    current = Config().defaults_version
    config = load_config(_write(tmp_path, {"disabled_apps": ["cmd.exe"], "defaults_version": current}))
    assert config.disabled_apps == ("cmd.exe",)


@pytest.mark.parametrize(
    "data",
    [
        {"disabled_apps": ["EXPLORER.EXE"]},  # already listed, in any case
        {"disabled_apps": [], "always_check_apps": ["Explorer.exe"]},  # the user chose to check it
    ],
)
def test_upgrade_leaves_file_explorer_as_the_user_set_it(tmp_path, data):
    config = load_config(_write(tmp_path, data))
    assert [app for app in config.disabled_apps if app.casefold() == "explorer.exe"] == data["disabled_apps"]


@pytest.mark.parametrize("bad", [0, "2", True, 1.5])
def test_bad_defaults_version_is_rejected(bad):
    with pytest.raises(ConfigError):
        save_config(replace(Config(), defaults_version=bad), None)  # validate runs before writing

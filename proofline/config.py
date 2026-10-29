"""Load, validate, and save user settings in config.json.

Settings and logs live under %LOCALAPPDATA%\\Proofline so they are
never synced by OneDrive along with the project folder. The portable build (a
portable.txt file beside Proofline.exe) keeps them in a data folder beside the exe.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from proofline.ai_prices import DEFAULT_MODEL, default_model
from proofline.ai_providers import (
    DEFAULT_OLLAMA_URL,
    DEFAULT_PROVIDER,
    PROVIDER_IDS,
    is_valid_model_name,
    normalize_ai_address,
)

log = logging.getLogger(__name__)

APP_DIR_NAME = "Proofline"
PORTABLE_MARKER = "portable.txt"  # shipped beside Proofline.exe in the portable zip only
PORTABLE_DATA_DIR_NAME = "data"


def app_data_dir(
    frozen: bool | None = None, executable: Path | None = None, local_app_data: str | None = None,
) -> tuple[Path, bool]:
    r"""(folder for settings, logs and usage files, is_portable).

    A packaged build with portable.txt beside its exe keeps everything in <exe folder>\data;
    any other run uses %LOCALAPPDATA%\Proofline.
    """
    frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if frozen:
        exe_dir = Path(executable or sys.executable).resolve().parent
        if (exe_dir / PORTABLE_MARKER).is_file():
            return exe_dir / PORTABLE_DATA_DIR_NAME, True
    base = local_app_data if local_app_data is not None else os.environ.get("LOCALAPPDATA")
    return Path(base or Path.home() / "AppData" / "Local") / APP_DIR_NAME, False


APP_DATA_DIR, IS_PORTABLE = app_data_dir()
INSTALLED_DATA_DIR = app_data_dir(frozen=False)[0]  # where an installed (or 0.1.0) copy keeps settings
SETTINGS_FILE_NAME = "config.json"


def import_settings_into_portable(portable_dir: Path, installed_dir: Path = INSTALLED_DATA_DIR) -> str:
    """Copy an installed copy's settings into a portable copy that has none yet.

    Copying the portable zip over an older install (0.1.0 kept settings in %LOCALAPPDATA%)
    would otherwise start from scratch. Copies, never moves; runs before logging starts, so
    it returns what happened ("" = nothing).
    """
    source, target = installed_dir / SETTINGS_FILE_NAME, portable_dir / SETTINGS_FILE_NAME
    if target.exists() or not source.is_file():
        return ""
    try:
        portable_dir.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    except OSError as exc:
        return f"Could not copy settings from {source} into the portable copy: {exc}"
    return f"Copied settings from {source} into the portable copy ({target})"
CONFIG_PATH = APP_DATA_DIR / "config.json"

# 127.0.0.1, not localhost: Windows tries ::1 first, and a server listening on IPv4 only
# then costs ~2 s per check (measured 2026-10-24 against Docker Desktop).
DEFAULT_SERVER_URL = "http://127.0.0.1:8010/v2/check"
CHECK_ENDPOINT = "/v2/check"
MIN_DEBOUNCE_MS = 200
MAX_DEBOUNCE_MS = 10_000
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
THEMES = ("auto", "light", "dark")
# LanguageTool language codes offered in Settings and the tray flyout, with display names.
LANGUAGES = {
    "auto": "Auto-detect",
    "en-US": "English (US)",
    "en-GB": "English (UK)",
    "es": "Spanish",
    "fr": "French",
    "de-DE": "German",
    "pt-PT": "Portuguese",
    "it": "Italian",
    "nl": "Dutch",
}
HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
DEFAULT_TRAY_COLOR = "#2e7d32"
DEFAULT_MIN_WORDS = 2
MIN_WORDS_RANGE = (1, 10)
DEFAULT_HOTKEY_TOGGLE = "ctrl+alt+p"
DEFAULT_HOTKEY_CHECK_NOW = "ctrl+alt+l"
DEFAULT_HOTKEY_FIX_FIRST = "ctrl+alt+j"
BOOL_FIELDS = ("enabled", "debug_mode", "badge_always_visible", "picky", "start_with_windows", "check_for_updates",
               "share_usage_counts", "welcome_shown", "flag_hidden_characters", "show_underlines", "ai_enabled")
AI_CAP_CENTS_RANGE = (10, 10_000)  # $0.10 to $100 a month
AI_MODEL_SEPARATOR = "="  # ai_models entries look like "groq=openai/gpt-oss-20b"
OLLAMA_ID = "ollama"
OTHER_ID = "other"
LIST_FIELDS = (
    "disabled_apps",
    "disabled_windows",
    "personal_dictionary",
    "disabled_rules",
    "rule_labels",
    "disabled_categories",
    "shown_hints",
    "always_check_apps",
    "custom_fields",
    "ai_models",
)
FIELD_SIGNATURE_SEPARATOR = "|"
FIELD_SIGNATURE_PARTS = 3
ANY_CLASS = "*"
HOTKEY_FIELDS = ("hotkey_toggle", "hotkey_check_now", "hotkey_fix_first", "hotkey_ai_rephrase")
URL_FIELDS = ("server_url", "ai_ollama_url", "ai_other_url", "ai_other_key_address")  # redacted in repr

# Recommended exclusions: places where checking is a security risk or just noise.
# They are the defaults for new installs and can be re-added from Settings.
DEFAULT_DISABLED_APPS = (
    # Password managers
    "KeePass.exe",
    "KeePassXC.exe",
    "1Password.exe",
    "Bitwarden.exe",
    # Terminals and shells
    "WindowsTerminal.exe",
    "cmd.exe",
    "powershell.exe",
    "pwsh.exe",
    "conhost.exe",
    "putty.exe",
    # Remote sessions and VMs (text is typed into another machine)
    "mstsc.exe",
    "vmconnect.exe",
    "RDCMan.exe",
    # Code, query, and spreadsheet editors
    "Code.exe",
    "devenv.exe",
    "Ssms.exe",
    "EXCEL.EXE",
    # File Explorer: its address bar, search box and rename box hold paths and file names
    "explorer.exe",
)
# Apps added to the recommended list after the first release, by the defaults_version that added
# them. Loading an older settings file adds them once, unless the user set the app to always check.
ADDED_DISABLED_APPS = {2: ("explorer.exe",)}
DEFAULTS_VERSION = max(ADDED_DISABLED_APPS)
LEGACY_DEFAULTS_VERSION = 1  # a settings file without the key predates the added apps
DEFAULT_DISABLED_WINDOWS = (
    "Password",
    "Sign in",
    "Log in",
    "Login",
    "Windows Security",
    "Command Prompt",
    "PowerShell",
    "Remote Desktop",
)


def field_signature(process_name: str, control_type: str, class_name: str) -> str:
    """Identifies a kind of text field, e.g. 'erp.exe|PaneControl|TEditor'."""
    return FIELD_SIGNATURE_SEPARATOR.join((process_name, control_type, class_name))


def custom_field_matches(signature: str, entries: tuple[str, ...]) -> bool:
    """Case-insensitive match; a class part of '*' matches any class name."""
    app, control_type, _class = (signature.casefold().split(FIELD_SIGNATURE_SEPARATOR) + ["", ""])[:3]
    for entry in entries:
        e_app, e_type, e_class = (entry.casefold().split(FIELD_SIGNATURE_SEPARATOR) + ["", ""])[:3]
        if (e_app, e_type) == (app, control_type) and e_class in (ANY_CLASS, _class):
            return True
    return False


def saveable_signature(signature: str) -> str:
    """Web apps use long, generated CSS class lists that change between versions and
    even with focus state; store those with a '*' class so the entry keeps matching."""
    app, control_type, class_name = (signature.split(FIELD_SIGNATURE_SEPARATOR) + ["", ""])[:3]
    if any(ch.isspace() for ch in class_name):
        class_name = ANY_CLASS
    return field_signature(app, control_type, class_name)


RULE_LABEL_SEPARATOR = "="


def rule_label(config: Config, rule_id: str) -> str:
    """How Settings shows a turned-off rule: its name with the id, or the id alone."""
    for entry in config.rule_labels:
        key, _, name = entry.partition(RULE_LABEL_SEPARATOR)
        if key == rule_id and name:
            return f"{name} ({rule_id})"
    return rule_id


def with_rule_label(config: Config, rule_id: str, name: str) -> Config:
    """config with the rule's display name recorded (one entry per rule; the latest wins)."""
    kept = tuple(e for e in config.rule_labels if e.partition(RULE_LABEL_SEPARATOR)[0] != rule_id)
    return replace(config, rule_labels=(*kept, f"{rule_id}{RULE_LABEL_SEPARATOR}{name.strip()}"))


class ConfigError(ValueError):
    """Raised when a setting has an invalid value."""


@dataclass(frozen=True, repr=False)
class Config:
    server_url: str = DEFAULT_SERVER_URL
    language: str = "auto"
    debounce_ms: int = 1000
    enabled: bool = True
    disabled_apps: tuple[str, ...] = DEFAULT_DISABLED_APPS
    disabled_windows: tuple[str, ...] = DEFAULT_DISABLED_WINDOWS
    debug_mode: bool = False
    show_underlines: bool = True  # wavy lines under flagged words, where the app reports their position
    badge_always_visible: bool = True
    personal_dictionary: tuple[str, ...] = ()
    disabled_rules: tuple[str, ...] = ()
    disabled_categories: tuple[str, ...] = ()
    picky: bool = False
    flag_hidden_characters: bool = True  # invisible characters and unusual spaces (hidden_chars)
    ai_enabled: bool = False  # AI provider suggestions, sent only when asked; the key is in Credential Manager
    ai_provider: str = DEFAULT_PROVIDER  # which service receives AI requests (ai_providers.PROVIDER_IDS)
    ai_model: str = DEFAULT_MODEL  # Claude's model only; other providers use ai_models
    ai_models: tuple[str, ...] = ()  # "<provider id>=<model name>" for each provider other than Claude
    ai_ollama_url: str = DEFAULT_OLLAMA_URL
    ai_other_url: str = ""  # the address of an OpenAI-compatible server; "" when none is set
    ai_other_key_address: str = ""  # the address Other's saved key was saved for; the key is sent only there
    ai_monthly_cap_cents: int = 100  # AI requests stop once this month's recorded cost would pass it
    start_with_windows: bool = False
    hotkey_toggle: str = DEFAULT_HOTKEY_TOGGLE
    hotkey_check_now: str = DEFAULT_HOTKEY_CHECK_NOW
    hotkey_fix_first: str = DEFAULT_HOTKEY_FIX_FIRST  # keyboard alternative to clicking a suggestion
    hotkey_ai_rephrase: str = ""  # AI: rephrase the sentence at the caret; off by default
    theme: str = "auto"
    tray_color: str = DEFAULT_TRAY_COLOR
    min_words: int = DEFAULT_MIN_WORDS
    shown_hints: tuple[str, ...] = ()
    always_check_apps: tuple[str, ...] = ()
    custom_fields: tuple[str, ...] = ()  # field_signature() strings
    paused_until: str = ""  # ISO local time a timed pause ends; "" when not paused
    rule_labels: tuple[str, ...] = ()  # "RULE_ID=Name" for rules turned off from the popup
    check_for_updates: bool = True  # ask GitHub daily whether a newer release exists
    share_usage_counts: bool = True  # anonymous Corrections Applied total for the README badges
    welcome_shown: bool = False  # the first-run welcome window was finished or closed
    defaults_version: int = DEFAULTS_VERSION  # the ADDED_DISABLED_APPS already applied

    def __repr__(self) -> str:
        values = ", ".join(
            f"{f.name}={redact_url(getattr(self, f.name)) if f.name in URL_FIELDS else getattr(self, f.name)!r}"
            for f in fields(self)
        )
        return f"Config({values})"

    def ai_model_for(self, pid: str) -> str:
        """The model for provider pid: ai_model for Claude, else the user's pick, else that
        provider's cheapest priced model ("" when it has none)."""
        if pid == DEFAULT_PROVIDER:
            return self.ai_model
        chosen = dict(entry.partition(AI_MODEL_SEPARATOR)[::2] for entry in self.ai_models)
        return chosen.get(pid, default_model(pid))

    def with_ai_model(self, pid: str, model: str) -> Config:
        """A copy with pid's model set; each non-Claude provider keeps one ai_models entry."""
        if pid == DEFAULT_PROVIDER:
            return replace(self, ai_model=model)
        kept = tuple(e for e in self.ai_models if e.partition(AI_MODEL_SEPARATOR)[0] != pid)
        return replace(self, ai_models=(*kept, f"{pid}{AI_MODEL_SEPARATOR}{model}"))

    def ai_address_for(self, pid: str) -> str:
        """The address the user set for a local provider; "" for every other provider."""
        return {OLLAMA_ID: self.ai_ollama_url, OTHER_ID: self.ai_other_url}.get(pid, "")

    def other_key_applies(self) -> bool:
        """True when Other's saved key was saved for the address Other uses now. A key saved for another
        address (or for none) is never sent, even after a restart; saving the key again rebinds it."""
        return self.ai_other_key_address == self.ai_other_url

    def is_custom_field(self, signature: str) -> bool:
        return custom_field_matches(signature, self.custom_fields)

    def is_disabled_for(self, process_name: str, window_title: str) -> bool:
        """True if checking is off for this app (exact name) or for a window whose title
        contains one of the disabled_windows entries. Both comparisons ignore case.
        Apps in always_check_apps are never disabled."""
        app = process_name.casefold()
        if app in {entry.casefold() for entry in self.always_check_apps}:
            return False
        if app in {entry.casefold() for entry in self.disabled_apps}:
            return True
        title = window_title.casefold()
        return any(entry.casefold() in title for entry in self.disabled_windows)


def redact_url(url: str) -> str:
    """Hide any user:password@ credentials so the URL is safe to log or display."""
    parsed = urlparse(url)
    if "@" not in parsed.netloc:
        return url
    host = parsed.netloc.rsplit("@", 1)[1]
    return urlunparse(parsed._replace(netloc=f"***@{host}"))


def is_insecure_remote(url: str) -> bool:
    """True when text would travel unencrypted to a host other than this machine."""
    parsed = urlparse(url)
    return parsed.scheme == "http" and (parsed.hostname or "") not in LOOPBACK_HOSTS


def normalize_server_url(url: str) -> str:
    """Validate a server URL and append /v2/check when only a base URL is given."""
    cleaned = url.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ConfigError(
            "Server URL must start with http:// or https:// and include a host, "
            "e.g. http://127.0.0.1:8010/v2/check"
        )
    path = parsed.path.rstrip("/")
    if path in ("", "/v2"):
        path = CHECK_ENDPOINT
    return urlunparse(parsed._replace(path=path))


def validate(config: Config) -> Config:
    """Return a normalized copy of config, or raise ConfigError."""
    if not isinstance(config.language, str) or not config.language.strip():
        raise ConfigError("Language must be a code such as 'auto' or 'en-US'.")
    is_int = isinstance(config.debounce_ms, int) and not isinstance(config.debounce_ms, bool)
    if not is_int or not MIN_DEBOUNCE_MS <= config.debounce_ms <= MAX_DEBOUNCE_MS:
        raise ConfigError(
            f"Typing delay must be between {MIN_DEBOUNCE_MS} and {MAX_DEBOUNCE_MS} ms."
        )
    for name in BOOL_FIELDS:
        if not isinstance(getattr(config, name), bool):
            raise ConfigError(f"'{name}' must be true or false.")
    for name in ("server_url", *HOTKEY_FIELDS):
        if not isinstance(getattr(config, name), str):
            raise ConfigError(f"'{name}' must be text.")
    for signature in _string_tuple(config.custom_fields, "custom_fields"):
        parts = signature.split(FIELD_SIGNATURE_SEPARATOR)
        if len(parts) != FIELD_SIGNATURE_PARTS or not parts[0].strip() or not parts[1].strip():
            raise ConfigError(f"Custom field {signature!r} must look like app.exe|ControlType|ClassName.")
    low, high = MIN_WORDS_RANGE
    if type(config.min_words) is not int or not low <= config.min_words <= high:
        raise ConfigError(f"Minimum words must be between {low} and {high}.")
    if type(config.defaults_version) is not int or config.defaults_version < LEGACY_DEFAULTS_VERSION:
        raise ConfigError("'defaults_version' must be a whole number from 1.")
    _validate_paused_until(config.paused_until)
    _validate_ai(config)
    if config.theme not in THEMES:
        raise ConfigError(f"Theme must be one of: {', '.join(THEMES)}.")
    if not isinstance(config.tray_color, str) or not HEX_COLOR.fullmatch(config.tray_color):
        raise ConfigError("Tray colour must look like #2e7d32.")
    return replace(
        config,
        server_url=normalize_server_url(config.server_url),
        language=config.language.strip(),
        **{name: _string_tuple(getattr(config, name), name) for name in LIST_FIELDS},
        **{name: getattr(config, name).strip().lower() for name in HOTKEY_FIELDS},
        **_normalized_ai_addresses(config),
    )


def _validate_ai(config: Config) -> None:
    if config.ai_provider not in PROVIDER_IDS:
        raise ConfigError(f"AI provider must be one of: {', '.join(PROVIDER_IDS)}.")
    if not is_valid_model_name(config.ai_model):
        raise ConfigError("AI model must be a name of letters, digits, and . _ : / - (up to 200 characters).")
    if not isinstance(config.ai_models, (list, tuple)) or not all(_is_ai_model_entry(e) for e in config.ai_models):
        raise ConfigError("Each AI model must look like provider=model-name, for a provider other than Claude.")
    chosen = [entry.partition(AI_MODEL_SEPARATOR)[0] for entry in config.ai_models]
    if len(set(chosen)) != len(chosen):
        raise ConfigError("Each provider can have only one AI model.")
    low, high = AI_CAP_CENTS_RANGE
    if not _is_cap(config.ai_monthly_cap_cents):
        raise ConfigError(f"Monthly AI limit must be between {low} and {high} cents.")


def _normalized_ai_addresses(config: Config) -> dict[str, str]:
    return {
        "ai_ollama_url": _ai_address(config.ai_ollama_url, "ai_ollama_url", optional=False),
        "ai_other_url": _ai_address(config.ai_other_url, "ai_other_url", optional=True),
        "ai_other_key_address": _ai_address(config.ai_other_key_address, "ai_other_key_address", optional=True),
    }


def _ai_address(value: object, name: str, optional: bool) -> str:
    """A normalized address; the value itself is never echoed, as it may hold a password."""
    if optional and value == "":
        return ""
    if not isinstance(value, str):
        raise ConfigError(f"'{name}' must be text.")
    try:
        return normalize_ai_address(value)
    except ValueError as exc:
        raise ConfigError(f"'{name}' is not a valid address: {exc}") from exc


def _is_ai_model_entry(entry: object) -> bool:
    if not isinstance(entry, str):
        return False
    pid, sep, name = entry.partition(AI_MODEL_SEPARATOR)
    return bool(sep) and pid in PROVIDER_IDS and pid != DEFAULT_PROVIDER and is_valid_model_name(name)


def _is_cap(value: object) -> bool:
    low, high = AI_CAP_CENTS_RANGE
    return type(value) is int and low <= value <= high


def _address_ok(value: object, optional: bool) -> bool:
    try:
        _ai_address(value, "", optional)
    except ConfigError:
        return False
    return True


# Each AI setting that load_config checks on its own; a bad value falls back to its default alone.
AI_VALUE_CHECKS = {
    "ai_enabled": lambda value: isinstance(value, bool),
    "ai_provider": lambda value: value in PROVIDER_IDS,
    "ai_model": is_valid_model_name,
    "ai_monthly_cap_cents": _is_cap,
    "ai_ollama_url": lambda value: _address_ok(value, optional=False),
    "ai_other_url": lambda value: _address_ok(value, optional=True),
    "ai_other_key_address": lambda value: _address_ok(value, optional=True),
}


def _sanitize_ai(raw: dict) -> dict:
    """Replace each bad AI setting with its default and drop bad ai_models entries, so one bad
    value does not reset the other settings. Logs one warning per bad value (never its content)."""
    clean = dict(raw)
    defaults = Config()
    for name, is_ok in AI_VALUE_CHECKS.items():
        if name in clean and not is_ok(clean[name]):
            log.warning("AI setting %s is not valid; using its default", name)
            clean[name] = getattr(defaults, name)
    if "ai_models" in clean:
        clean["ai_models"] = _kept_ai_models(clean["ai_models"])
    return clean


def _kept_ai_models(entries: object) -> list:
    if not isinstance(entries, list):
        log.warning("AI setting ai_models is not a list; dropping it")
        return []
    kept: list[str] = []
    chosen: set[str] = set()
    for entry in entries:
        pid = entry.partition(AI_MODEL_SEPARATOR)[0] if isinstance(entry, str) else None
        if _is_ai_model_entry(entry) and pid not in chosen:
            kept.append(entry)
            chosen.add(pid)
    if len(kept) != len(entries):
        log.warning("Dropped %d AI model entries that were invalid or repeated", len(entries) - len(kept))
    return kept


def _validate_paused_until(value: object) -> None:
    if not isinstance(value, str):
        raise ConfigError("'paused_until' must be text.")
    if not value:
        return
    try:
        datetime.fromisoformat(value)
    except ValueError as exc:
        raise ConfigError("'paused_until' must be a date and time like 2026-10-23T14:00:00.") from exc


def _string_tuple(values: object, name: str) -> tuple[str, ...]:
    """Validate a list of non-empty strings and return it de-duplicated, order kept."""
    if not isinstance(values, (list, tuple)) or not all(
        isinstance(v, str) and v.strip() for v in values
    ):
        raise ConfigError(f"'{name}' must be a list of non-empty strings.")
    return tuple(dict.fromkeys(values))


def load_config(path: Path = CONFIG_PATH) -> Config:
    """Read config.json, falling back to defaults when it is missing or invalid."""
    if not path.exists():
        log.info("No config at %s; using defaults", path)
        return Config()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("Could not read %s (%s); using defaults", path, exc)
        return Config()
    if not isinstance(raw, dict):
        log.warning("%s does not contain a JSON object; using defaults", path)
        return Config()

    known = {f.name for f in fields(Config)}
    raw = _sanitize_ai(raw)
    raw.setdefault("defaults_version", LEGACY_DEFAULTS_VERSION)
    try:
        return with_added_defaults(validate(Config(**{k: v for k, v in raw.items() if k in known})))
    except ConfigError as exc:
        log.warning("Invalid setting in %s (%s); using defaults", path, exc)
        return Config()


def with_added_defaults(config: Config) -> Config:
    """config with the recommended exclusions added since its defaults_version, each once.

    An app already listed, or set to always check, is left as the user has it. The result is
    saved with the next settings change; until then each start applies the same addition.
    """
    if config.defaults_version >= DEFAULTS_VERSION:
        return config
    listed = {app.casefold() for app in (*config.disabled_apps, *config.always_check_apps)}
    added = tuple(
        app for version, apps in sorted(ADDED_DISABLED_APPS.items()) if version > config.defaults_version
        for app in apps if app.casefold() not in listed
    )
    if added:
        log.info("Added to the apps not checked (new recommended exclusions): %s", ", ".join(added))
    return replace(config, disabled_apps=(*config.disabled_apps, *added), defaults_version=DEFAULTS_VERSION)


def save_config(config: Config, path: Path = CONFIG_PATH) -> Config:
    """Validate and atomically write config. Returns the normalized config."""
    validated = validate(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(asdict(validated), indent=2), encoding="utf-8")
    tmp_path.replace(path)
    log.info("Saved config to %s", path)
    return validated

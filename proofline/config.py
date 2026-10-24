"""Load, validate, and save user settings in config.json.

Settings and logs live under %LOCALAPPDATA%\\Proofline so they are
never synced by OneDrive along with the project folder.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

log = logging.getLogger(__name__)

APP_DATA_DIR = (
    Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    / "Proofline"
)
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
BOOL_FIELDS = ("enabled", "debug_mode", "badge_always_visible", "picky", "start_with_windows")
LIST_FIELDS = (
    "disabled_apps",
    "disabled_windows",
    "personal_dictionary",
    "disabled_rules",
    "disabled_categories",
    "shown_hints",
    "always_check_apps",
    "custom_fields",
)
FIELD_SIGNATURE_SEPARATOR = "|"
FIELD_SIGNATURE_PARTS = 3
ANY_CLASS = "*"
HOTKEY_FIELDS = ("hotkey_toggle", "hotkey_check_now")

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
)
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
    badge_always_visible: bool = True
    personal_dictionary: tuple[str, ...] = ()
    disabled_rules: tuple[str, ...] = ()
    disabled_categories: tuple[str, ...] = ()
    picky: bool = False
    start_with_windows: bool = False
    hotkey_toggle: str = DEFAULT_HOTKEY_TOGGLE
    hotkey_check_now: str = DEFAULT_HOTKEY_CHECK_NOW
    theme: str = "auto"
    tray_color: str = DEFAULT_TRAY_COLOR
    min_words: int = DEFAULT_MIN_WORDS
    shown_hints: tuple[str, ...] = ()
    always_check_apps: tuple[str, ...] = ()
    custom_fields: tuple[str, ...] = ()  # field_signature() strings
    paused_until: str = ""  # ISO local time a timed pause ends; "" when not paused

    def __repr__(self) -> str:
        values = ", ".join(
            f"{f.name}={redact_url(self.server_url) if f.name == 'server_url' else getattr(self, f.name)!r}"
            for f in fields(self)
        )
        return f"Config({values})"

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
    _validate_paused_until(config.paused_until)
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
    )


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
    try:
        return validate(Config(**{k: v for k, v in raw.items() if k in known}))
    except ConfigError as exc:
        log.warning("Invalid setting in %s (%s); using defaults", path, exc)
        return Config()


def save_config(config: Config, path: Path = CONFIG_PATH) -> Config:
    """Validate and atomically write config. Returns the normalized config."""
    validated = validate(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(asdict(validated), indent=2), encoding="utf-8")
    tmp_path.replace(path)
    log.info("Saved config to %s", path)
    return validated

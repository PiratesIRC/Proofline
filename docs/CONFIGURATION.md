# Configuration

Everything in the Settings window is stored in one JSON file. You normally change settings in
the app; this page is for administrators, scripted deployment and troubleshooting.

## Files and registry

| What | Where |
|---|---|
| Settings | `%LOCALAPPDATA%\Proofline\config.json` |
| Logs | `%LOCALAPPDATA%\Proofline\logs\app.log` (rotates at 2 MB, 3 backups) |
| Single-instance lock | `%LOCALAPPDATA%\Proofline\app.lock` |
| Update check result | `%LOCALAPPDATA%\Proofline\version_check.json` |
| Usage count ledger | `%LOCALAPPDATA%\Proofline\usage_counts.jsonl` (one line per applied correction) |
| Usage client state | `%LOCALAPPDATA%\Proofline\usage\proofline\` (random install id, report timing) |
| Notification icon | `%LOCALAPPDATA%\Proofline\app-icon.png` |
| Start with Windows | `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, value `Proofline` |
| Notification name and icon | `HKCU\Software\Classes\AppUserModelId\PiratesIRC.Proofline` |

No administrator rights are needed; nothing is written under `HKEY_LOCAL_MACHINE`.

`config.json` is written atomically (temp file, then rename). If it is missing, unreadable or
invalid, the app starts with defaults and logs a warning. Unknown keys are ignored. Keys that are
absent take their defaults, so a file containing only `server_url` is valid.

## Settings reference

| Key | Type | Default | Settings location | Notes |
|---|---|---|---|---|
| `server_url` | string | `http://127.0.0.1:8010/v2/check` | General › LanguageTool server | `http://` or `https://`; a bare host or `/v2` gets `/v2/check` appended. Credentials (`user:pass@`) are redacted in logs. |
| `language` | string | `auto` | General › Language; quick settings | A LanguageTool code such as `en-US`, `en-GB`, `es`, `de-DE`. |
| `enabled` | bool | `true` | Tray › Checking enabled; quick settings | Pausing for 1 hour sets this to `false` and back. |
| `start_with_windows` | bool | `false` | General | Kept in sync with the Run registry value. |
| `debounce_ms` | int | `1000` | Checking › Check after I stop typing for | 200–10000. |
| `min_words` | int | `2` | Checking › Only check text with at least | 1–10. `Ctrl+Alt+L` ignores it. |
| `picky` | bool | `false` | Checking › Picky mode | Sends `level=picky`. |
| `personal_dictionary` | list of strings | `[]` | Checking › Personal dictionary; popup › Add to dictionary | Spelling matches only; case-insensitive. |
| `disabled_rules` | list of strings | `[]` | Checking › Turned-off rules; popup › Turn off this rule | LanguageTool rule IDs, sent as `disabledRules`. |
| `disabled_categories` | list of strings | `[]` | Checking › Turned-off categories | Category IDs (upper-cased), sent as `disabledCategories`. |
| `disabled_apps` | list of strings | see below | Apps & fields › Don't check in › Apps | Process names, exact match, case-insensitive. |
| `disabled_windows` | list of strings | see below | Apps & fields › Window titles containing | Matches if the window title *contains* the text, case-insensitive. |
| `always_check_apps` | list of strings | `[]` | Apps & fields › Always check › Apps | Overrides the two lists above. |
| `custom_fields` | list of strings | `[]` | Apps & fields › Custom text fields; Add a text field… | `app.exe\|ControlType\|ClassName`; `*` as the class matches any class. Checked even when the control doesn't look like a text box, and overrides exclusions and field filters (never password fields). |
| `theme` | string | `auto` | Appearance › Theme | `auto` (follow Windows), `light`, `dark`. |
| `tray_color` | string | `#2e7d32` | Appearance › Accent and tray icon colour | `#rrggbb`; also the accent colour of Settings and quick settings. |
| `badge_always_visible` | bool | `true` | Appearance › Show the badge in every text field | When `false`, the badge appears only when there are issues. |
| `hotkey_toggle` | string | `ctrl+alt+p` | Shortcuts | `""` turns the shortcut off. Modifiers: `ctrl`, `alt`, `shift`, `win`; keys: letters, digits, `f1`–`f24`, `space`, `enter`, `tab`, `esc`, … |
| `hotkey_check_now` | string | `ctrl+alt+l` | Shortcuts | Must differ from `hotkey_toggle`. |
| `debug_mode` | bool | `false` | Advanced › Debug mode | Adds short text samples to the log. |
| `check_for_updates` | bool | `true` | Advanced › Check for updates | Asks GitHub whether a newer release exists (see below). Sends no text. |
| `share_usage_counts` | bool | `true` | Advanced › Share anonymous usage counts | Sends the Corrections Applied total and a random id to plugin-stats.dpas.workers.dev for the README badges. Turning it off asks the server to delete this install's figures. See README › Anonymous usage counts. |
| `paused_until` | string | `""` | Quick settings › Pause for 1 hour | Local time the pause ends, e.g. `2026-10-23T14:00:00`. Restored at startup; checking turns back on once it has passed. `""` when not paused. |
| `shown_hints` | list of strings | `[]` | (none) | Setup tips already shown (`google-docs`, `java-access-bridge`, `firefox-update`) and releases already announced (`update-<version>`). Remove an entry to see that tip or announcement again. |

### Default exclusions

`disabled_apps`: `KeePass.exe`, `KeePassXC.exe`, `1Password.exe`, `Bitwarden.exe`,
`WindowsTerminal.exe`, `cmd.exe`, `powershell.exe`, `pwsh.exe`, `conhost.exe`, `putty.exe`,
`mstsc.exe`, `vmconnect.exe`, `RDCMan.exe`, `Code.exe`, `devenv.exe`, `Ssms.exe`, `EXCEL.EXE`.

`disabled_windows`: `Password`, `Sign in`, `Log in`, `Login`, `Windows Security`,
`Command Prompt`, `PowerShell`, `Remote Desktop`.

These apply to new installs and to config files that never saved these lists. **Add recommended
exclusions** (Apps & fields › Apps) adds any that are missing without touching your own entries.

### Built-in field filters (not configurable)

Independently of the lists above, the app never checks password fields, read-only fields,
dropdowns without editable text, browser address bars, numeric/spinner fields, or fields whose
label, placeholder or automation ID mentions one-time/verification codes, card numbers, CVV,
SSN, PIN, routing or account numbers, IBAN, API/secret keys or tokens. A `custom_fields` entry
overrides these filters except for passwords.

### Example

```json
{
  "server_url": "https://languagetool.example.org/v2/check",
  "language": "en-US",
  "start_with_windows": true,
  "personal_dictionary": ["Dispatcharr", "Laserfiche"],
  "disabled_categories": ["TYPOGRAPHY"],
  "always_check_apps": ["erp.exe"]
}
```

## Environment variables

| Variable | Effect |
|---|---|
| `PROOFLINE_LOG_LEVEL` | Console log level (`DEBUG`, `INFO`, …). Default `INFO`; the file always records `DEBUG`. Invalid values fall back to `INFO` with a warning. |
| `PROOFLINE_LOG_TEXT=1` | Same as Debug mode: include short text samples in logs. |

The names from before the rename, `LT_DESKTOP_LOG_LEVEL` and `LT_DESKTOP_LOG_TEXT`, still work when
the new name is not set.

**Upgrading from LanguageTool Desktop:** on start, if `%LOCALAPPDATA%\LanguageToolDesktop` exists
and `%LOCALAPPDATA%\Proofline` does not, the folder is moved (or, if a file in it is in use, only
`config.json` is copied). The old Run value `LanguageToolDesktop` and the key
`HKCU\Software\Classes\AppUserModelId\PiratesIRC.LanguageToolDesktop` are deleted.
| `LT_TEST_SERVER_URL` | Development only: enables the live-server integration tests. |

## Limits

- At most 20,000 characters of a field are read and sent per check (the public API's request
  limit).
- The focused element is polled every 300 ms.
- When the server is unreachable, it is re-tested every 60 seconds.
- Update check: one anonymous request to
  `https://api.github.com/repos/PiratesIRC/Proofline/releases/latest` on a background thread at
  start, then again only when the cached result is stale (24 hours after a success, 2 hours after
  a failure, or after the installed version changed). Settings only reads the cached result. A new
  release is announced once by a tray notification.
- "Can't reach the server" is notified once per outage and at most once every 30 minutes.

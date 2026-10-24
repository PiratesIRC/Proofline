# Development

## Setup

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

`requirements.txt` holds the runtime dependencies (PyQt6, uiautomation, pywin32, requests);
`requirements-dev.txt` adds pytest, pytest-qt, pytest-cov and ruff; `requirements-build.txt`
adds PyInstaller for the packaged build (see [Releasing](#releasing-a-build-for-colleagues)).

## Running

```powershell
.\.venv\Scripts\python.exe main.py                     # app, with console logging
$env:PROOFLINE_LOG_LEVEL = "DEBUG"; .\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe -m proofline.probe 60       # what UIA sees in the focused field
```

Only one instance can run (lock file). Quit the tray app before starting another from a
terminal.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q --cov=proofline --cov-report=term-missing
$env:LT_TEST_SERVER_URL = "http://127.0.0.1:8010/v2"; .\.venv\Scripts\python.exe -m pytest -q
```

- GUI tests use **pytest-qt** (`qtbot`, `qapp`).
- **Live server tests** (`tests/test_integration_server.py`, marker `integration`) are skipped
  unless `LT_TEST_SERVER_URL` is set.
- **Clipboard tests** use the real Windows clipboard; each test saves and restores your clipboard,
  and opens it with retries because clipboard-history tools briefly hold it after changes.
- **Registry tests** (autostart, app identity) only touch keys under
  `HKCU\Software\ProoflineTest`, deleted afterwards. They never modify the real Run key.
- **Hotkey tests** register an unlikely combination (`ctrl+alt+shift+f24`) and simulate
  `WM_HOTKEY`.
- The UIA reader and correction code are exercised live (see `proofline/probe.py`) rather than
  unit-tested; their pure helpers are unit-tested. Coverage of `QThread.run` code isn't reported
  by coverage.py even though it is tested.
- `tests/factories.py` builds `FieldSnapshot` / `FocusResult` test data.

## Lint

```powershell
.\.venv\Scripts\python.exe -m ruff check proofline main.py tests
.\.venv\Scripts\python.exe -m ruff check proofline main.py tests --fix
```

## Conventions

- `from __future__ import annotations`, type hints on every signature, a module docstring.
- Immutable data: frozen dataclasses; change config with `dataclasses.replace` and save the copy.
- Named constants instead of magic numbers; functions under about 50 lines; files under 800.
- `logging`, never `print`. Never log typed text unless `text_logging_enabled()`; use
  `text_snapshot.loggable()` and `config.redact_url()`.
- All UIA calls happen on the monitor thread.
- Commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`.

## Adding a setting

1. Add the field with a default to `Config` in `config.py`; extend `validate()` (or add it to
   `BOOL_FIELDS` / `LIST_FIELDS`), and add tests in `tests/test_config.py`.
2. Add a card to the right page in `settings_pages.py`: load it in `_load()` and emit
   `self._emit(field=value)` on change. Give the card search `keywords`.
3. Use the value where it matters (monitor, checker, overlay, `integration.py` for OS-level
   effects). Components receive config through `config_provider` callables or
   `LanguageToolApp._set_config()`.
4. Document it in `docs/CONFIGURATION.md`, and in `README.md` if users need to know about it.
5. Add tests for the page (`tests/test_settings_window.py`) and the behaviour.

## Building and releasing

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt   # once: PyInstaller
winget install --id JRSoftware.InnoSetup -e --scope user               # once: Inno Setup 6
powershell -File packaging\build.ps1                                   # in its own process
```

`build.ps1` runs PyInstaller (`packaging/Proofline.spec`, a one-folder windowed build in
`dist\Proofline\`) and then makes the two release files:

- `dist\Proofline-<version>-portable.zip`: the app folder plus `portable.txt`, which makes the app
  keep its settings in `data\` next to the exe (`config.app_data_dir`).
- `dist\Proofline-<version>-setup.exe`: Inno Setup (`packaging/Proofline.iss`), per-user install
  into `%LOCALAPPDATA%\Programs\Proofline`, Start menu shortcut with the app's AppUserModelID,
  Windows 10 1809+ x64. Its uninstaller removes the Run value and the app registration, not the
  settings. `-SkipInstaller` builds only the zip.

Run it in its own PowerShell process: PyInstaller logs to stderr, which stops the script under a
`2>&1` redirect. The version comes from `proofline/__init__.py`; bump it and the CHANGELOG heading
before a release. `scripts/make_screenshots.py` re-renders the README images from the real widgets
with sample data (offscreen, 2x).

With **Start when I sign in to Windows** on, the Run entry points at the exe; at every startup the
app rewrites an entry that points somewhere else, so switching between source and the build, or
moving the folder, fixes itself the next time the app starts. The build is unsigned, so
SmartScreen may warn on first run.

A smoke test of a fresh build without touching your real settings: set `LOCALAPPDATA` to an
empty folder for that process. It still writes the real AppUserModelId registry key (and the Run
entry if Start with Windows is on in that config), so restart your usual copy afterwards.

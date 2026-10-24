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

## Releasing a build for colleagues

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt   # once: PyInstaller
.\packaging\build.ps1
```

This makes `dist\Proofline\` (a one-folder, windowed build with no Python needed) and
`dist\Proofline-<version>.zip`. The version comes from `proofline/__init__.py`; bump
it before a release. `packaging/Proofline.spec` bundles the `uiautomation` helper DLLs
and the comtypes UI Automation wrappers already generated in the venv, and
`packaging/make_icon.py` draws the exe icon from the tray badge.

Colleagues unzip the folder somewhere permanent and run `Proofline.exe`. With
**Start when I sign in to Windows** on, the Run entry points at the exe; at every startup the app
rewrites an entry that points somewhere else, so switching between source and the build, or
moving the folder, fixes itself the next time the app starts. The build is unsigned, so
SmartScreen may warn on first run.

A smoke test of a fresh build without touching your real settings: set `LOCALAPPDATA` to an
empty folder for that process. It still rewrites the real Run entry if Start with Windows is on
in that config, so restart your usual copy afterwards.

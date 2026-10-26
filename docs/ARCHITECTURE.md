# Architecture

A PyQt6 tray application with one background thread that reads the focused text field through
Windows UI Automation (UIA), a thread pool for HTTP calls to LanguageTool, and a set of
non-activating overlay windows.

## Threads

| Thread | Runs | Talks to the GUI via |
|---|---|---|
| Main (Qt GUI) | Tray, flyout, Settings, badge, popup, config, checker bookkeeping | — |
| `TextMonitor` (QThread) | All UIA work: polling the focused element every 300 ms, typing-pause detection, applying corrections | Qt signals (queued) |
| Qt thread pool | LanguageTool requests and connection tests (`workers.run_in_background`) | Qt signals |

UIA objects can't cross threads, and `uiautomation` sets the process DPI awareness when it is
imported, so `uia_reader` and `text_replace` are imported **inside** the monitor thread, after Qt
has created the application. Corrections are queued to the monitor (`request_replace`) for the
same reason.

## Data flow

```text
TextMonitor ──(FocusResult / FieldSnapshot)──► OverlayController ──► BadgeWidget / IssuesPopup
     │  typing pause (TypingDebouncer)                                   │ user picks a fix
     ▼                                                                    ▼
GrammarChecker ──run_in_background──► LanguageToolClient          ReplaceRequest
     │  checked(snapshot, matches) / failed(msg)                          │ queued to the monitor
     ▼                                                                    ▼
OverlayController (filters: dictionary, ignores, rules)            text_replace: verify focus,
ServerHealth (tray error state, retry)                             select range, paste via clipboard
```

`LanguageToolApp` (`app.py`) owns the components and wires their signals. Configuration is an
immutable `Config` dataclass: every change creates a new object, saves it, then
`_set_config()` pushes it to the monitor, overlay, Settings window, quick settings and
`DesktopIntegration` (theme, tray colour, autostart, hotkeys, applied only when changed).

## Module map

| Area | Modules |
|---|---|
| Entry point and wiring | `main.py`, `app.py`, `app_identity.py` (AppUserModelID for notifications) |
| Configuration | `config.py` (dataclass, validation, defaults, JSON I/O), `logging_setup.py` |
| Reading fields | `text_monitor.py` (thread, debounce, capture mode), `uia_reader.py` (UIA), `win32_edit.py` (classic Edit/RichEdit fallback), `field_filters.py` (address bars, numeric, sensitive labels), `setup_hints.py`, `text_snapshot.py` (plain data types) |
| Checking | `checker.py`, `lt_client.py` (HTTP API, UTF-16 offset mapping), `dictionary.py`, `hidden_chars.py` (local invisible-character and unusual-space matches, merged after the server answers), `health.py` (server health, outage notifications), `server_test.py` (Settings connection test) |
| Overlay | `overlay_controller.py`, `badge.py`, `overlay_widgets.py` (issues popup, Undo notice), `underlines.py` + `underline_rects.py` + `underline_overlay.py` (wavy lines under flagged words), `issue_card.py` (card at the word holding the caret), `app_names.py` (friendly app names), `non_activating.py`, `screen_coords.py` (physical → logical pixels) |
| Corrections | `replace_request.py`, `text_replace.py`, `clipboard.py` |
| Tray and quick settings | `tray.py`, `tray_flyout.py`, `quick_settings.py`, `window_corners.py` |
| Settings UI | `settings_window.py`, `settings_pages.py`, `settings_widgets.py` (category checklist, shortcut recorder, running-app picker, server status line), `ui_kit.py` (cards, switches, info bars, theme tokens), `list_editor.py`, `field_picker.py`, `welcome.py` (first-run window) |
| Desktop integration | `integration.py`, `theme.py`, `autostart.py`, `hotkeys.py` |
| Diagnostics | `diagnostics.py`, `probe.py` |
| Usage counts | `usage.py` (ledger, Windows lock, reporting points), `usage_client.py` (vendored from plugin-stats, pinned in `scripts/client_manifest.json`; never edit) |
| AI assist (Claude API, on request only) | `ai_prices.py` (models and prices), `ai_usage.py` (`ai_usage.jsonl` ledger, monthly totals, cap check), `ai_keys.py` (API key in Windows Credential Manager), `ai_client.py` (one structured-output request through the `anthropic` SDK, error kinds), `ai_service.py` (one request at a time, refusals, records cost; HTTP on the Qt thread pool), `ai_settings_page.py` + `ai_setup.py` (Settings, AI), `sentences.py` (the sentence at an offset), `ai_jobs.py` (each job's prompt, schema and answer cleaning), `ai_diff.py` (changed words in bold), `rephrase.py` (one rephrase at a time in the card; drops stale answers) |
| Update check | `update_check.py` (GitHub latest release, cached in `version_check.json`, background refresh) |
| Rename migration | `legacy.py` (moves settings and removes registry entries from the LanguageTool Desktop name) |
| Packaging | `packaging/Proofline.spec`, `packaging/build.ps1`, `packaging/make_icon.py` |

## Key decisions

**Polling instead of UIA events.** Focus and text-changed events are unreliable across apps and
can flood the client. A 300 ms poll of `GetFocusedElement` plus a debounce is simple and cheap.

**Finding the field.** A focused element counts when it is an Edit, Document or editable ComboBox
(search boxes), not a password, not read-only, and exposes TextPattern, ValuePattern, or is a
classic Win32 edit control. If focus is on an inner Text/Group/Custom/Pane element, the reader
walks up to four ancestors to find the editable one. `custom_fields` signatures bypass the type
check and the field filters.

**Caret position.** Tried in order: TextPattern2 caret range, the current selection, the Win32
system caret. The badge itself is placed by the field rectangle (outside the right edge for
single-line fields, inside the bottom-right corner otherwise), with the caret as a fallback.

**Offsets.** LanguageTool is Java and reports UTF-16 offsets; `lt_client.utf16_index_map`
converts them to Python string indices so emoji don't shift corrections.

**Safe corrections.** Before pasting, `text_replace` verifies the same field (runtime ID) and
window still have focus and the text at the offset still equals the flagged text. It selects the
range by character offset, falls back to finding the n-th occurrence, then waits up to 500 ms for
the selection to read back exactly (Chromium applies `Select()` asynchronously). Only then does
it paste. `clipboard.py` backs up every memory-based clipboard format, marks temporary content as
excluded from clipboard history, sends Ctrl+V and restores the backup.

**Non-activating overlays.** The badge and popup are frameless tool windows with
`WS_EX_NOACTIVATE`, so clicking them never takes focus from the field being corrected.
`WA_TranslucentBackground` must be set before the native window is created, or transparent areas
render black.

**Flyout corners.** The quick-settings flyout is opaque on purpose: `window_corners` asks DWM
for Windows 11 rounded corners, border and shadow, which DWM only gives non-layered windows.
On Windows 10 the request fails quietly and the corners stay square.

**Underlines.** After a check, `OverlayController` sends an `UnderlineTarget` (field id, checked text, spans) to `TextMonitor.set_underline_target`. On every poll while the field still holds that text, the monitor measures the spans with `underline_rects.measure` (on its own thread, using the element `uia_reader.last_control()` resolved in the same poll) and emits `underlines_changed` when the rectangles differ, so scrolling is followed within one poll. `clean_rects` clips to the field and drops slivers under 3 px, which Edge returns for scrolled-out text and line starts. `UnderlineOverlay` is non-activating and click-through (`make_non_activating(click_through=True)`).

**Card.** `OverlayController._update_card` runs on every caret move and every new measurement: `underlines.span_at` finds the measured word holding the snapshot's caret (not the position just after the last letter), and span i maps to `underlined_matches(matches)[i]`. The card hides while the popup is open and whenever the target changes. Its buttons reuse the popup's handlers (replace, ignore, add word, show popup).

**Pinned popup.** Dragging the popup sets `IssuesPopup.is_pinned` (reset on hide). `OverlayController._release_popup` then shows a status line (`show_status`) instead of hiding it when the field or its text changes; `_refit` leaves a pinned popup where it was dropped. Corrections stay safe because the popup lists issues only for the current snapshot.

**Popup sizing.** Rows added to a widget that is already visible stay hidden until the next
event-loop pass, and `QScrollArea` caches its content size, so `adjustSize()` alone squashed the
issues list when results changed while the popup was open. The popup shows rows as it adds
them, hides removed rows at once, and sets the list height from its contents (capped at
`POPUP_MAX_HEIGHT`).

**Packaged build.** PyInstaller one-folder, windowed. `autostart.is_frozen()` makes Start with
Windows register the exe; `DesktopIntegration` rewrites a Run entry whose command differs from
`launch_command()`. With no console, `sys.stderr` is `None`, so only the file log handler is
added.

**DPI.** UIA reports physical pixels; Qt positions windows in logical pixels scaled around each
screen's origin. `screen_coords` converts using the scale of the screen containing the point.

**Style sheets and themes.** `palette()` values in Qt style sheets are resolved once, so the
popup, Settings and flyout re-apply their style sheets when shown or when the theme changes.

**Privacy by default.** Typed text is never logged unless debug mode is on; logs and settings
live in `%LOCALAPPDATA%`; server credentials are redacted from logs and reports.

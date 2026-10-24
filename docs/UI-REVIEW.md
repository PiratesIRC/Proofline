# UI review (2026-10-24)

A review of the app's windows from the point of view of a beginner or everyday user, with the
changes it recommends. Status column: **done** means implemented and tested, **open** means not
started.

## How the review was done

- Read the UI code: `tray_flyout.py` (quick settings), `overlay_widgets.py` (issues popup),
  `badge.py`, `settings_pages.py` and `settings_window.py` (Settings), `field_picker.py`
  ("Add a text field"), `setup_hints.py`, `tray.py`.
- Rendered every window to PNG with the default config (Qt offscreen platform, Windows fonts).
- Limitation: the offscreen platform ignored the dark colour scheme, so dark-mode findings come
  from reading the code, not from looking at a render.

## Summary

The tray flyout and the Settings window are tidy and consistent with Windows 11. The weak points
for beginners: nothing appears on first launch, server setup assumes the user knows what a
LanguageTool server and a URL are, and the issues popup (the screen users see most) is styled
differently from the rest of the app and has permanent one-click actions with no undo.

## Recommendations

### 1. First-run welcome window (open)

Today the app starts silently in the tray (often inside the `^` overflow area) and the server
address must be found in Settings. Add a three-step window shown on first launch:

1. Choose a server: preset "This PC (port 8010)" or a custom address; the test runs on its own.
2. Try it: a sample box with "This are a test." so the user sees the badge and applies one fix.
3. Start with Windows, plus where to find the tray icon.

### 2. Issues popup: safer actions, consistent look (done 2026-10-24)

| Finding | Change |
|---|---|
| "Turn off in msedge.exe", "Turn off in this window" and "Turn off this rule" save permanently with one click, no confirmation or undo; the two "Turn off in…" buttons are as large as Close | Turn-off actions and Settings folded under **More options** (an inline section, not a menu window, so the text field keeps focus); add word, turn off rule, app or window show a notice with **Undo** |
| Executable names (`msedge.exe`) mean little to beginners | Friendly app name from the exe's version information ("Microsoft Edge"), with the exe name as fallback |
| "Ignore" lasts only for the session, which the label doesn't say | Renamed **Ignore for now** |
| The flagged word is shown alone ("Thsi"), struck through | Shown inside a short excerpt of its sentence, highlighted, without strike-through |
| No overview | Header with the issue count ("3 issues") |
| Own stylesheet: grey default buttons, pure-blue links, hardcoded green that ignores the accent colour; dark mode follows Qt's palette (inferred from code) | Styled through `ui_kit` tokens and the accent colour, like Settings and the flyout |
| Red flagged text `#e53935` on `#f0f0f0` is about 3.7:1, below WCAG AA 4.5:1 | New `error_text` token: `#c42b1c` on light cards, `#ff99a4` on dark (calculated, not measured with a tool) |
| (Found while doing this) the flyout's green "Connected" status was drawn in the normal text colour: `QLabel#statusOk` lost to the more specific `QWidget#uiRoot QLabel` rule | Status selectors now start with `QWidget#uiRoot` |

### 3. Server test with plain-language results (done 2026-10-24)

The connection test showed the raw exception text, and a successful test said "The test sentence
returned 1 issue(s)". It now shows one status line in three colours:

- **Green, "Ready"**: the server answered and found the error in the test sentence.
- **Orange**: the server answered but checking doesn't work. Examples: "Language not available",
  "Test sentence not corrected", "Not a LanguageTool server", "Password required", "Server error".
- **Red**: no connection. Examples: "Can't connect", "No response", "Secure connection failed",
  "Address not valid".

Save also runs the test, so a user who forgets to press Test still sees the result.

### 4. Names people can read instead of raw IDs (open)

- Turned-off rules are typed as IDs such as `MORFOLOGIK_RULE_EN_US`. Store the rule's description
  when it is turned off from the popup and show "Possible spelling mistake (MORFOLOGIK_…)".
- Categories: checkboxes with plain names instead of typing `TYPOS`.
- App lists: a "Pick from running apps" button; the custom-field placeholder
  `app.exe|ControlType|ClassName` means nothing to a beginner.
- Shortcuts are typed as text (`ctrl+alt+p`). Use a recorder field ("Press the keys you want")
  and display `Ctrl+Alt+P`.

### 5. Checking, Pause and the shortcut in the flyout (open)

"Checking: Off" and "Pause for 1 hour" look like two features doing the same thing, and the pause
tile's hint says "Ctrl+Alt+P to toggle" although that shortcut turns checking on and off, not the
one-hour pause. Use one **Checking** tile with the choices On / Pause 1 hour / Pause until
tomorrow / Off. Give "Picky mode" a subtitle such as "Extra style tips".

### 6. Fewer "can't reach the server" notifications (done 2026-10-24)

A notification appeared for every distinct error message and again after every recovery, so a
server that drops in and out, or whose error text changes (timeout, then refused), produced
repeated notifications. Now: one notification per outage whatever its error text, and at most one
per 30 minutes even if the server keeps dropping out. The tray icon and its tooltip still show the
current state. Not measured: how often it fired before, because this PC has no app log
(`%LOCALAPPDATA%\LanguageToolDesktop\logs` does not exist here).

## Smaller findings (open)

| Where | Finding | Change |
|---|---|---|
| Flyout header | The ⚙ glyph renders as a small purple colour emoji | Segoe Fluent Icons settings glyph (U+E713) |
| Flyout footer | **Quit** has a border and stands out more than **More settings**; the gear opens the same window | Plain text link for Quit |
| Field picker | Unstyled Qt; a large technical details box dominates; greyed-out buttons before any capture | `ui_kit` style, "Technical details" collapsed, only relevant buttons shown |
| Setup tips | Tray balloons with raw URLs and literal backticks; marked as seen even if missed | Show in the flyout or a small window with a clickable link |
| Advanced › About | No version, changelog or help link | Version, "What's new", Help / Troubleshooting link. Version, update status and a Releases link done 2026-10-24; help link open |
| Checking page | Spin box suffix "2 word(s)" | "2 words" with correct plural |
| General page | Server description wraps ("…sent to be / checked") | Shorter text or wider column |

## Accessibility (open)

- Badge disc is 20 px; WCAG 2.2 target size (2.5.8) asks for 24 px.
- The popup never takes focus (on purpose, so the text field keeps it), so keyboard and
  screen-reader users can't pick a suggestion. Option: a shortcut that opens the popup with
  numbered suggestions (1–9).
- The badge has no accessible name.

## What already works

- Settings save instantly and have a search box.
- "Add a text field" explains in plain words why a field is skipped.
- Badge animation respects Windows "Animation effects".
- The insecure-`http://` warning and the Debug mode warning are clear.

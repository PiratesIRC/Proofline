# Changelog

All notable changes to this project. The project has no tagged releases yet; everything below
is the current development version.

## Unreleased

### Renamed to Proofline (2026-10-24)
- The app is now **Proofline** (was LanguageTool Desktop): window titles, tray tooltip, flyout,
  notifications, packaged `Proofline.exe`, and the Python package `proofline`. The tray icon
  shows **P** instead of LT.
- On first start, settings and logs move from `%LOCALAPPDATA%\LanguageToolDesktop` to
  `%LOCALAPPDATA%\Proofline`, and the old Start with Windows entry and notification identity
  (`PiratesIRC.LanguageToolDesktop`) are removed; the new ones are written from your settings.
- Environment variables are now `PROOFLINE_LOG_LEVEL` and `PROOFLINE_LOG_TEXT`; the old
  `LT_DESKTOP_` names still work.

### UI review changes (2026-10-24)
- Settings › General: the connection test shows one coloured status line. Green **Ready** when
  the server answers and corrects the test sentence; orange when it answers but checking doesn't
  work (language not available, test sentence not corrected, not a LanguageTool server, password
  required, server error); red when there is no connection (can't connect, no response, secure
  connection failed, address not valid). **Save** also runs the test.
- Issues popup restyled with the app's theme colours and accent: header with the issue count, the
  flagged words shown highlighted inside a short excerpt of the text, suggestion buttons in the
  accent colour, **Ignore for now** (was Ignore), and the app's own name ("Microsoft Edge"
  instead of `msedge.exe`).
- **Turn off in <app>**, **Turn off in this window** and **Settings…** moved under
  **More options** in the popup.
- Add to dictionary, Turn off this rule, and turning off an app or window now show a notice with
  **Undo** in the popup.
- "Can't reach the server" notifications: one per outage (whatever the error text) and at most
  one every 30 minutes; the tray icon still shows the current state.
- Fixed: the green "Connected" status in the tray flyout was drawn in the normal text colour.
- Review and remaining recommendations: `docs/UI-REVIEW.md`.

### Settings and quick settings
- Windows 11-style Settings window: left navigation (General, Checking, Apps & fields,
  Appearance, Shortcuts, Advanced), **Find a setting** search, setting cards with toggle
  switches, expandable lists and info bars, light/dark aware with the tray colour as accent.
- Changes save immediately; the server address (Test/Save) and shortcuts (Apply) keep explicit
  buttons.
- Tray quick-settings flyout on left-click: connection status, Checking, Picky mode, Pause for
  1 hour (auto-resumes, even across a restart), Language, current-app card, More settings, Quit.
- Flyout has Windows 11 rounded corners and shadow, and sits beside a left or right taskbar.

### Checking and corrections
- Detects the focused text field in any app through UI Automation; checks after a typing pause.
- Floating badge beside the field (checking spinner, clean check mark, red issue count with a
  short pulse); high contrast on light and dark fields; respects Windows animation settings.
- Issues popup with one-click fixes, Ignore, Add to dictionary, Turn off this rule, and turning
  checking off for the app or window.
- Corrections select the text and paste via the clipboard, verifying focus, text and selection
  first; the clipboard is restored and the fix is kept out of clipboard history.
- Personal dictionary, turned-off rules and categories, Picky mode, minimum words to check.
- Global shortcuts: `Ctrl+Alt+P` pause/resume, `Ctrl+Alt+L` check now.

### Reaching more fields
- Browser search boxes (editable combo boxes), rich web editors (focus on an inner element),
  classic Win32 Edit/RichEdit fallback.
- **Add a text field…** helper explains why a field is or isn't checked and can always check a
  field (`custom_fields`) or an app (`always_check_apps`).
- One-time setup tips for Google Docs, Java apps and Firefox older than 143.
- Clear message for apps running as administrator.

### Privacy and safety
- Skips password fields, read-only fields, address bars, numeric fields and fields labelled as
  sensitive (one-time codes, card numbers, SSN, PIN, API keys, tokens).
- Recommended default exclusions for password managers, terminals, remote desktops, code and
  spreadsheet editors, and sign-in windows.
- Typed text is kept out of logs unless Debug mode is on; server credentials are redacted.
- Warning and confirmation for plain `http://` servers on another computer.
- Settings and logs stored in `%LOCALAPPDATA%\LanguageToolDesktop`.

### Reliability and diagnostics
- Server health check at startup with a red tray **!** and automatic retry every minute.
- Diagnostic report, debug mode, log folder and clear-logs actions; `lt_desktop.probe` tool.
- Notifications show "LanguageTool Desktop" (AppUserModelID) instead of "Python".
- Single-instance lock, Start with Windows, theme (follow Windows / light / dark), tray colour.
- Default server address is `http://127.0.0.1:8010/v2/check` instead of `localhost`, which made
  Windows try IPv6 first and added about 2 seconds to every check against an IPv4-only server.
  A setting already saved with `localhost` is left as it is.
- Settings › Advanced has a **Powered by LanguageTool** card with a link to languagetool.org and
  a note that this app is independent of LanguageTooler GmbH; the README says the same and no
  longer suggests the public API for everyday use (its terms ask for no automated requests).

### Packaging
- `packaging\build.ps1` makes a one-folder build and zip with PyInstaller: no Python needed,
  own icon and version info, Start with Windows points at the exe and fixes a stale entry.

### Fixes along the way
- LanguageTool offsets are UTF-16; emoji no longer shift corrections.
- Corrections in Edge/Chrome/WebView2 wait for Chromium's asynchronous selection.
- Badge and popup corners render transparent; popup colours follow runtime theme changes.
- Badge for single-line fields sits outside the field so site icons stay visible.
- Settings window fits 1080p screens.
- Issues popup resizes when results change while it is open (it used to squash the list).

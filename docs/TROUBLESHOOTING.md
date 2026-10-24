# Troubleshooting

## A text box isn't being checked

1. Open **Add a text field…** (tray right-click menu, the quick-settings **Current app** card, or
   **Settings › Apps & fields**) and click into the text box. It reports one of:

   | Result | What to do |
   |---|---|
   | Already checked | Nothing; type a sentence and pause. Very short text (below **Minimum words**) isn't checked until you press `Ctrl+Alt+L`. |
   | Turned off here | An exclusion matches. Click **Always check this app**, or remove the entry under **Apps & fields**. |
   | Skipped by a rule | The control isn't recognised as a text box, or a filter (address bar, numeric, sensitive label) skipped it, but its text is readable. Click **Always check this field**. |
   | Text isn't available | The app doesn't share the text with other programs. See the app notes below. |
   | Can't read this app | The app runs as administrator; see below. |
   | Password field | Never checked, by design. |

2. Check that checking isn't paused (grey tray icon) and the server is reachable (no red **!**).
3. For a detailed trace, run the probe and click into the field:

   ```powershell
   .\.venv\Scripts\python.exe -m proofline.probe 60
   ```

   It prints the app, control type, class, the text access method (`Text`, `Value`,
   `Win32 messages`), the caret position and why a field is skipped. **Copy details** in the
   Add-a-text-field window gives the same information without field contents.

## App-specific notes

| App | Notes |
|---|---|
| Edge, Chrome, Vivaldi, WebView2 apps (new Outlook, Teams) | Supported. Search boxes with suggestion lists are supported. The first read after switching tabs can take a moment while the browser builds its accessibility tree. |
| Google Docs / Sheets / Slides | Text is drawn on a canvas. Turn on screen reader support in the document (`Ctrl+Alt+Z`, or Tools › Accessibility). The app shows this tip once. |
| Firefox | UI Automation support arrived in Firefox 143; update older versions. |
| Java (Swing/AWT) apps | Enable the Java Access Bridge: run `jabswitch -enable`, then restart the app. |
| Notepad, WordPad-style and classic Win32 boxes | Supported, including a fallback for edit boxes that only answer classic window messages. |
| Microsoft Word / classic Outlook | Usually supported; very large documents are read up to 20,000 characters. |
| Remote Desktop, Citrix, VMs | Text lives on the remote machine and can't be read. Excluded by default. |
| Terminals, code editors, Excel | Excluded by default (not prose). Remove them from **Apps** to try. |
| Apps run as administrator | Windows blocks normal apps from reading them. Run Proofline as administrator too, or accept that they are skipped. |

## The server

- **Red ! on the tray icon / "Could not connect":** check the address in Settings › General and
  click **Test**. The app retries every minute and clears the error by itself once the server
  answers. It notifies once per outage, at most every 30 minutes.
- **Test results in Settings:** red (**Can't connect**, **No response**, **Secure connection
  failed**, **Address not valid**) means no connection; orange (**Language not available**,
  **Test sentence not corrected**, **Not a LanguageTool server**, **Password required**, **Server
  error**) means the server answered but checking doesn't work; green **Ready** means it works.
- **"No response within 10 seconds":** the server is overloaded or the text is very long.
- **HTTP 413 / 429 from the public API:** the public API's size or rate limit was hit; use a
  self-hosted server.
- **Yellow "Unencrypted connection" bar:** the server uses `http://` on another computer, so text
  travels unencrypted. Use `https://` if the server supports it.

## Applying a correction fails

A tray notification explains why nothing was changed. The app refuses to paste unless the same
field still has focus, the text hasn't changed since it was checked, and the flagged text is
exactly what got selected.

- "The text has changed since it was checked": wait for the badge to turn red again, then retry.
- "Could not select the flagged text": the app didn't accept a programmatic selection. Browsers
  apply selections asynchronously; the app waits up to 500 ms. If it keeps failing, report it
  with the diagnostic report.
- "This app does not let other programs select text": the field offers text for reading only.
- "The clipboard is busy": another program held the clipboard; retry.

## The badge or popup

- **Badge covers part of the field:** for single-line fields it sits just outside the right edge;
  if the field touches the screen edge it moves inside. Turn off **Show the badge in every text
  field** to show it only when there are issues.
- **No animation:** the badge follows Windows' *Animation effects* setting (Settings ›
  Accessibility › Visual effects).

## Logs and diagnostic reports

- **Settings › Advanced › Copy diagnostic report** copies Windows/Python/Qt versions, your
  settings (server credentials redacted) and the last 200 log lines. Paste it into your issue.
- **Debug mode** adds short samples of typed text to the log, which helps with app-specific
  problems. Turn it off and **Clear logs** afterwards.
- Logs: `%LOCALAPPDATA%\Proofline\logs\app.log`. Useful lines:
  - `Focus: <app> <ControlType> … -> <reason>`: what was detected and why it was or wasn't used
  - `Typing paused in …` / `N issue(s) in … ms`: a check and its result
  - `Correction not applied: …`: why a fix was refused

## Starting and stopping

- **"Already running":** another copy is in the tray. Quit it from its menu.
- **Doesn't start at sign-in:** check **Settings › General › Start when I sign in to Windows**.
  The startup entry points at `Proofline.exe` (packaged build) or
  `.venv\Scripts\pythonw.exe main.py` (source); if you moved the folder, start the app once by
  hand and it updates the entry.
- **Checking stays off after a restart:** a 1-hour pause carries over a restart and ends on
  time, but turning checking off from the menu or `Ctrl+Alt+P` lasts until you turn it back on.

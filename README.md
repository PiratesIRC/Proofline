# Proofline

A system-wide grammar and spelling checker for Windows, in the spirit of the Grammarly and
LanguageTool desktop apps. It runs in the system tray, watches the text box you are typing in
(in almost any app), checks the text with a [LanguageTool](https://languagetool.org) server you
choose, and lets you fix issues with one click.

Proofline is an independent project. It is not made by, endorsed by or affiliated with
LanguageTooler GmbH, the company behind [LanguageTool](https://languagetool.org). The
LanguageTool server it talks to is open source (LGPL 2.1).

- Works across apps through Windows UI Automation: browsers (Edge, Chrome, Vivaldi), new Outlook
  and Teams, Notepad, Office, and most standard Windows text boxes.
- A small badge appears beside the text box: it spins while checking, turns green when the text
  is clean, and shows a red issue count when something needs attention.
- Click the badge for suggestions; click a suggestion to apply it. Your clipboard is restored
  afterwards.
- Your own server: point it at a self-hosted LanguageTool server so text stays on your network.

## Requirements

- Windows 10 or 11
- Python 3.13 to run from source (3.14 also works; 3.13 is what the project is tested on).
  The packaged build needs no Python.
- A LanguageTool server reachable over HTTP(S), normally one you run yourself (see
  [Server](#server))

## Install and run

**Packaged build:** unzip `Proofline-<version>.zip` somewhere permanent (for example
`%LOCALAPPDATA%\Programs`) and run `Proofline\Proofline.exe`. Coming from LanguageTool
Desktop (the app's earlier name)? Quit it first; Proofline moves its settings over on first start.
To update,
quit the app, replace the folder and start it again; settings live in `%LOCALAPPDATA%` and are
kept.

**From source:**

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py        # with a console window (logs visible)
.\.venv\Scripts\pythonw.exe main.py       # without a console window
```

A round **P** icon appears in the system tray (check the `^` overflow area). Only one copy runs at a
time; starting a second one shows a message and exits.

### First-time setup

1. Left-click the tray icon, then **More settings** (or right-click › **Settings…**).
2. On **General**, enter your server address, e.g. `https://languagetool.example.org` or
   `http://127.0.0.1:8010`. `/v2/check` is added automatically. Prefer `127.0.0.1` to
   `localhost`: Windows tries IPv6 first, which can add about 2 seconds to every check.
3. Click **Test**, then **Save** (Save also tests). A green **Ready** means checking works; orange
   means the server answered but something is wrong (for example the language isn't available);
   red means there is no connection. Each comes with a one-line explanation.
4. Optionally turn on **Start when I sign in to Windows**.

If the server can't be reached, the tray icon shows a red **!** with the reason in its tooltip,
and the app retries every minute. A notification appears once per outage, at most every 30
minutes.

## Using it

| You see | Meaning |
|---|---|
| Grey badge with a spinning arc | Checking (or waiting for you to pause typing) |
| Green badge with a check mark | No issues found |
| Red badge with a number | That many issues; it pulses briefly to get your attention |
| Brown badge with **!** | The server couldn't be reached; hover for details |

Click the badge to open the issues popup:

- Each issue shows the flagged words highlighted in their sentence. Click a suggestion button to
  replace them.
- **Ignore for now** hides that issue for this session; **Add to dictionary** (spelling only) stops
  a word being flagged; **Turn off this rule** disables a LanguageTool rule.
- **More options** › **Turn off in <app>** / **Turn off in this window** stop checking there.
- Adding a word or turning something off shows a notice with **Undo**.

### Tray quick settings

Left-click the tray icon for quick settings: connection status, **Checking** on/off,
**Picky mode**, **Pause for 1 hour** (it ends on time even if the app restarts in between),
**Language**, and a **Current app** card to turn checking off (or back on) for the app you were
just using. Right-click the icon for the classic menu.

### Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Alt+P` | Pause or resume checking |
| `Ctrl+Alt+L` | Check the current text box now (ignores the typing pause and minimum length) |

Change them in **Settings › Shortcuts**.

### When a text box isn't checked

Use **Add a text field…** (tray menu, quick settings, or **Settings › Apps & fields**) and click
into the text box. The helper explains whether and why it is skipped and, where possible, offers
**Always check this field** or **Always check this app**. See
[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for app-specific notes.

## Settings

Settings save as soon as you change them, except the server address (**Save**) and shortcuts
(**Apply**). Use **Find a setting** at the top left to search.

| Section | What's there |
|---|---|
| General | Server address (Test / Save), language, start with Windows |
| Checking | Typing pause, minimum words, Picky mode, personal dictionary, turned-off rules and categories |
| Apps & fields | Add a text field, apps and window titles to skip, apps to always check, custom fields |
| Appearance | Theme (follow Windows / light / dark), accent and tray colour, badge visibility |
| Shortcuts | Global shortcuts |
| Advanced | Debug mode, copy a diagnostic report, open or clear logs, link to languagetool.org |

All options and their `config.json` names are listed in
[docs/CONFIGURATION.md](docs/CONFIGURATION.md).

## Server

The app talks to LanguageTool's HTTP API (`POST /v2/check`).

- **Self-hosted (recommended for organisations):** run the LanguageTool server on your network,
  e.g. `java -cp languagetool-server.jar org.languagetool.server.HTTPServer --port 8081`.
  See <https://dev.languagetool.org/http-server>.
- **Public API: not supported for everyday use.** LanguageTool's free public API
  (`https://api.languagetool.org/v2/check`) asks clients not to send automated requests. This app
  sends a check automatically after every typing pause, so using the public API with it goes
  against those terms, even within the rate limits (20 requests and 75 KB per minute, 20 KB per
  request). It would also send everything you type in checked fields to a third party. At most,
  point the app at it briefly to try the app out, then switch to your own server. See
  <https://dev.languagetool.org/public-http-api> and <https://languagetool.org/legal/terms>.

## Privacy and security

- Text is sent only to the server you configure. A yellow warning appears in Settings, and you are
  asked to confirm, if the address is plain `http://` to another computer.
- Password fields are never read. By default the app also skips password managers, terminals,
  remote desktop and VM windows, code and spreadsheet editors, browser address bars, numeric
  fields, fields labelled like one-time codes, card numbers, SSNs, PINs, API keys or tokens, and
  windows whose title contains *Password*, *Sign in*, *Log in*, *Login* or *Windows Security*.
- Logs never contain what you type unless you turn on **Debug mode** (Settings › Advanced) or set
  `PROOFLINE_LOG_TEXT=1`. Window titles are logged.
- Corrections use the clipboard briefly; your clipboard contents are restored and the correction
  is kept out of Windows clipboard history (Win+V).
- Settings and logs live in `%LOCALAPPDATA%\Proofline`, outside OneDrive.

## Development

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check proofline main.py tests
.\packaging\build.ps1      # packaged build + zip in dist\ (needs requirements-build.txt)
```

Live-server tests run when `LT_TEST_SERVER_URL` is set. See
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Documentation

- [docs/CONFIGURATION.md](docs/CONFIGURATION.md): every setting, file location and environment variable
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md): fields not detected, app-specific notes, logs
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): how it works
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md): setup, tests and conventions for contributors
- [CHANGELOG.md](CHANGELOG.md): what changed

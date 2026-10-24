<div align="center">

<img src="docs/images/logo.png" width="96" alt="Proofline logo">

# Proofline

**Grammar and spelling checking in every Windows app, against a LanguageTool server you control.**

[![Latest release](https://img.shields.io/github/v/release/PiratesIRC/Proofline?label=release&color=2e7d32)](https://github.com/PiratesIRC/Proofline/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/PiratesIRC/Proofline/total?color=2e7d32)](https://github.com/PiratesIRC/Proofline/releases)
[![Windows 10 | 11](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4?logo=windows&logoColor=white)](#requirements)
[![Python 3.13](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](#from-source)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue)](LICENSE)
[![Sponsor](https://img.shields.io/badge/Sponsor-%E2%9D%A4-db61a2?logo=githubsponsors&logoColor=white)](https://github.com/sponsors/PiratesIRC)
[![Corrections Applied](https://img.shields.io/endpoint?url=https://plugin-stats.dpas.workers.dev/badge/proofline/corrections_applied)](#anonymous-usage-counts)
[![Active Installs](https://img.shields.io/endpoint?url=https://plugin-stats.dpas.workers.dev/badge/proofline/installs)](#anonymous-usage-counts)

[Download](https://github.com/PiratesIRC/Proofline/releases/latest) ·
[Features](#features) ·
[Requirements](#requirements) ·
[Install](#install) ·
[Privacy](#privacy-and-security) ·
[Docs](#documentation) ·
[License](#license)

<img src="docs/images/hero.png" width="860" alt="A text editor with three mistakes underlined, the red Proofline badge in its corner, and the issues popup listing suggestions">

</div>

Proofline runs in the system tray and watches the text box you are typing in, in almost any app.
When you pause, it checks the text with a [LanguageTool](https://languagetool.org) server you
choose and shows a small badge beside the field. Click the badge, click a suggestion, done.

> [!NOTE]
> Proofline is an independent project. It is not made by, endorsed by or affiliated with
> LanguageTooler GmbH, the company behind [LanguageTool](https://languagetool.org). The
> LanguageTool server it talks to is open source (LGPL 2.1).

## Features

- **Works across apps** through Windows UI Automation: browsers (Edge, Chrome, Vivaldi), new
  Outlook and Teams, Notepad, Office, and most standard Windows text boxes.
- **One badge, one click.** The badge spins while checking, turns green when the text is clean,
  and shows a red issue count when something needs attention. Click a suggestion to fix the text;
  your clipboard is restored afterwards.
- **Readable suggestions.** Each issue shows the flagged words inside their sentence, with
  Ignore for now, Add to dictionary, Turn off this rule, and Undo for anything permanent.
- **Your own server.** Point it at a self-hosted LanguageTool server so your text stays on your
  network. The connection test says in plain words whether checking works (green), the server
  answered but something is wrong (orange), or there is no connection (red).
- **Keyboard friendly.** `Ctrl+Alt+J` applies the first suggestion, `Ctrl+Alt+L` checks now,
  `Ctrl+Alt+P` turns checking on or off. Record your own combinations in Settings.
- **Light and dark**, following Windows or your choice, with your accent colour.
- **Installer or portable**, no administrator rights needed for either.

<table>
  <tr>
    <td align="center"><img src="docs/images/popup-light.png" width="300" alt="Issues popup, light theme"><br><sub>Issues popup</sub></td>
    <td align="center"><img src="docs/images/popup-dark.png" width="300" alt="Issues popup, dark theme"><br><sub>Dark theme</sub></td>
    <td align="center"><img src="docs/images/flyout-light.png" width="300" alt="Tray quick settings"><br><sub>Tray quick settings</sub></td>
  </tr>
  <tr>
    <td align="center" colspan="2"><img src="docs/images/settings-general-light.png" width="600" alt="Settings, General page with the server status Ready"><br><sub>Settings: server test</sub></td>
    <td align="center"><img src="docs/images/welcome.png" width="300" alt="First-run welcome window"><br><sub>First-run welcome</sub></td>
  </tr>
</table>

## Requirements

| | |
|---|---|
| **Windows** | Windows 10 version 1809 or later, or Windows 11, 64-bit |
| **Disk space** | About 100 MB (the installed app measured 94 MB) |
| **Administrator rights** | Not needed: the installer installs for your account only, the portable copy runs from any folder |
| **A LanguageTool server** | One you can reach over HTTP or HTTPS: on the same PC ([one Docker command](#need-a-languagetool-server), or the LanguageTool server `.jar` with Java 17 or newer) or on your network. See [Server](#server) |
| **Network** | Your LanguageTool server. Optional: GitHub, for the daily update check, and plugin-stats.dpas.workers.dev, for the [anonymous usage counts](#anonymous-usage-counts). Both can be turned off |
| **From source** | Python 3.13, 64-bit (3.14 also works; 3.13 is what the project is tested on), plus `requirements.txt` |

Apps that run as administrator can only be checked when Proofline also runs as administrator,
because Windows blocks normal apps from reading them.

## Install

Download one of these from [Releases](https://github.com/PiratesIRC/Proofline/releases/latest):

| File | What it is |
|---|---|
| `Proofline-<version>-setup.exe` | **Installer.** Installs for your account into `%LOCALAPPDATA%\Programs\Proofline`, adds a Start menu shortcut, and can be removed from Windows Settings › Apps. Settings live in `%LOCALAPPDATA%\Proofline` and survive updates and uninstalling. |
| `Proofline-<version>-portable.zip` | **Portable.** Unzip anywhere, including a USB stick, and run `Proofline\Proofline.exe`. Settings, logs and usage files stay in a `data` folder next to the exe. Delete `portable.txt` to make the copy use `%LOCALAPPDATA%\Proofline` instead. |

> [!TIP]
> The exe is not code-signed, so Windows SmartScreen may say it is unrecognised. Choose
> **More info** › **Run anyway** if you trust the download.

To update, run the new installer (it replaces the old version), or quit the portable copy and
replace its folder, keeping `data`. A portable copy that has no settings of its own yet copies
them once from `%LOCALAPPDATA%\Proofline` (an installed copy or 0.1.0), so unzipping the portable
version over an older install keeps your settings. Settings › Advanced shows when a newer release is available,
and **Check now** looks straight away.

Coming from LanguageTool Desktop, the app's earlier name? Quit it first; Proofline moves its
settings over on first start.

### Need a LanguageTool server?

With [Docker](https://www.docker.com/products/docker-desktop/) installed, one command starts a
server on this PC that only this PC can reach:

```powershell
docker run -d --name languagetool --restart unless-stopped -p 127.0.0.1:8010:8010 erikvl87/languagetool
```

Then choose **This PC** in the welcome window (the default address
`http://127.0.0.1:8010/v2/check`). The first start downloads about 450 MB and takes a minute.
To serve other PCs on your network, put it behind HTTPS (see [Server](#server)).

### From source

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py        # with a console window (logs visible)
.\.venv\Scripts\pythonw.exe main.py       # without a console window
```

### First start

A round **P** icon appears in the system tray (check the `^` overflow area). Only one copy runs
at a time. On a fresh install a short welcome window helps you pick a server, explains the badge,
and offers **Start with Windows**.

To set the server later, left-click the tray icon, choose **More settings**, and on **General**:

1. Enter your server address, e.g. `https://languagetool.example.org` or `http://127.0.0.1:8010`.
   `/v2/check` is added automatically. Prefer `127.0.0.1` to `localhost`: Windows tries IPv6
   first, which can add about 2 seconds to every check. A server that needs a login takes it in
   the address: `https://user:password@host`.
2. Click **Save**. It also tests the connection: green **Ready** means checking works.

If the server can't be reached, the tray icon shows a red **!** with the reason in its tooltip,
and the app retries every minute. A notification appears once per outage, at most every 30
minutes.

## Using it

<img src="docs/images/badge-states.png" width="520" alt="The four badge states: checking, no issues, 3 issues, server problem">

| You see | Meaning |
|---|---|
| Grey badge with a spinning arc | Checking (or waiting for you to pause typing) |
| Green badge with a check mark | No issues found |
| Red badge with a number | That many issues; it pulses briefly to get your attention |
| Brown badge with **!** | The server couldn't be reached; hover for details |

Click the badge to open the issues popup:

- Each issue shows the flagged words highlighted in their sentence. Click a suggestion button to
  replace them.
- **Ignore for now** hides that issue for this session; **Add to dictionary** (spelling only)
  stops a word being flagged; **Turn off this rule** disables a LanguageTool rule.
- **More options** › **Turn off in <app>** / **Turn off in this window** stop checking there.
- Adding a word or turning something off shows a notice with **Undo**.

### Tray quick settings

Left-click the tray icon for quick settings: connection status, **Checking** (On, Pause for 1
hour, Pause for the rest of today, Off; a pause ends on time even if the app restarts in between),
**Picky mode** (extra style tips), **Language**, and a **Current app** card to turn checking off,
or back on, for the app you were last typing in. Right-click the icon for the classic menu.

### Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Alt+P` | Turn checking on or off |
| `Ctrl+Alt+L` | Check the current text box now (ignores the typing pause and minimum length) |
| `Ctrl+Alt+J` | Apply the first suggestion for the current text box |

Change them in **Settings › Shortcuts**: click a box and press the keys.

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
| Checking | Typing pause, minimum words, Picky mode, personal dictionary, turned-off rules (by name) and categories (checkboxes) |
| Apps & fields | Add a text field, apps (pick a running app) and window titles to skip, apps to always check, custom fields |
| Appearance | Theme (follow Windows / light / dark), accent and tray colour, badge visibility |
| Shortcuts | Three global shortcuts, recorded by pressing the keys |
| Advanced | Debug mode, diagnostic report and logs, check for updates (with Check now), share anonymous usage counts, version, Help and Releases links |

All options and their `config.json` names are listed in
[docs/CONFIGURATION.md](docs/CONFIGURATION.md).

## Server

The app talks to LanguageTool's HTTP API (`POST /v2/check`).

- **Self-hosted (recommended):** run the LanguageTool server on this PC or your network, for
  example with Docker ([the one-line command above](#need-a-languagetool-server), image
  [`erikvl87/languagetool`](https://hub.docker.com/r/erikvl87/languagetool)) or
  `java -cp languagetool-server.jar org.languagetool.server.HTTPServer --port 8081`.
  See <https://dev.languagetool.org/http-server>.
- **Other PCs on your network:** publish the server through a reverse proxy with HTTPS (for
  example Caddy or nginx) and, if it is reachable by others, a login; then use
  `https://user:password@your-host/v2/check` in Proofline. Plain `http://` to another computer
  sends your text unencrypted, and Proofline warns before using it.

> [!WARNING]
> **The public API is not supported for everyday use.** LanguageTool's free public API
> (`https://api.languagetool.org/v2/check`) asks clients not to send automated requests. This app
> sends a check automatically after every typing pause, so using the public API with it goes
> against those terms, even within the rate limits (20 requests and 75 KB per minute, 20 KB per
> request). It would also send everything you type in checked fields to a third party. At most,
> point the app at it briefly to try the app out, then switch to your own server. See
> <https://dev.languagetool.org/public-http-api> and <https://languagetool.org/legal/terms>.

## Privacy and security

- Text is sent only to the server you configure. A yellow warning appears, and you are asked to
  confirm, if the address is plain `http://` to another computer.
- Password fields are never read. By default the app also skips password managers, terminals,
  remote desktop and VM windows, code and spreadsheet editors, browser address bars, numeric
  fields, fields labelled like one-time codes, card numbers, SSNs, PINs, API keys or tokens, and
  windows whose title contains *Password*, *Sign in*, *Log in*, *Login* or *Windows Security*.
- Logs never contain what you type unless you turn on **Debug mode** (Settings › Advanced) or set
  `PROOFLINE_LOG_TEXT=1`. Window titles are logged.
- Corrections use the clipboard briefly; your clipboard contents are restored and the correction
  is kept out of Windows clipboard history (Win+V).
- Settings and logs live in `%LOCALAPPDATA%\Proofline` (outside OneDrive), or in the portable
  copy's `data` folder.
- Anonymous usage counts: the app sends the number of corrections you applied and a random id
  to the author's counter, at most once an hour, for the badges above. No text is sent. Details
  and how to turn it off: [Anonymous usage counts](#anonymous-usage-counts).
- Update check: about once a day the app asks GitHub (api.github.com) for the latest Proofline
  release. The request contains no text you typed. Turn it off in **Settings › Advanced › Check
  for updates**.

## Anonymous usage counts

The Corrections Applied and Active Installs badges count every install that leaves the "Share
anonymous usage counts" setting (on by default, Settings › Advanced) ticked. Corrections Applied
counts the suggestions you applied from the issues popup or with `Ctrl+Alt+J`, after the app
verified the text box and pasted the fix. Checks, ignored issues and corrections the app refused
(for example because the text changed) count nothing. The same word fixed twice counts twice, so
the figure measures fixes made, not distinct words.

While the app runs, it sends its Corrections Applied total and a random id for this install to the
author's counter at plugin-stats.dpas.workers.dev: when it starts, then on an hourly timer, and right
after a correction. It sends at most once an hour, or ten minutes after the last successful send
when a correction has just been applied.

The server stores that id with the total and the date of the last report, and keeps them until this
install unticks the setting and the delete succeeds, or until the author removes them by hand. An
install that stops reporting still counts toward Corrections Applied. The connection shows the
server your public IP address; the server uses it only to limit abuse and does not store it in its
database, though when an install first registers it keeps a salted one-way hash of it (of its /64
block for IPv6) for up to three days. Cloudflare, which hosts the server, keeps its own request
logs. No text you typed, app names, window titles, server addresses or settings are sent. The
figures are self-reported by installs and capped by the server, not verified.

What counts as an active install: an install that sent at least one report in the last 30 UTC days.
A badge changes after the server's hourly recount, which runs at the start of each UTC hour, and
Shields may cache the badge for up to an hour more, so a new report can take up to about two hours
to show.

Unticking the setting makes the app ask the server, straight away, to delete this install's figures.
Once the server confirms the delete, the app forgets its id, and ticking the setting again later
starts a new one; if the delete could not reach the server, the app keeps the id and retries. The
app keeps one line per applied correction (a count and a time, nothing else) in
`usage_counts.jsonl`, and its id and the timing of its reports in `usage\proofline\`
(`install_id`, `sent`, `backoff`, `disabled`, `delete_backoff`, `lock`), both in the settings
folder. To start a new id, untick the setting so the server deletes this install's figures;
deleting that folder while the setting is ticked, or before the server confirms the delete, leaves
the old figures on the server, and the new id then sends the full total again, so the badge counts
it twice.

## Development

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check proofline main.py tests
powershell -File packaging\build.ps1           # dist\: portable zip and installer
.\.venv\Scripts\python.exe scripts\make_screenshots.py   # README images in docs\images\
```

The build needs `requirements-build.txt` (PyInstaller) and Inno Setup 6 for the installer
(`winget install --id JRSoftware.InnoSetup -e --scope user`, or pass `-SkipInstaller`).
Live-server tests run when `LT_TEST_SERVER_URL` is set. See
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Documentation

- [docs/CONFIGURATION.md](docs/CONFIGURATION.md): every setting, file location and environment variable
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md): fields not detected, app-specific notes, logs
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): how it works
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md): setup, tests and conventions for contributors
- [docs/UI-REVIEW.md](docs/UI-REVIEW.md): the UI review behind the 0.2.0 changes
- [CHANGELOG.md](CHANGELOG.md): what changed

## Sponsor

This app is free and always will be. If it saves you time and you would like to support the work,
you can sponsor it at [github.com/sponsors/PiratesIRC](https://github.com/sponsors/PiratesIRC).

Sponsoring buys no priority, no private support and no influence over what gets built. Bug
reports and pull requests are just as welcome from everyone.

## Disclaimer

- Proofline is an independent project. It is not made by, endorsed by or affiliated with
  LanguageTooler GmbH. "LanguageTool" is a trademark of LanguageTooler GmbH; Proofline uses the
  name only to say which server software it works with.
- Proofline does not include a LanguageTool server. If you point it at one of LanguageTool's
  hosted services (the free public API or a paid plan), that use is governed by
  [LanguageTool's terms](https://languagetool.org/legal/terms), and the public API asks clients not
  to send automated requests, which is how Proofline works (see [Server](#server)). Proofline is
  meant for a server you run yourself.
- Proofline is provided as is, without any warranty (sections 15 and 16 of the
  [license](LICENSE)). A grammar checker can miss mistakes and can suggest wrong ones; check
  important text yourself.

## License

Copyright (C) 2026 PiratesIRC.

Proofline is free software: you can redistribute it and/or modify it under the terms of the
[GNU General Public License version 3](LICENSE) as published by the Free Software Foundation.

The release builds include third-party libraries under their own licenses: PyQt6 (GPL-3.0),
Qt 6 (LGPL-3.0), uiautomation (Apache-2.0), comtypes (MIT), requests (Apache-2.0), pywin32 (PSF),
urllib3 (MIT), certifi (MPL-2.0), charset-normalizer (MIT) and idna (BSD-3-Clause). The
LanguageTool server Proofline talks to is a separate program under the LGPL-2.1.

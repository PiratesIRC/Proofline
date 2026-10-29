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
[![AI Rephrases](https://img.shields.io/endpoint?url=https://plugin-stats.dpas.workers.dev/badge/proofline-ai/ai_rephrases)](#anonymous-usage-counts)
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
- **Underlines and a card.** Flagged words get a wavy red line in apps that tell other programs
  where each word is on screen (tested in Edge and Notepad). With the caret inside a flagged
  word, a card opens under it with the suggestions.
- **Your own server.** Point it at a self-hosted LanguageTool server so your text stays on your
  network. The connection test says in plain words whether checking works (green), the server
  answered but something is wrong (orange), or there is no connection (red).
- **Keyboard friendly.** `Ctrl+Alt+J` applies the first suggestion, `Ctrl+Alt+L` checks now,
  `Ctrl+Alt+P` turns checking on or off. Record your own combinations in Settings.
- **Optional AI suggestions.** Off by default. They use your own API key for a provider you
  choose, or a local Ollama server with no key and no cost. **AI Rephrase** in the card under an
  underlined word rewrites one sentence, with the changed words in bold, and only that sentence
  is sent. **Find more issues** in the issues popup asks the AI for problems LanguageTool missed
  in the whole text box; **Rewrite for clarity** and **Change tone** list the AI's edits as
  separate changes you accept one at a time or all at once. A monthly spending limit stops cloud AI requests when the next one could
  take the month past it. See [AI suggestions](#ai-suggestions-optional).
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
| Grey badge with a spinning arc | Checking (or waiting for you to pause typing). It appears once the box holds enough words to check, so an empty search box or chat input shows no badge |
| Green badge with a check mark | No issues found |
| Red badge with a number | That many issues; it pulses briefly to get your attention |
| Brown badge with **!** | The server couldn't be reached; hover for details |

Flagged words also get a wavy red line under them, in apps that tell other programs where
each word is on screen (measured in Edge and Notepad). The lines move with the text when you
scroll, disappear while you type, and come back after the next check. Turn them off in
Settings › Appearance › **Underline issues in the text**.

Put the caret inside an underlined word (click it, or move there with the arrow keys) and a
small card opens under it with the suggestions, **Ignore**, **Add to dictionary** for spelling,
and **All issues…** for the full popup. Click a suggestion to apply it. The card closes when
the caret leaves the word.

Click the badge to open the issues popup:

- Each issue shows the flagged words highlighted in their sentence. Click a suggestion button to
  replace them.
- **Ignore for now** hides that issue for this session; **Add to dictionary** (spelling only)
  stops a word being flagged; **Turn off this rule** disables a LanguageTool rule.
- **More options** › **Turn off in <app>** / **Turn off in this window** stop checking there.
- Adding a word or turning something off shows a notice with **Undo**.
- Proofline also flags characters you can't see: a zero-width space or soft hyphen inside a word,
  text-direction controls, and unusual spaces such as a thin or em space. Placeholder characters
  that chat and document editors add themselves are left alone. The popup shows
  them as their code (`[U+200B]`) with a **(remove)** or **(normal space)** button. Turn this off
  in Settings › Checking › **Flag hidden characters**.
- Drag the popup by its heading to move it, for example out from under the Start menu. A moved popup stays open until you click **✕**: it follows the text box you type in and shows the new results after each check.

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

### AI suggestions (optional)

Proofline can ask an AI model to reword a sentence or to find problems LanguageTool missed. It
is off until you turn it on, it works with the provider you choose, and it sends text only when
you click or press its shortcut. The default provider is Claude, Anthropic's AI model.

1. Choose a provider in **Settings › AI**. Each provider needs your own API key from its website
   (paste it, click **Save**, then **Test**), or, for Ollama and Other, a server address.
   The key is kept in Windows Credential Manager, not in the settings file.
2. Turn on **Use AI suggestions**.
3. Choose a model. The cloud providers have a short built-in list, cheapest first, and the
   default is the cheapest; Ollama, Other and OpenRouter list the models their server offers.
   Choose **Other model...** at the end of any list to type a name instead.
4. For cloud providers, set the **Monthly spending limit** (default $1.00). One limit covers all
   cloud providers together.

| Provider | What you need | Notes |
|---|---|---|
| Claude (Anthropic) | API key from [console.anthropic.com](https://console.anthropic.com/) | Tested with a real account. Privacy: [privacy page](https://privacy.anthropic.com/). |
| OpenAI | API key from [platform.openai.com](https://platform.openai.com/) | (untested). Your text goes to OpenAI. Privacy: [API data guide](https://developers.openai.com/api/docs/guides/your-data). |
| Gemini (Google) | API key from [aistudio.google.com](https://aistudio.google.com/) | (untested). With a free key, Google may use your text to improve its products and people may read it. Paid keys are covered by different terms. Privacy: [Gemini API terms](https://ai.google.dev/gemini-api/terms). |
| Grok (xAI) | API key from [console.x.ai](https://console.x.ai/) | (untested). Your text goes to xAI. Privacy: [security and data FAQ](https://docs.x.ai/developers/faq/security). |
| Mistral | API key from [console.mistral.ai](https://console.mistral.ai/) | (untested). Mistral may use API data from free accounts for training; check the privacy settings in the Mistral console. Privacy: [opt-out article](https://help.mistral.ai/en/articles/455207-can-i-opt-out-of-my-input-or-output-data-being-used-for-training). |
| DeepSeek | API key from [platform.deepseek.com](https://platform.deepseek.com/) | (untested). DeepSeek's general privacy policy says it stores data on servers in China. Privacy: [privacy policy](https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html). |
| Groq | API key from [console.groq.com](https://console.groq.com/) | (untested). Your text goes to Groq. Privacy and terms: [services agreement](https://console.groq.com/docs/legal/services-agreement). |
| OpenRouter | API key from [openrouter.ai](https://openrouter.ai/) | (untested). Requests go to the company running the model you pick; Proofline asks OpenRouter to skip companies that store or train on your text. The model list is loaded from OpenRouter (Refresh). Privacy: [privacy page](https://openrouter.ai/privacy). |
| Ollama | Nothing. Ollama running on this computer (default `http://localhost:11434`), or another address you enter | Tested with a live Ollama server (qwen2.5:3b on localhost, 2026-10-26). No key and no cost. Your text stays on this computer at a localhost address; at any other address it goes to that computer. A cloud model (Proofline recognises one by a name ending in `-cloud` or `:cloud`, which is unverified) sends your text to Ollama's servers. |
| Other OpenAI-compatible server | The server's address (LM Studio, llama.cpp `llama-server`, Jan, Together AI and similar), and a key only if the server asks for one | (untested). Your text, and your key if you saved one, go to that address. Cost is not tracked, because the server may be paid. |

Copilot is not supported: Microsoft and GitHub offer no public API that other apps can use with
your Copilot subscription.

**(untested)** means no one has yet checked that provider with a real account. Claude and Ollama are the
tested ones. If an untested provider does not work for you, please report it on GitHub; the label
comes off once it is confirmed to work. Plain `http://` to a computer other than this one is not
encrypted, so Proofline warns about it, and a key cannot be saved for such an address; use
`https://`, or turn off the server's key requirement on a trusted network.

The model lists for Ollama, Other and OpenRouter come from the provider's server. They are fetched
when you press **Refresh**, when you save an Ollama or Other address, and when you pick OpenRouter (OpenRouter's prices
are also loaded at startup, and when you turn AI on, while it is the selected provider, because the spending check
needs them; a failed load is tried once more after 30 seconds);
never when the page opens. Each provider remembers its own model, including a typed name. A typed
model is charged at that provider's most expensive listed model (for OpenRouter, the most
expensive model in the loaded list). A typed model that costs more than every listed one can pass the
limit. The page says the cost is estimated.

Then, in the card under an underlined word, click **AI Rephrase**. The card shows the sentence it
picked and "Asking the AI...", then up to three rewordings with the changed words in bold.
Click one to replace that sentence; nothing else in the text box changes. For a sentence with
no underlined word, set a shortcut for **AI Rephrase the sentence at the caret** in
**Settings › Shortcuts** (none by default), put the caret in the sentence and press it.

<table>
  <tr>
    <td align="center"><img src="docs/images/ai-rephrase-light.png" width="300" alt="The card under an underlined word, with AI Rephrase rewordings of a sentence"><br><sub>AI Rephrase in the card</sub></td>
    <td align="center"><img src="docs/images/ai-find-light.png" width="300" alt="The issues popup with the AI links open and an AI suggestion row below a spelling mistake"><br><sub>Find more issues</sub></td>
  </tr>
  <tr>
    <td align="center" colspan="2"><img src="docs/images/ai-settings-light.png" width="600" alt="Settings, AI page with the switch, provider, API key, model and monthly limit"><br><sub>Settings, AI</sub></td>
  </tr>
</table>

- For AI Rephrase, only that one sentence is sent to the provider you chose, with its key.
- Every request is counted in `ai_usage.jsonl` (provider, token counts and cost, never your
  text), and **Settings › AI** shows today's and this month's totals. Cloud providers show
  dollars against the spending limit; Ollama and Other show tokens and requests instead. Once a
  cloud request could take the month past your limit, AI requests stop until next month or a
  higher limit.
- **Cancel** hides the answer, but a request already sent still finishes and still counts
  toward the limit.
- If you type in the text box while the AI is answering, the answer is dropped.
- If the provider rejects your key, **AI Rephrase** is hidden until you save a new key or
  **Test** succeeds.
- Each provider keeps its own key, model and address. Switching provider does not send one
  provider's key to another, and a Test result for a provider you have since left is ignored.
- The sentence finder is simple: it can split after abbreviations such as "e.g.", so check the
  sentence shown in the card.

**Find more issues.** Open the issues popup from the badge, click **AI ▾**, then **Find more
issues**. The AI reads the whole text box and returns problems LanguageTool missed. They get a
purple line (LanguageTool's are red) and a popup row titled "AI suggestion", with the same fix
buttons and **Ignore for now**.

- The whole text of the box is sent, at most 8,000 characters. On Claude a full box costs about
  $0.0013 on Haiku and about $0.05 on Opus; on other cloud providers the cost depends on their
  prices. Either way it counts toward the monthly limit like any other request.
- The findings belong to that text. If you edit it yourself, they disappear; a fix Proofline
  applies for you keeps the others in place.
- On text with no LanguageTool issues, the badge appears only while **Settings › Appearance ›
  Show the badge in every text field** is on (the default).

**Rewrite for clarity and Change tone.** In the issues popup, click **AI ▾**, then **Rewrite
for clarity**, or **Change tone** and one of **More formal**, **More casual**, **Shorter** or
**Friendlier**. The AI rewrites the whole text box, and Proofline lists each changed phrase as its
own row titled with the job ("Clearer wording", "More formal" and so on): click the new wording to
apply that change, or **Ignore for now** to skip it. **Accept all AI suggestions** at the top of
the list applies every AI change at once. Your text is never replaced as one block.

- The whole text of the box is sent, at most 8,000 characters. The AI sends the whole text back,
  so a full box costs a little more than Find more issues.
- A rewrite that changes most of the words says so above the rows; check each change.
- A change that adds or removes a line break is not offered (the line under the popup says how
  many were left out), because pasting a line break is not reliable in every app.
- The changes belong to that text, like Find more issues: editing it yourself clears them, and a
  change Proofline applies keeps the others in place.

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
| Checking | Typing pause, minimum words, Picky mode, hidden characters, personal dictionary, turned-off rules (by name) and categories (checkboxes) |
| Apps & fields | Add a text field, apps (pick a running app) and window titles to skip, apps to always check, custom fields |
| Appearance | Theme (follow Windows / light / dark), accent and tray colour, badge visibility, underlines |
| Shortcuts | Three global shortcuts, recorded by pressing the keys |
| AI | Use AI suggestions (on or off), the provider, its API key (Save, Test) or server address, the model with its prices, the monthly spending limit (cloud providers), and today's and this month's usage totals |
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
  confirm, if the address is plain `http://` to another computer. The one exception is
  [AI suggestions](#ai-suggestions-optional): off by default, and when you turn them on, the
  text you ask about is sent to the AI provider you chose (or to the Ollama or other server
  address you set), as described in that section.
- Password fields are never read. By default the app also skips password managers, terminals,
  remote desktop and VM windows, code and spreadsheet editors, File Explorer, browser address
  bars, search boxes, numeric fields, fields labelled like one-time codes, card numbers, SSNs, PINs, API keys or tokens, and
  windows whose title contains *Password*, *Sign in*, *Log in*, *Login* or *Windows Security*.
- Logs never contain what you type unless you turn on **Debug mode** (Settings › Advanced) or set
  `PROOFLINE_LOG_TEXT=1`. Window titles are logged.
- Corrections use the clipboard briefly; your clipboard contents are restored and the correction
  is kept out of Windows clipboard history (Win+V).
- Settings and logs live in `%LOCALAPPDATA%\Proofline` (outside OneDrive), or in the portable
  copy's `data` folder.
- Anonymous usage counts: the app sends the number of corrections and AI rephrases you applied,
  with a random id, to the author's counter, at most once an hour, for the badges above. No text is sent. Details
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

AI Rephrases counts the AI rewordings you chose that the app then pasted into the text box,
under the same rules: a request you cancelled, a rewording you did not pick, or one the app
refused to paste counts nothing. An applied rewording counts here and not under Corrections
Applied. It is reported the same way as Corrections Applied, under its own name
(`proofline-ai`) with its own random id, and the same setting turns both off.

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

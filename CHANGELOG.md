# Changelog

All notable changes to this project.

## 0.4.5 (2026-11-13)

### Changed
- `THIRD-PARTY-NOTICES.txt` in the app folder now lists every bundled package. It was missing
  annotated-types, typing-inspection, docstring-parser, opentelemetry-api, PyQt6-sip, PyQt6-Qt6
  (it named only "Qt 6") and the PyInstaller bootloader. The build now stops when a bundled
  package is not listed.
- The app folder no longer includes setuptools and pygments, which the app never used.
- With the Orange accent in light mode, buttons and the flyout's selected tiles now use black
  text. White text on that orange was below the usual contrast guideline (3.1:1 where 4.5:1 is
  recommended).

### Fixed
- Closing the **Add a text field…** window with Esc left it watching every focus change until
  Proofline restarted, including while checking was paused. Esc now stops it, as Close does.
- A server address the app could not parse (for example a port above 65535) put the whole
  address, password included, into the log and the error message on every check. The password
  is now removed from error text, and Settings refuses a port outside 1 to 65535.
- An AI provider's "forbidden" answer (HTTP 403) was reported as "did not accept the API key" and
  turned the AI links off until **Test** was pressed. Providers also send it when one text is
  flagged by moderation, when the region is not supported, or when the key lacks access to one
  model. The provider's own reason is now shown, and the AI links stay on.
- When the program in front stopped responding, Proofline could stop checking every field,
  in every app, until that program recovered or was closed (measured: a single read waited 60
  seconds). It now skips a program that does not answer within a quarter of a second and checks
  it again once it responds.
- In **Settings › Shortcuts**, pressing a combination Proofline already uses ran that shortcut
  instead of putting it in the box, so two shortcuts could not be swapped. Proofline's shortcuts
  are now turned off while a shortcut box has the keyboard focus.
- A correction could paste your own clipboard contents instead of the suggested word when the
  program you were typing in was busy for more than about a third of a second (measured with a
  0.7 second delay). Proofline now waits until the field shows the correction, for up to two
  seconds, before it puts your clipboard back.

## 0.4.4 (2026-11-12)

### Added
- **Fix all N issues** in the issues popup applies the first suggestion of every LanguageTool
  issue at once. It shows when two or more issues have a suggestion; AI findings keep their own
  **Accept all AI suggestions**.

### Fixed
- After **Add to dictionary** or **Ignore for now**, the wavy line under that word could stay on
  screen. The line is now removed at once.
- One invalid value in `config.json` no longer resets every setting. Only that setting takes its
  default; the personal dictionary, the skipped apps and the other settings are kept. The file as
  it was is copied to `config.json.bak` first.
- When Windows refused to put a correction on the clipboard, the clipboard was left empty. Your
  earlier clipboard contents are now put back, and no keystroke is sent.
- A correction checks again that the same field and window are in front immediately before it
  sends Ctrl+V or Delete. Before, a switch to another window while the word was being selected
  (up to half a second) could send the keystroke to the other program.
- Fields whose automation ID names a password, key, PIN, card number, token, user name or email
  in camelCase (such as `txtPassword`, `myApiKey`, `creditCardNumber`, `txtUserName`) are no
  longer checked. Before, only IDs with the word separated by `_`, `-` or a space were skipped.
- **Don't check in › Apps** could match the wrong program after Windows gave a closed program's
  process number to a new one, because the program name was remembered per process number.
- When the LanguageTool server comes back after an outage, the field in front is checked at once.
  Before, text typed during the outage stayed unchecked until it was edited.
- If the app cannot start, it now shows a message with the error and where the log is. Before,
  the packaged app exited with no icon and no message. When the log folder cannot be written
  (such as a portable copy in a read-only folder), the log goes to `%TEMP%\Proofline\logs`.
- An AI answer from a paid provider that came back without token counts was recorded as costing
  nothing, so it did not count toward the monthly AI limit. It is now recorded at its largest
  possible cost, as failed requests with an unknown outcome already were.
- The card under a flagged word now moves with the word when the text scrolls. Before, it stayed
  where the word had been.
- After **Add to dictionary** on the card under a word, the next issues list (even in another
  field) opened with an old "Added *word* to your dictionary" notice. That notice now shows only
  when the word is added from the open list.
- Shortcuts typed in **Settings › Shortcuts** but not yet applied are kept when another setting
  saves. Before, any other change reloaded the page and the typed keys were lost.
- The Checking tile's tooltip and the minimum-words help in Settings name your own shortcuts.
  Before, they always said Ctrl+Alt+P and Ctrl+Alt+L, even after those shortcuts were changed.
- The sections in Settings that fold open (personal dictionary, turned-off rules, app and window
  lists) can be reached with Tab and opened with Space or Enter, show an outline when focused, and
  have a name for screen readers. Before, only the mouse could open them.
- Clicking the badge while a check is running shows "Checking…" until the results arrive. Before,
  the list said "No issues found." in that time.
- The Undo notice after **Turn off in this app** or **this window** stays open while the mouse is
  on it, and closes 10 seconds after the mouse leaves. Before, it closed after 10 seconds even
  while you were reaching for Undo.
- When another program held the clipboard just after a correction was pasted, the correction was
  reported as failed although it had been applied. Putting your clipboard back is now tried three
  times, and a failure is only logged.
- An Ollama answer that stopped at the length limit now says it was cut off, as the other
  providers do, instead of "could not be read".

### Changed
- The log no longer contains window titles or the words in your personal dictionary and other
  setting lists unless **Debug mode** or `PROOFLINE_LOG_TEXT=1` is on. Without it, a window
  title is logged as its length and each list as its number of items.

## 0.4.3 (2026-11-03)

### Fixed
- The badge no longer appears in fields that are not prose:
  - User name and email sign-in fields (a label, ID or class with *user name*, *username*,
    *user ID*, *login ID* or *email*). Fields such as *Email body* are still checked.
  - Dropdowns you can type into, such as the Outlook reminder snooze box and web pickers.
  - Fields whose text is only numbers and punctuation, such as an IP address, an amount or a
    date.
  - Code-entry fields labelled *Enter code*, *Secure code* or *Enter time-based code*.
- An Outlook reply was skipped as a "sensitive field" when the email subject contained a word
  such as *password*, because Outlook names the message body after the subject. The label rules
  now ignore a document's name; its help text, automation ID and class are still checked.

### Changed
- LastPass for Desktop is on the recommended list of apps to skip; it is added once to existing
  settings.

## 0.4.2 (2026-10-31)

### Fixed
- Applying a correction could fail now and then with "Thread does not have a clipboard open", or
  leave the clipboard unrestored. Proofline now opens the clipboard with a hidden window of its
  own instead of none.
- AI changes applied from the issues popup (Find more issues, Rewrite for clarity, Change tone,
  Accept all) now count toward the AI Rephrases badge. They were counted as Corrections Applied,
  so the AI Rephrases badge only moved when someone used AI Rephrase.

## 0.4.1 (2026-10-29)

### New
- **Rewrite for clarity** and **Change tone** (More formal, More casual, Shorter, Friendlier) in the
  issues popup's **AI ▾** row. The AI's rewrite is listed as separate changes, each applied or
  skipped like any suggestion; **Accept all AI suggestions** applies them all at once. Your text is
  never replaced as one block.

### Fixed
- Links on the Rules page and the AI privacy link keep the accent colour after the language or
  provider changes while Settings is open.
- Search boxes are no longer checked: the Start menu and Settings search, and search inputs on
  web pages and in apps.
- File Explorer is no longer checked by default (its address bar, search box and rename box).
  Settings from earlier versions get it added to **Don't check in › Apps** once; remove it there
  to check File Explorer again.
- Clicking into a text box no longer shows the grey checking badge before you type. A box that
  already holds text shows its result when the check finishes.
- Deleting a word and typing it again no longer leaves the grey checking badge up without a check.
- `Ctrl+Alt+J` applies the first LanguageTool suggestion only; it no longer applies an AI finding.
- An AI finding that deletes text offers a remove button instead of "No suggestion".
- A suggestion containing `&` shows the `&` instead of underlining the next letter.
- "Asking the AI..." no longer comes back after the request ended or AI was turned off, and no
  AI message appears under the Undo notice after **Turn off in app**.
- Clicking the badge while a rewording is on screen no longer opens the issues list beside it.
- Pressing the AI shortcut again while a rewording is being fetched no longer throws away the
  first answer (which was still billed); the extra press is ignored.
- AI requests now stop at their stated time limit (20 seconds, 120 for Ollama and Other) for the
  whole request, not for each network step.
- A LanguageTool check that times out (10 seconds) shows the server error at once instead of after
  three tries (about 32 seconds). Other failures are still tried again quietly.
- Checking text that has not changed since its last check reuses that result instead of asking
  the server again.
- Settings links use your accent colour (or the theme link colour when the accent is too faint to
  read); they were pure blue.
- Settings › AI describes both features, keeps saying when a saved Other server key does not belong
  to the current address, updates the usage line when the spending limit changes, and enables
  **Test** again after an unexpected error.

## 0.4.0 (2026-10-26)

### New
- **Find more issues**: in the issues popup, **AI ▾** then **Find more issues** asks the AI provider
  for problems LanguageTool missed in the whole text box. They show with a purple line and as
  "AI suggestion" rows with the usual fix buttons and Ignore. Fixes Proofline applies keep the
  other findings in place; editing the text yourself clears them.
- **More AI providers.** Settings › AI now offers OpenAI, Gemini, Grok, Mistral, DeepSeek, Groq,
  OpenRouter, Ollama (on this computer or another address you enter) and any OpenAI-compatible
  server (LM Studio, llama.cpp, Jan, Together AI and similar), alongside Claude. One provider is
  active at a time, and each keeps its own key, model and address. Providers other than Claude
  and Ollama are marked "(untested)" until someone confirms them with a real account. The monthly spending
  limit covers the cloud providers; Ollama and Other show tokens and requests instead. Copilot is
  not supported: Microsoft and GitHub offer no public API for other apps. Existing settings keep
  Claude.

### Fixed
- Text from the AI in the issues popup and the card is always shown as plain text.
- One slow or failed reply from the LanguageTool server no longer shows the server error. Proofline
  tries the check up to three times, one second apart, and shows the error only if all three fail.
- Test in Settings › AI says "Ollama answered." (or "Other server answered.") when no key was sent,
  instead of "The key works."

## 0.3.1 (2026-10-26)

### Fixed
- The installed and portable 0.3.0 apps could save a Claude API key but never read it back:
  the AI page kept showing the empty key box, Test stayed disabled, and AI features could not
  be used. A module that reading from Windows Credential Manager needs was missing from the
  package. A key you already saved in 0.3.0 is picked up after updating.
- When Proofline cannot read the key from Credential Manager, the AI page now says so under the
  key box. Before, the error went only to the log.

## 0.3.0 (2026-10-26)

### New
- Optional AI suggestions through Claude, Anthropic's AI model, with your own API key. Off by
  default. **Settings › AI** holds the on/off switch, the key (kept in Windows Credential
  Manager) with a Test button, the model, a monthly spending limit (default $1.00), and
  today's and this month's totals.
- **AI Rephrase** in the card under an underlined word: up to three rewordings of that sentence,
  changed words in bold. Choosing one replaces only that sentence. Only the sentence is sent.
- A shortcut to rephrase the sentence at the caret, for sentences with no underlined word. Set
  it in **Settings › Shortcuts** (none by default).
- An AI Rephrases badge in the README: the number of AI rewordings applied, counted like
  Corrections Applied and turned off by the same setting.
- Wavy red lines under flagged words, drawn over the text box in apps that report where each
  word is on screen (tested in Edge and Notepad). They follow the text when it scrolls, disappear
  while you type, and return after the next check. Clicks go through to the text box.
  Settings › Appearance › Underline issues in the text turns them off.
- A card under an underlined word while the caret is inside it: up to three suggestions (the
  first highlighted), Ignore, Add to dictionary for spelling, and All issues… for the popup.
- Hidden characters are flagged: a zero-width space, soft hyphen or direction mark inside a word,
  text-direction controls anywhere, and unusual spaces (thin, em, narrow no-break, ideographic and
  similar). Placeholders that web editors (Slate, Quill, CKEditor 5) insert themselves are not. The
  popup shows each as its code, such as `[U+200B]`, with a fix that removes it or puts a normal
  space in its place. On by default; Settings › Checking › Flag hidden characters turns it
  off. LanguageTool does not flag these itself.

### Fixed
- A password field is recognised as soon as it has focus, before Proofline looks at the
  text box around it, so its text is never read.
- A suggestion that removes text (**(remove)**) now deletes the selection with the Delete key
  instead of pasting an empty clipboard.

## 0.2.2 (2026-10-25)

### New
- Drag the issues popup by its heading to move it. A moved popup stays open until you close it,
  follows the text box you type in, and shows "Checking…" while a check runs. Useful when the Start
  menu covers the popup.

### Fixed
- The grey checking badge appeared as soon as you clicked into an empty box (Start menu search,
  Discord) and kept spinning, although no check runs until the box holds the minimum number of
  words. It now waits for that.

## 0.2.1 (2026-10-24)

### Fixed
- Unzipping the 0.2.0 portable version over a 0.1.0 install started with empty settings: the
  portable copy looked only in its own `data` folder. A portable copy without settings now copies
  them once from `%LOCALAPPDATA%\Proofline`; the original file is left in place. (Workaround for
  0.2.0: delete `portable.txt` from the Proofline folder.)

## 0.2.0 (2026-10-24)

### New
- First-run welcome window on a fresh install: pick and test a server, see what the badge states
  mean, choose Start with Windows.
- Portable version (`Proofline-<version>-portable.zip`, settings in a `data` folder next to the
  exe) and a per-user installer (`Proofline-<version>-setup.exe`, no administrator rights).
- Tray quick settings: one **Checking** tile with On / Pause for 1 hour / Pause for the rest of
  today / Off, replacing the separate Pause tile. Picky mode reads "Extra style tips".
- New shortcut **Ctrl+Alt+J** applies the first suggestion for the current text box.
- Settings › Advanced › **Check now** checks for a newer release straight away; **Help** and
  **What's new** links open the troubleshooting guide and this changelog.
- Readable names in Settings: turned-off rules by name, categories as checkboxes, "Pick a running
  app…" for the app lists, custom fields as a short sentence, shortcuts recorded by pressing the
  keys and shown in capitals (CTRL+ALT+P).
- The turned-off rules and categories card links to LanguageTool's rule browser (for the chosen
  language) and its list of categories.
- Setup tips and the new-version notice open their page when the notification is clicked.
- The field picker ("Add a text field…") is styled like the app, shows only the buttons that apply,
  and folds the technical details away.

### Fixed
- Small windows no longer flash on screen when the app starts.
- The flyout's tile text was clipped at 150% and 200% display scaling.
- The flyout's "Current app" card showed the taskbar ("No text box focused") after clicking the
  tray icon; it now keeps the app you were last typing in.
- Links in dark mode were dark blue on dark grey; they use the accent colour now. The flyout's
  settings gear was drawn as a colour emoji.
- The welcome window warns and asks before using plain `http://` to another computer, like
  Settings.

### License
- Proofline is now free software under the GNU General Public License version 3 (`LICENSE`).
  Release builds include `LICENSE.txt` and `THIRD-PARTY-NOTICES.txt`. The README has a Disclaimer
  section on LanguageTool's trademark and terms.

### Accessibility
- The badge is larger (24 px disc) and has a name screen readers announce, such as "Proofline: 3
  issues. Click to see them."

## 0.1.0 (2026-10-24)

First release.

### Anonymous usage counts (2026-10-24)
- README badges for Corrections Applied and Active Installs, counted like the PiratesIRC
  Dispatcharr plugins: the app sends its applied-correction total and a random install id to
  plugin-stats.dpas.workers.dev, at most once an hour (ten minutes after a new correction). No text
  is sent. **Settings › Advanced › Share anonymous usage counts** (on by default) turns it off and
  asks the server to delete this install's figures.

### Update check (2026-10-24)
- Settings › Advanced › About shows the installed version and whether a newer release exists on
  GitHub ("You are up to date", "Update available", or "Version check unavailable"), with a
  Releases link. A new release is announced once by a tray notification.
- The check runs in the background, at most daily (2 hours after a failure), and never while a
  window opens. Turn it off with **Check for updates**.

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

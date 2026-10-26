# AI assist (Claude API) design

Date: 2026-10-26. Status: draft for the operator's approval. Nothing here is built yet.

Marking: **[operator]** = the operator chose it in the brainstorming answers.
**[my call]** = Claude chose it after the operator said "go"; the operator can overturn any of these.

## Intent

Proofline checks text with LanguageTool, which finds rule-based spelling and grammar errors. The
operator wants an optional AI layer on top that can do what LanguageTool cannot: reword a
sentence, rewrite text for clarity, change its tone, and find word-choice or grammar problems
the rules miss. It must stay a proofreader, not a ghost-writer: the operator keeps control of
every change, every send, and every cent.

## Goals

1. Four AI jobs **[operator]**:
   - **Rephrase this sentence**: from the card under a flagged word, and from a shortcut for the
     sentence holding the caret; 1 to 3 rewordings of that one sentence.
   - **Rewrite for clarity**: the whole field (or the selection, if one exists).
   - **Change tone**: the whole field or selection, to one of: more formal, more casual,
     shorter, friendlier **[my call: these four presets, no free-text instruction box in v1]**.
   - **Find what LanguageTool missed**: extra issues that appear as ordinary underlines and
     popup rows, marked as coming from AI.
2. Provider: the Claude API through the official `anthropic` Python SDK, with the operator's
   own API key **[operator]**.
3. Runs only when the operator asks: a click or a shortcut. Never on a typing pause, never in
   the background **[operator]**.
4. Results never replace the field wholesale. Every rewrite is diffed against the original into
   separate word-level suggestions, each accepted or skipped like a LanguageTool fix, and applied
   through the existing verified correction path (`replace_request.py`, `text_replace.py`)
   **[my call, from the operator's "rewrites too much" deal-breaker]**.

## Non-goals (v1)

- Local models (Ollama, LM Studio) or other providers. The client sits behind a small interface
  so one can be added later, but none is built.
- Automatic or continuous AI checking.
- Free-form chat or "write this for me" generation.
- Image, file, or clipboard input. Only the text Proofline already read from the focused field.
- Syncing keys or usage between PCs.

## Anti-goals (a failure even if it works)

From the operator **[operator]**:

- **Text sent without the operator's action.** Any request not started by a click or shortcut is
  a bug. Text from fields Proofline skips (password fields, sensitive labels, excluded apps) is
  never sent, even on request.
- **Slow responses.** A request with no visible progress, or one that can hang.
- **Surprise costs.** Spending with no running total or no hard limit.
- **Rewriting too much.** Changes to meaning or to the operator's voice, or one opaque block
  replacing their text.

## The parts, as decided

### Turning it on **[my call]**

- Off by default. Settings gets a new **AI** page: an on/off switch, an API key box with a
  Test button, a model picker, a monthly spending cap, and the usage totals.
- The key is stored in Windows Credential Manager through `win32cred` (pywin32 is already a
  dependency), target name `Proofline/anthropic-api-key`. Never in `config.json`, never logged,
  never shown again after saving (the box shows "Key saved" plus a Remove button).
- With the switch off or no key saved, no AI button, menu item, or shortcut appears or works.

### Where the operator asks **[my call]**

- **Card** (`issue_card.py`): a **Rephrase** link in the action row. It rewords the sentence
  holding the flagged word. The rewordings replace the card's fix list while it waits, with a
  small "Asking Claude..." line and a Cancel link.
- **Popup** (`overlay_widgets.IssuesPopup`): a new **AI** link in the header opens a short inline row
  (built at step 3 as a row of links, not a Qt menu: a menu grabs the mouse and would eat the
  user's click back into the field):
  Rewrite for clarity, Change tone (submenu of the four presets), Find more issues. The popup is
  also where results of the whole-field jobs appear.
- **Badge**: when there are no LanguageTool issues the popup still opens from the badge (it
  already shows a "no issues" state), so the AI menu is reachable on clean text.
- **Shortcuts**: one new global hotkey, "Rephrase the sentence at the caret (AI)" (named "AI rewrite
  sentence" in the first draft), empty by default, set on the Shortcuts page like the existing three. The results open
  in the same card, placed under the caret rectangle instead of under a flagged word, so the
  shortcut works on sentences with no flagged word. Choosing a rewording applies it through the
  same verified path as the card's other fixes. If the field reports no caret rectangle, the card
  opens under the field's top-left corner.
- **Tray flyout**: no AI controls in v1.

### What the operator sees while it works **[my call]**

- A progress line in the card or popup ("Asking Claude...") with a Cancel link, shown within
  100 ms of the click.
- Timeout of 20 s, then an error line with a Retry link. Errors (no network, bad key, cap
  reached, rate limit, refusal) each get a plain one-line message; none open a dialog.
- If the field's text changes while waiting, the result is discarded (same rule LanguageTool
  results already follow: a stale snapshot is dropped).

### Showing the results **[my call]**

- **Rephrase**: up to 3 rewordings as buttons in the card, full sentence each, with the
  changed words in bold. Clicking one replaces that sentence only.
- **Rewrite for clarity / Change tone**: the popup lists the changes as rows like LanguageTool
  rows: the original fragment struck through, the new fragment, Accept and Skip. An "Accept all"
  link at the top. Changes are word-level diff hunks of original versus rewrite (Python
  `difflib.SequenceMatcher` on word tokens, merging hunks closer than 2 words apart).
- **Find more issues**: each issue becomes a `Match` with category "AI" and rule id
  `AI_SUGGESTION`, so it gets an underline, a card, Ignore and the popup row for free. Its
  underline is a different colour from LanguageTool's red (a purple, picked in the light and dark
  render check). Results are kept for that snapshot only and cleared when the text changes.
  Ignore uses the existing key, `(rule_id, error_text)` held for the session only
  (`dictionary.ignore_key`), so ignoring one AI finding hides AI findings on that same quoted
  text only, not every AI finding.
- AI rows and AI suggestions are labelled "AI" so they are never confused with LanguageTool's.

### Keeping it from rewriting too much **[my call]**

- The system prompt tells the model to keep meaning, facts, names, and the author's voice; to
  change only what the job requires; and to return the text unchanged when it is already fine.
- Responses use structured output (`output_config.format` with a JSON schema), so Proofline
  parses fields, never free text. Schemas: rephrase returns `{"options": [string]}`; rewrite and
  tone return `{"text": string}`; find-issues returns
  `{"issues": [{"quote": string, "occurrence": int, "message": string, "replacement": string}]}`,
  and Proofline locates each quote in the text itself (the model does not give offsets). An issue
  whose quote is not found is dropped.
- A rewrite that changes more than 60% of the words is shown with a warning line at the top
  ("This rewrite changes most of the text") rather than hidden.

### Model and cost **[my call]**

- Default model `claude-haiku-5-5` (fastest, $0.10 / $0.50 per million input / output tokens
  at prompts of 100K tokens or fewer, measured from the claude-api skill's model table
  2026-10-26), effort `low`. The picker also offers `claude-sonnet-5-5` ($2.00 / $10.00) and
  `claude-opus-5-5` ($4.00 / $20.00), prices from the same table, shown beside each name.
- Prices are a constant table in code, one row per model. They are checked against Anthropic's
  pricing page at each Proofline release (a step in the release checklist). A model
  missing from the table cannot be picked.
- Input limit: 8,000 characters per request. Longer text is refused with a message ("Select a
  shorter part to rewrite") rather than truncated.
- `max_tokens` 2,000 for rephrase and find-issues, 4,000 for rewrites.
- Usage ledger: every response's `usage` (input and output tokens) and its cost at the model's
  price is appended to `ai_usage.jsonl` in Proofline's data folder (`%LOCALAPPDATA%\Proofline`,
  or `data\` beside the exe for a portable copy, the same folder as `config.json`), with date,
  job, model, tokens and cost; never the text. The AI page shows today's and this month's
  totals. A portable copy therefore has its own ledger and cap, like its own settings.
- A request that was sent but returned no `usage` (timeout, cancel, dropped connection) is
  recorded at its worst-case cost, so the recorded total is never below the real spend. One
  Proofline request at a time; a second click while one is running is refused with a message.
  The SDK's automatic retries are set to 0 so one click is at most one billed request.
- The key's Test button sends a fixed short prompt and is counted like any other request.
- Months are calendar months in local time.
- Monthly cap, default $1.00, settable from $0.10 to $100. When this month's total reaches the
  cap, AI requests are refused with "Monthly AI limit reached" until the next month or a higher
  cap. The check runs before sending, using the worst-case cost of the request (input estimate
  plus `max_tokens` of output), so one request cannot pass the cap by much.

### Privacy **[my call]**

- Only the field text (or selection, or sentence) is sent. No language code is sent (corrected at
  step 2: the prompt asks for the text's own language).
- Typed text is never logged, following the existing `logging_setup.text_logging_enabled()` rule.
- The Settings AI page states in one line what is sent and to whom, and links to Anthropic's
  data-use page.

## Constraints from the existing project

- Python 3.13, PyQt6; new dependency `anthropic` (official SDK). It must be added to
  `requirements.txt`, bundled by PyInstaller, and the bundle size change measured.
- HTTP runs on the Qt thread pool (`workers.run_in_background`), never on the GUI thread or the
  UIA monitor thread. Results come back by Qt signal.
- Corrections go through the verified path (same field runtime ID, unchanged text, exact
  selection), queued with `request_replace`. Offsets are UTF-16 where they meet LanguageTool
  code (`lt_client.utf16_index_map`).
- New config fields follow the `Config` rules (immutable dataclass, `validate()`, `BOOL_FIELDS`,
  tests, `docs/CONFIGURATION.md`). Settings save instantly except the key, which uses explicit
  Save and Test buttons like the server URL.
- Tests must not call the real API. A fake client covers the jobs; one opt-in live test runs only
  when an environment variable with a key is set, like `LT_TEST_SERVER_URL` does today.
- Files under 800 lines, functions under 50; README, CHANGELOG and docs updated; the README and
  release notes go through the outbound-writing check.

## Suggested build order **[my call]**

1. Key storage, AI settings page, client wrapper, usage ledger and cap. No visible AI action yet.
2. Rephrase from the card (smallest result UI, uses the existing card).
3. Find more issues (reuses underlines, card and popup rows).
4. Rewrite for clarity and Change tone with the diff rows in the popup.

Each step is its own feature commit plus test commit and is usable on its own.

## Left to the builder

- Module names and splits (for example `ai_client.py`, `ai_jobs.py`, `ai_diff.py`, `ai_usage.py`,
  `ai_keys.py`, a settings page class).
- Exact prompt wording, within the rules above.
- Sentence splitting for Rephrase (a simple rule-based splitter is fine).
- Exact layout and spacing, checked by rendering light and dark PNGs.
- The purple for AI underlines, as long as it reads in both themes and differs from the red.

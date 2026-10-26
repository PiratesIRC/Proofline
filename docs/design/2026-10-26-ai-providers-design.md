# AI providers other than Claude: design

Date: 2026-10-26. Status: revised after three design reviews (builder check, security and privacy,
fit with the existing code); for the operator's approval. Nothing here is built yet.

Marking: **[operator]** = the operator chose it in the brainstorming answers.
**[my call]** = Claude chose it; the operator can overturn any of these.
**[research]** = from the provider research and the fact-check of 2026-10-26 (provider
documentation only, no real requests). **[review]** = added or changed because a design review
found a problem.

## Intent

Proofline's AI features (AI Rephrase in 0.3.x; Find more issues on branch `ai-step3`; Rewrite and
Change tone later) work only with Anthropic's Claude API today. The operator wants Proofline to
offer every major AI provider, so a user can pick the one they already have a key for, or a model
running on their own computer **[operator]**.

## Goals

1. These providers, in this order in the list **[operator, from the research shortlist]**:
   Claude (Anthropic), OpenAI, Google Gemini, xAI Grok, Mistral, DeepSeek, Groq, OpenRouter,
   Ollama, and "Other OpenAI-compatible server" (LM Studio, llama.cpp `llama-server`, Jan,
   Together AI and similar, by address).
2. One provider is active at a time, picked on the Settings AI page. Each provider keeps its own
   key, model choice and (Ollama, Other) server address, so switching provider and back loses
   nothing **[operator, on my recommendation]**.
3. Every AI feature works with every provider. Features, prompts, card and popup behaviour do not
   change; only where the request goes changes.
4. Ollama shows usage in **tokens and requests**, with no dollar cost and no spending limit
   **[operator]**. "Other" does the same, but because it can point at a paid service (for
   example Together AI) that Proofline cannot detect, its usage line says "cost not tracked", never "runs
   locally" **[review]**.
5. Cloud providers keep dollar costs and the monthly spending limit.

## Non-goals

- **Copilot** **[operator]**. Microsoft Copilot (consumer) has no public API; Microsoft 365
  Copilot APIs need a company tenant and are in preview; GitHub Models was retired on 2026-07-30;
  the GitHub Copilot SDK needs GitHub's separate runtime program and a GitHub sign-in renewed about
  every 8 hours, has no JSON-schema option or token counts, and GitHub's terms do not say whether a
  public third-party app may use it **[research]**. The README says Copilot is not supported
  because it has no public API for third-party apps.
- Amazon Bedrock and Perplexity (AWS account setup; a search product with a different API)
  **[research, my call]**. Reachable through "Other" if someone wants to try.
- Choosing a provider per request, or falling back to a second provider when one fails
  **[operator, on my recommendation]**.
- Prompts tuned per provider. All providers get the same system prompts and schemas.
- Reading a provider's account balance.
- Sending a key over plain HTTP to another computer (see Addresses) **[review, my call]**.

## Anti-goals

- Text or a key going to a provider or address the user did not pick, or being sent when AI is
  off. The existing rules (only when asked, one request at a time, 8,000-character limit) stay.
- A key in `config.json`, in a URL, or in the log. Keys stay in Windows Credential Manager only.
- A provider that ignores the JSON schema producing garbage in the card or popup. Every answer is
  checked on Proofline's side before use.
- The spending limit silently not applying, or spend that was sent but not counted.

## Settings AI page (layout A) [operator]

The page keeps its current look (the operator chose mockup "A. Provider drop-down"; mockups of
Gemini and Ollama selected were shown on 2026-10-26). Top to bottom:

1. **Use AI suggestions** switch (unchanged).
2. Group **Provider**:
   - **AI provider** card: a drop-down with the ten providers. Description: "Each provider keeps
     its own key". A provider not yet tested with a real account shows "(untested)" after its
     name (see Verification).
   - **Key card** for providers that use a key: title "<Provider> API key", description naming
     where to get the key and that it is kept in Windows Credential Manager; key box, Save, Test,
     Remove, working as the Claude card does today, including the read-error message from 0.3.1.
     Other gets the same card marked optional ("Only if your server asks for one").
   - **Server address card** for Ollama and Other: address box with Save and Test. Ollama's
     description: "Ollama's default is http://localhost:11434". This is a second explicit-button
     setting alongside the LanguageTool server URL; the project's "settings save instantly" rule
     is updated to name it **[review]**.
   - **Privacy lines** for the selected provider, replacing today's Anthropic-only text
     **[review: wording corrected]**:
     - Cloud: "When you ask for an AI suggestion, or press Test, Proofline sends that text (Test
       sends a short fixed sentence) to <Provider> with your key. Nothing is sent otherwise." plus
       a link to that provider's API data page. Refresh of a model list also contacts the provider
       and is named where it exists.
     - Gemini: "With a free Gemini key, Google may use your text to improve its products and
       people may read it. Paid keys are covered by different terms." (Google's terms, confirmed.)
     - Mistral: "Mistral may use API data from free accounts for training. Check the privacy
       settings in your Mistral console." (The opt-out switch is confirmed; the free-plan default
       is not, so the wording says "may".)
     - OpenRouter: "Requests go to the company running the model you pick. Proofline asks
       OpenRouter to skip companies that store or train on your text."
     - DeepSeek: "DeepSeek's general privacy policy says it stores data on servers in China."
       (Confirmed in that policy, which does not separately cover API data.)
     - Ollama on localhost/127.0.0.1/[::1]: "Your text stays on this computer." Ollama on any other
       address: "Your text goes to the computer at this address." Ollama models that run on
       Ollama's own servers (cloud models) send the text there; the line says so for such a model
       (how Ollama marks them is to be checked during implementation).
     - Other: "Your text, and your key if you saved one, go to the server at this address."
     - Any `http://` address that is not localhost, 127.0.0.1 or [::1], key or not: "This address
       is not encrypted, so your text can be read on the network." **[review]**
3. Group **Model and spending** (cloud) or **Model and usage** (Ollama, Other):
   - **Model** card (see Models). Ollama, Other and OpenRouter get a Refresh button.
   - **Monthly spending limit** card, cloud providers only. One limit for all providers together
     **[my call]**.
   - **Usage line**: cloud "Today $0.0012 · This month $0.0310 of $1.00 · 14 requests" (all
     providers' dollar spend); Ollama "Today 1,240 tokens · This month 18,900 tokens · 42 requests
     (no cost: runs locally)" when on localhost; Other and non-local Ollama "... 42 requests (cost
     not tracked)".

**Key handling across providers [review]:** the provider is captured when Save, Test or Remove is
clicked and travels with the request; nothing reads "the current provider" later. Switching the
drop-down clears any unsaved text in the key box. A key is only ever sent to the provider it was
saved for; there is no fallback from one provider's key to another's. A Test result for a
provider other than the one now shown is ignored. Changing Other's address deletes Other's saved
key (the user re-enters it), so a key saved for one server is never sent to a new address.

## Models [operator, on my recommendation]

- **Cloud providers: a fixed list of 2-3 models each, with prices built in**, cheapest first and
  default, rechecked at every release (today's `ai_prices.py` rule). Fact-checked lists (dollars
  per million tokens, input / output):

  | Provider | Models |
  |---|---|
  | Claude | unchanged: Haiku 5.5, Sonnet 5.5, Opus 5.5 |
  | OpenAI | `gpt-6-luna` 0.10/0.50, `gpt-6.1-sol` 2.00/10.00, `gpt-6-astra` 10.00/50.00 |
  | Gemini | `gemini-2.5-flash-lite` 0.10/0.40, `gemini-3.5-flash-lite` 0.30/2.50, `gemini-2.5-pro` 1.25/10.00 |
  | Grok | `grok-4.3` 1.25/2.50, `grok-4.5` 2.00/6.00, `grok-4.7` 2.00/6.00 |
  | Mistral | `mistral-small-2603` 0.15/0.60, `mistral-large-4` 1.36/4.18, `mistral-medium-3-5` 1.50/7.50 |
  | DeepSeek | `deepseek-flash` 0.30/1.20, `deepseek-v4-pro` 1.32/3.96: DeepSeek's PEAK rates, so the limit never under-counts **[my call]**. Not readable on DeepSeek's pricing page in either research pass; confirm during implementation |
  | Groq | `openai/gpt-oss-20b` 0.075/0.30, `openai/gpt-oss-120b` 0.15/0.60 only: the models with strict JSON-schema support that are not in preview **[operator]** |

- **OpenRouter: live list** from `GET /api/v1/models`, filtered to models whose
  `supported_parameters` include `structured_outputs`, prices from the same list. Loaded when the
  user picks OpenRouter or presses Refresh, never on page open **[review]**. Also fetched in the
  background at startup when OpenRouter is selected and AI is on, and again after a "no prices" refusal,
  because the spending check needs the prices (**[ruling, final review]**; AI stays unavailable for
  OpenRouter until they load). The list is public, so it is fetched without the key.
- **Ollama and Other: live list** from `/api/tags` and `/v1/models`, loaded on Refresh or when
  the address is saved. Other's list is not filtered (servers do not report capabilities).
- **Typing a model name [my call, changed by review]:** every list ends with "Other model...".
  - Cloud providers: a typed model is charged against the spending limit at **that provider's
    most expensive listed price**, so the limit still holds. The page says "Cost estimated at
    <most expensive model>'s price".
  - Ollama and Other: unpriced, as all their models are.
  - A typed name is checked for shape (letters, digits, `.`, `-`, `_`, `:`, `/`, at most 200
    characters) and URL-encoded where it goes into a URL path (Gemini).
- Each provider remembers its own last model, typed ones included.

## Cost and the usage log [review]

- The usage log (`ai_usage.jsonl`) gains fields for the provider and whether the cost is known.
  **Every new field has a default on read** (provider Claude, cost known), so 0.3.x lines keep
  counting; today an unexpected or missing field makes `read_entries` skip the line, which would
  zero the month and lift the limit. A test reads a line written by 0.3.x.
- Unpriced requests (Ollama, Other) are logged with their token counts and cost 0, flagged
  cost-unknown, and left out of dollar totals. The cost path must not call the price table for
  them on any path: done, error, or estimated after a timeout (today `cost()` raises for an
  unknown model and is called from both the limit check and `_record`). A test covers a timeout
  on an unpriced model.
- Totals gain token sums for the token usage line.
- **OpenRouter:** the limit check before sending uses the list price for the worst case; the log
  records the cost OpenRouter reports (`usage.cost`, in credits, which OpenRouter's FAQ says are
  US dollars). If the reply has no cost, the log uses the list-price calculation.
- **DeepSeek retry:** each attempt passes the limit check on its own; a retry that would pass the
  limit is not sent. Each attempt is logged with its own token counts.
- **Log write failure:** if the usage log cannot be written, AiService keeps the month total in
  memory for the rest of the session so the limit still holds, and logs a warning.

## Requests

- **One shared module for providers that use OpenAI's chat format** **[my call, from the
  research]**: OpenAI, Grok, Mistral, DeepSeek, Groq, OpenRouter, Other. Each is a small settings
  entry: base address, JSON mode, how to turn reasoning off or lowest, where token counts are, and
  which error codes mean bad key / out of credit / rate limited. OpenAI's Responses API or chat
  completions is the builder's choice, as long as structured output and token counts work.
- **JSON mode per provider:** strict JSON schema for OpenAI, Grok, Mistral, Groq, OpenRouter;
  JSON-object only for DeepSeek (schema and the word "json" in the prompt). **Other [review]:**
  sends strict JSON schema; if the server answers 400 naming `response_format` or `json_schema`,
  Proofline retries once in JSON-object mode with the schema in the prompt and remembers that mode
  for that address. Other sends no reasoning setting (unknown server); a leading `<think>...</think>`
  block in the answer is removed before parsing.
- **Reasoning settings (fact-checked):** OpenAI `low` (lowest accepted by gpt-6-luna unconfirmed;
  a 400 naming the effort is a code bug); Grok `low` (cannot be turned off on grok-4.5+; `none`
  unconfirmed on grok-4.3); DeepSeek `thinking: {"type": "disabled"}`; Groq gpt-oss
  `reasoning_effort: low`; Gemini thinking level set explicitly (off by default on
  gemini-2.5-flash-lite, minimal by default on gemini-3.5-flash-lite); Ollama `think: false`.
- **Own modules:** Claude keeps `AnthropicBackend`, but its user-facing messages become
  provider-named like the others, and it is given its fixed `base_url` explicitly so an
  `ANTHROPIC_BASE_URL` environment variable cannot redirect the key **[review]**. Gemini: native
  `generateContent` with `responseMimeType: "application/json"` and `responseSchema`, key in the
  `x-goog-api-key` header only; **never a key in a URL**, no `?key=` fallback **[review]**. If the
  header turns out not to work, the request fails as "key not accepted" and the code is fixed.
  Ollama: native `/api/chat` with `format` = the schema, `think: false`, `options.num_ctx` at
  least 8192 (Ollama's default is 4,096 tokens on PCs with under 24 GB of graphics memory,
  confirmed; that includes the operator's GTX 1060).
- **HTTP library [review, corrected]:** `httpx2`, which the Anthropic SDK already depends on
  (`httpx` is not installed; measured). Added to `requirements.txt` explicitly, with
  THIRD-PARTY-NOTICES entries for it and for `anthropic`. Clients use `follow_redirects=False`
  (a redirect is an error; nothing is re-sent) and `trust_env=False` (proxy environment variables
  are ignored, so no proxy sees keys or text) **[review, my call]**. No provider SDKs are added.
- **Schema check [review, my call]:** a small hand-written checker for the JSON Schema keywords
  Proofline's own request schemas use (`type`, `properties`, `required`, `additionalProperties`,
  `items`, `enum`); a test fails if any request schema in the app uses another keyword. No
  `jsonschema` dependency. An answer that is not valid JSON or does not match fails as
  "bad_response" with the provider's name in the message.
- **OpenRouter routing:** every request sends `provider.require_parameters: true` and
  `provider.data_collection: "deny"`, plus `HTTP-Referer` and `X-OpenRouter-Title` app headers.
- **Timeouts:** cloud 20 seconds as today; Ollama and Other 120 seconds (the first request loads
  the model). Messages state the timeout that applied, not a fixed "20 seconds" **[review]**.
- **Errors:** messages name the selected provider ("Gemini did not accept the API key."). A new
  "out of credit" message where the provider reports it separately (OpenAI 429 with `error.code`
  `credit_balance_exhausted`; DeepSeek, OpenRouter, Mistral, Gemini 402); it is not in Rephrase's
  retry set. Gemini's bad-key status is ambiguous in Google's docs: 400 with a key-related reason,
  401 and 403 all mean "key not accepted". Unrecognised 4xx answers show the provider's own
  message, as Claude does today. Ollama and Other map 401/403 to "key not accepted" only when a key
  was sent.
- **AiService [review]:** the backend factory takes the provider, its address and its key;
  "a key is saved" and "the key was rejected" are remembered per provider and reset on a provider
  switch; Ollama and keyless Other are never refused with "Add an API key".

## Addresses (Ollama, Other) [review]

- Accepted: `http://` or `https://`, a host, an optional port and path; no `user:password@`,
  query, fragment or spaces; trailing slash normalised. Validated on Save and on load.
- Plain `http://` to anything other than localhost, 127.0.0.1 or [::1] is allowed for text, with
  the warning above. **A key cannot be saved for such an address** (the key box explains: "Use
  https, or turn off the server's key requirement on a trusted network") **[my call]**. Reuses
  `config.is_insecure_remote`, extended to [::1].
- `Config.__repr__` redacts the new address fields with `redact_url`, as it does the LanguageTool
  URL today (the full repr is logged at start-up).

## Keys and settings

- Credential Manager target per provider: `Proofline/<provider>-api-key`. Claude keeps
  `Proofline/anthropic-api-key` (constant `KEY_TARGET` kept, so the publish audit's allow-list
  entries still match; new targets get allow-list entries in the same commit). Tests use
  `ProoflineTest/<provider>-api-key`, never real targets. The key-store functions take the
  provider explicitly.
- `config.json` gains the selected provider (default Claude, so existing installs behave the
  same), each provider's model, and the Ollama and Other addresses, as immutable fields (tuples or
  separate fields, no dicts). **Loading never fails because of them [review]:** an unknown
  provider, malformed model name or bad address is replaced with its default and logged, as an
  unknown `ai_model` is today; today any validation error on load resets every setting, so the new
  fields must be sanitised before validation. Typed model names are validated by shape, not
  against the model table. Existing tests that pin the old behaviour (an unknown model being reset
  or refused) change on purpose.
- **Other's key is bound to its address [extra fix, 2026-10-26].** Saving Other's key stores the
  current `ai_other_url` in `ai_other_key_address` (through the settings page's save). The key is sent
  only while the two are equal, so after a restart a key saved for address A is never sent to B. When
  the address changes, the key is deleted; if the delete fails, `ai_other_key_address` is cleared, the
  key waits for a new Save, and the page says so. The model list is fetched with the same rule.
- The anonymous AI usage counter (`proofline-ai`) is unchanged.

## Logging [review]

No request or response body, header, key, or URL with a query string is logged at any level,
including debug mode. `httpx2` and `httpcore2` stay in `logging_setup.NOISY_LOGGERS` at WARNING.
Tests: each backend runs against an `httpx2.MockTransport` with DEBUG capture, sending a known key
and known text, and neither appears in any log record; a test keeps the noisy loggers at WARNING.

## User-facing text and docs [review]

Every user-facing "Claude" that means "the AI provider" becomes the provider's name or neutral
wording: `ai_client.py` messages, `ai_settings_page.py` (privacy text, key description, switch
description, group title, search keywords), `ai_find.py` ("Asking Claude...", "Claude found
nothing more."), `rephrase.py`, `issue_card.py`, and docstrings. Docs: README (AI section, a
provider table, the Copilot note), `docs/CONFIGURATION.md`, `docs/ARCHITECTURE.md`, CHANGELOG
0.4.0, the project's settings rule. Tests pinned to the old strings change on purpose. README images
of the AI page are regenerated if `scripts/make_screenshots.py` draws it.

## Fact-check of 2026-10-26

The provider details were re-checked, counting a fact as confirmed only if read on an official
page that was actually fetched. Confirmed: chat addresses and key headers (Gemini's header
for `generateContent` excepted), strict JSON schema on OpenAI, Grok, Mistral, Groq (gpt-oss),
OpenRouter, LM Studio and llama.cpp; JSON-object only on DeepSeek; token-count field names for
OpenAI chat, Grok, DeepSeek, Groq, Mistral, Gemini and llama.cpp; the prices in the Models table
except DeepSeek; the out-of-credit codes listed under Errors; training and retention terms for
OpenAI, Grok, Groq, Gemini, and OpenRouter's routing fields. Corrected: Mistral IDs and prices;
OpenRouter's header name; llama.cpp's default port (9931, not 8080); Jan's and LM Studio's keys
are optional. Still unconfirmed: DeepSeek prices and peak hours, Mistral's free-plan training
default, Groq's out-of-credit code, Ollama's errors for an unknown model or over-long input, key
prefixes, whether model-list calls are free.

## Verification before release

A provider counts as tested once **one real request with a real key** passes through the live
test path: one environment variable and one live test per provider (as `tests/test_ai_live.py`
does for Claude), skipped without a key.

**Untested providers ship, labelled [operator]:** "(untested)" after the name in the list, and the
page says "This provider has not been tested with a real account yet. If something does not work,
please report it on GitHub." The label comes off once someone confirms it works. Claude and
Ollama are tested: Ollama passed a live request on 2026-10-26 (qwen2.5:3b on localhost), and
Claude passed a live run on 2026-10-26 after the backend change. Other can be tested on the
operator's PC if a local server is installed (installing one needs the operator's approval). During implementation the builder may re-read
provider pages to settle the unconfirmed items above; what stays unconfirmed ships as
documented, behind the untested label and the schema check. The packaged build is checked for
`httpx2` with the release bytecode scan.

## Branch and release [my call]

Built on a new branch from `ai-step3`, because Find more issues (unreleased, on that branch) must
work with every provider. Both ship together in 0.4.0.

## Left to the builder

- Module names and how provider entries are laid out in code.
- The exact Config field shapes, within the rules above.
- Exact wording of descriptions and messages, within the content given above.
- OpenAI Responses API or chat completions.
- How a live model list shows loading or failure, and how "Other model..." is entered.

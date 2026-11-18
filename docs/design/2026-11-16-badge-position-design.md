# Movable badge, remembered per text box (design, 2026-11-16)

Status: awaiting operator approval. Size: a small change.

## Why

In some text boxes the badge sits on top of the words being typed. The operator wants to drag
the badge out of the way once and have Proofline put it back in that spot every time that box is
used again, regardless of window size, screen resolution or display scaling.

## Goals

- Drag the badge with the left mouse button; a plain click still opens the issues popup.
- On release, save the spot for that box; reuse it whenever the same box has focus again.
- The saved spot follows the box when the window moves or resizes and when the resolution or
  Windows scaling changes.
- A way to return one box to automatic placement, and one to clear every saved spot.

## Non-goals

- Automatic avoidance of the caret (approach C below). Possible later, separately.
- Moving the issues popup, the issue card or the underlines. The popup already opens next to
  the badge's geometry, so it follows the moved badge.

## Anti-goals (a failure even if it works)

- A click that opens the popup gets swallowed as a tiny drag, or a drag opens the popup.
- Typed text, window titles or field names written to `config.json` in readable form.
- Dragging takes focus away from the text box (Proofline would then see a focus change and
  hide the badge).

## Approaches considered

- **A. Drag, remembered per box.** Chosen by the operator 2026-11-16.
- B. Drag, remembered per program: one spot for every box in a program; a spot that suits a
  browser search box is wrong for a comment box. Rejected.
- C. No drag; the badge moves away when the caret comes near it. Does not let the operator
  choose the spot. Rejected for now.

## Design

### Identifying the box (my call; operator can change)

Windows gives no identifier for a text box that survives after it closes (`field_id` is a
UI Automation runtime id, new each time). The key is built from:

`process name | control type | class name (saveable_signature form, so generated web class
lists become *) | AutomationId | page title (browsers only)`

- AutomationId: the reader already reads it (`uia_reader.py`, `automation_id=`); carry it
  into `FieldSnapshot`.
- The element Name is NOT used: Outlook names its message body after the email subject,
  which would make every email a new box.
- Browsers (chrome, msedge, firefox, brave, opera, vivaldi): add the window title with the
  browser's trailing suffix removed (" - Google Chrome", " - Microsoft Edge" including a
  profile segment and "and N more pages", Firefox's suffix). Known limit: a title that changes
  (Gmail "Inbox (3)") counts as a new box. Other programs: no title, so a box keeps its spot
  across documents.
- Stored as a SHA-256 hex digest (first 16 bytes) of the key, never the key itself, so page
  titles do not land in `config.json`.

### Storing the spot

- Anchor = the corner of the box's visible logical rectangle nearest the badge centre at
  release. Offset = badge top-left minus that corner, in logical pixels (`screen_coords`
  already converts physical to logical, which absorbs Windows scaling).
- Placement: corner of the box's current logical rectangle + offset, then clamped so the badge
  is fully inside the screen's available area. A saved spot replaces `badge_position()`'s
  result; with no saved spot, `badge_position()` runs unchanged.
- Config field `badge_positions: tuple[str, ...]`, entries `"<digest>=<corner>:<dx>:<dy>"`,
  corner one of `tl tr bl br`. Added to `Config`, `LIST_FIELDS`, `validate()` (drop malformed
  entries), tests and `docs/CONFIGURATION.md`. At most 200 entries; saving a new one drops
  the oldest. Saved through the app's save handler like other settings.

### Dragging

- `BadgeWidget`: press records the point; movement beyond
  `QApplication.startDragDistance()` starts a drag, which moves the window with the cursor
  and hides the popup. Release without a drag emits `clicked` (today it emits on press).
  Release after a drag emits a new `moved` signal with the final geometry.
- `OverlayController` turns `moved` into an anchor and offset for the current snapshot and
  saves it. While a drag is in progress, redraws caused by caret polls do not move the badge.
- The badge stays a non-activating window (`non_activating.make_non_activating()`); verify
  live that dragging leaves focus in the text box.

### Resetting

- Issues popup: a "Reset badge position" link, shown only when the current box has a saved
  spot. Not a right-click menu, because a `QMenu` may take focus from the box.
- Settings > Appearance: "Reset all badge positions" button (empties `badge_positions`).

## Known limits (accepted 2026-11-16, after plan review)

- Boxes that look identical to UI Automation share one spot: Gmail's compose body and inline
  reply on the same page; every Outlook message body; every Word document; every chat box in
  one Electron app (Teams, Slack, Discord are not treated as browsers because their titles
  change per channel).
- A page title that changes loses the spot, except for a leading or trailing "(N)" counter,
  which is stripped.
- (Fixed 2026-11-16: the key is now an HMAC with a random secret in Credential Manager,
  `badge_secret.py`.) Before that, the hash was unsalted: someone holding `config.json` could confirm a guessed page title, but
  cannot read one. No readable title or typed text is stored.
- The oldest saved spot is dropped first at 200, not the least recently used (refreshing on
  use would write the config on every focus change).
- The spot is fixed to the box, not the text: as the text scrolls, the badge can again sit
  over words being typed (caret avoidance, approach C, stays out of scope).
- A badge dropped over a pinned issues popup covers part of it; the popup is not moved.
- The issues popup's own placement is unchanged; it still opens beside the badge.

## Left to the builder

- Exact browser title suffix rules (cover with tests from real titles).
- Whether clamping should also keep the badge within some distance of the box when the box
  shrinks a lot.
- Tests: key building (browser and non-browser, Outlook body), corner choice, placement after
  the box moves, resizes and changes scaling, clamping, config round trip and pruning, click
  versus drag threshold, no move during a drag. CHANGELOG and README entries.

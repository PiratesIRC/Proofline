"""Keeps the badge and popup in sync with the focused field and the latest check results."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

from PyQt6.QtCore import QObject, QPoint, QRect, pyqtSignal

from proofline.ai_jobs import is_ai_match
from proofline.ai_merge import PendingEdit, merge_with_ai, moved_matches
from proofline.app_names import display_name
from proofline.badge import BADGE_SIZE, BadgeState, BadgeWidget
from proofline.config import Config
from proofline.dictionary import filter_matches, ignore_key
from proofline.issue_card import IssueCard
from proofline.lt_client import Match
from proofline.overlay_widgets import IssuesPopup
from proofline.rephrase import RephraseTarget
from proofline.replace_request import ReplaceRequest
from proofline.screen_coords import (
    ScreenInfo,
    current_screens,
    screen_for,
    to_logical_rect,
)
from proofline.sentences import sentence_span
from proofline.text_snapshot import FieldSnapshot, ScreenRect, word_count
from proofline.underline_overlay import UnderlineOverlay
from proofline.underlines import (
    Underlines,
    UnderlineTarget,
    span_at,
    target_for,
    underlined_matches,
)

log = logging.getLogger(__name__)

BADGE_MARGIN = 4
SINGLE_LINE_MAX_HEIGHT = 56  # taller fields are treated as multi-line
SILENT_STATES = frozenset({BadgeState.CHECKING, BadgeState.CLEAN})
CARD_FALLBACK_MARGIN = 400  # around the anchor when no screen holds it
CHECKING_STATUS = "Checking…"
TOO_SHORT_STATUS = "Nothing to check yet. Keep typing."
NO_FIELD_STATUS = "Click in a text box to check it."

AppNameProvider = Callable[[FieldSnapshot], str]


def friendly_app_name(snapshot: FieldSnapshot) -> str:
    return display_name(snapshot.process_id, snapshot.process_name)


class OverlayController(QObject):
    replace_requested = pyqtSignal(object)  # ReplaceRequest
    disable_app_requested = pyqtSignal(str)  # process name
    disable_window_requested = pyqtSignal(str)  # window title
    settings_requested = pyqtSignal()
    add_word_requested = pyqtSignal(str)  # word for the personal dictionary
    disable_rule_requested = pyqtSignal(str, str)  # LanguageTool rule id, its name
    undo_requested = pyqtSignal(str, str)  # config field, value to remove again
    underline_target_changed = pyqtSignal(object)  # UnderlineTarget | None, for the monitor
    rephrase_requested = pyqtSignal(object)  # RephraseTarget, from the card's Rephrase link
    find_more_requested = pyqtSignal(object)  # FieldSnapshot, from the popup's Find more issues

    def __init__(
        self,
        config_provider: Callable[[], Config],
        badge: BadgeWidget | None = None,
        popup: IssuesPopup | None = None,
        screens_provider: Callable[[], Sequence[ScreenInfo]] = current_screens,
        app_name_provider: AppNameProvider = friendly_app_name,
        underlines: UnderlineOverlay | None = None,
        card: IssueCard | None = None,
        ai_available: Callable[[], bool] = lambda: False,
    ) -> None:
        super().__init__()
        self._config_provider = config_provider
        self._app_name_provider = app_name_provider
        self._badge = badge or BadgeWidget()
        self._popup = popup or IssuesPopup()
        self._underlines = underlines or UnderlineOverlay()
        self._target: UnderlineTarget | None = None
        self._measured: Underlines | None = None  # the latest rectangles for self._target
        self._card = card or IssueCard()
        self._card_held = False  # a rephrase owns the card
        self._card_word: tuple[QRect, QRect] | None = None  # logical word rect and bounds of the card
        self._ai_available = ai_available
        self._screens_provider = screens_provider
        self._snapshot: FieldSnapshot | None = None
        self._server_matches: tuple[Match, ...] = ()  # as returned by the server
        self._matches: tuple[Match, ...] = ()  # after dictionary/ignore/rule filters
        self._ignored: set[tuple[str, str]] = set()  # 'Ignore' clicks, this session only
        self._ai_key: tuple[tuple[int, ...], str] | None = None  # (field_id, text) the AI findings belong to
        self._ai_matches: tuple[Match, ...] = ()
        self._pending_edit: PendingEdit | None = None  # the last correction sent, for moving AI findings
        self._state = BadgeState.CHECKING
        self._message = ""

        self._badge.clicked.connect(self._toggle_popup)
        self._popup.replacement_chosen.connect(self._on_replacement_chosen)
        self._popup.disable_app_requested.connect(self._on_disable_app)
        self._popup.disable_window_requested.connect(self._on_disable_window)
        self._popup.settings_requested.connect(self._on_settings)
        self._popup.ignore_requested.connect(self._on_ignore)
        self._popup.add_word_requested.connect(self._on_add_word)
        self._popup.disable_rule_requested.connect(self._on_disable_rule)
        self._popup.undo_requested.connect(self.undo_requested.emit)
        self._card.replacement_chosen.connect(self._on_replacement_chosen)
        self._card.ignore_requested.connect(self._on_ignore)
        self._card.add_word_requested.connect(self._on_add_word)
        self._card.all_issues_requested.connect(self._show_popup)
        self._card.rephrase_requested.connect(self._on_rephrase_link)
        self._popup.find_more_requested.connect(self._on_find_more)

    @property
    def card(self) -> IssueCard:
        return self._card

    @property
    def popup(self) -> IssuesPopup:
        return self._popup

    def set_ai_matches(self, snapshot: FieldSnapshot, matches: tuple[Match, ...]) -> None:
        """The AI's findings for snapshot's exact text; they replace earlier ones and show with LanguageTool's."""
        current = self._snapshot
        if current is None or (current.field_id, current.text) != (snapshot.field_id, snapshot.text):
            return
        self._ai_key = (snapshot.field_id, snapshot.text)
        self._ai_matches = tuple(matches)
        if self._state in (BadgeState.ISSUES, BadgeState.CLEAN):  # otherwise on_checked merges them
            self._apply_filters()

    def _on_find_more(self) -> None:
        if self._snapshot is not None:
            self.find_more_requested.emit(self._snapshot)

    def _current_ai_matches(self) -> tuple[Match, ...]:
        snapshot = self._snapshot
        if snapshot is None or self._ai_key != (snapshot.field_id, snapshot.text):
            return ()
        return self._ai_matches

    def _carry_ai_matches(self, snapshot: FieldSnapshot) -> None:
        """The text changed: move AI findings across Proofline's own fix, otherwise drop them."""
        edit, self._pending_edit = self._pending_edit, None  # used once
        if self._ai_key is None:
            return
        if (edit is not None and edit.field_id == snapshot.field_id and snapshot.text == edit.new_text
                and self._ai_key == (edit.field_id, edit.old_text)):
            self._ai_matches = moved_matches(self._ai_matches, edit, snapshot.text)
            self._ai_key = (snapshot.field_id, snapshot.text)
        else:
            self._ai_key, self._ai_matches = None, ()

    def hold_card(self, held: bool) -> None:
        """While held, nothing here hides or replaces the card; releasing it refreshes."""
        self._card_held = held
        if not held:
            self.refresh()

    def _hide_card(self) -> None:
        if not self._card_held:
            self._card.hide()

    def on_field_changed(self, snapshot: FieldSnapshot | None) -> None:
        previous = self._snapshot
        self._snapshot = snapshot
        if snapshot is None:
            self._server_matches = ()
            self._matches = ()
            self._sync_underlines()
            self._badge.hide()
            self._release_popup(NO_FIELD_STATUS)
            return
        if previous is None or (previous.field_id, previous.text) != (snapshot.field_id, snapshot.text):
            if self._ai_key != (snapshot.field_id, snapshot.text):
                self._carry_ai_matches(snapshot)
            self._server_matches = ()
            self._matches = ()
            self._set_state(BadgeState.CHECKING)
            self._release_popup(CHECKING_STATUS if self._will_check(snapshot) else TOO_SHORT_STATUS)
        self.refresh()

    def _will_check(self, snapshot: FieldSnapshot) -> bool:
        """The monitor checks a field only once it holds config.min_words words."""
        return word_count(snapshot.text) >= max(1, self._config_provider().min_words)

    def _release_popup(self, status: str) -> None:
        """The listed issues no longer apply: close the popup, or show status if it was dragged."""
        if self._popup.is_notice_only:  # keep Undo reachable after turning off an app
            return
        if self._popup.is_pinned:
            self._popup.show_status(status)
        else:
            self._popup.hide()

    def on_checked(self, snapshot: FieldSnapshot, matches: tuple[Match, ...]) -> None:
        current = self._snapshot
        if current is None or (current.field_id, current.text) != (snapshot.field_id, snapshot.text):
            log.debug("Ignoring results for text that is no longer displayed")
            return
        self._server_matches = tuple(matches)
        self._apply_filters()

    def on_config_changed(self) -> None:
        """Settings changed (dictionary, disabled rules, badge visibility): re-filter and redraw."""
        if self._state in (BadgeState.ISSUES, BadgeState.CLEAN):
            self._apply_filters()
        else:
            self.refresh()

    def _apply_filters(self) -> None:
        config = self._config_provider()
        kept = filter_matches(self._server_matches, config.personal_dictionary, self._ignored)
        disabled = set(config.disabled_rules)
        languagetool = tuple(m for m in kept if m.rule_id not in disabled)
        ai = filter_matches(self._current_ai_matches(), (), self._ignored)  # disabled rules never hide AI
        self._matches = merge_with_ai(languagetool, ai, config.personal_dictionary)
        self._set_state(BadgeState.ISSUES if self._matches else BadgeState.CLEAN)
        self.refresh()
        if self._popup.isVisible() and not self._popup.is_notice_only:
            self._show_popup()

    def _on_ignore(self, match: Match) -> None:
        self._ignored.add(ignore_key(match))
        self._apply_filters()

    def on_check_failed(self, message: str) -> None:
        if self._snapshot is not None:
            self._set_state(BadgeState.ERROR, message)
            self.refresh()

    def refresh(self) -> None:
        """Re-place and redraw the badge, e.g. after the caret moved or settings changed."""
        self._sync_underlines()
        self._update_card()
        snapshot = self._snapshot
        show_silent = self._config_provider().badge_always_visible
        if snapshot is None or (self._state in SILENT_STATES and not show_silent):
            self._badge.hide()
            return
        if self._state is BadgeState.CHECKING and not self._will_check(snapshot):
            # No check will run, so a spinner would never stop (empty search box, chat input).
            self._badge.hide()
            return
        self._badge.set_state(self._state, len(self._matches), self._message)
        self._badge.move(badge_position(snapshot, self._screens_provider()))
        self._badge.show()
        self._badge.raise_()

    def _sync_underlines(self) -> None:
        """Tell the monitor which spans to measure; hide the lines when there are none."""
        wanted = self._state is BadgeState.ISSUES and self._config_provider().show_underlines
        target = target_for(self._snapshot, self._matches) if wanted else None
        if target == self._target:
            return
        self._target = target
        self._measured = None
        if target is None:
            self._underlines.hide()
            self._hide_card()
        self.underline_target_changed.emit(target)

    def on_underlines(self, underlines: Underlines | None) -> None:
        """Draw what the monitor measured, if it still belongs to the current target."""
        if underlines is None or not underlines.matches(self._target):
            self._measured = None
            self._underlines.hide()
            self._hide_card()
            return
        self._measured = underlines
        screens = self._screens_provider()
        words = [to_logical_rect(rect, screens) for rects in underlines.rects for rect in rects]
        # One flag per rectangle: a span that wraps onto two lines has two.
        ai_flags = [is_ai_match(match) for match, rects in zip(underlined_matches(self._matches), underlines.rects)
                    for _ in rects]
        self._underlines.show_underlines(to_logical_rect(underlines.field_rect, screens), words, ai_flags)
        if self._popup.isVisible():
            self._popup.raise_()  # the lines must not draw over the list of issues
        self._badge.raise_()
        self._update_card()

    def _update_card(self) -> None:
        """Show the card for the flagged word holding the caret; hide it otherwise."""
        if self._card_held:
            return
        found = self._match_at_caret()
        if found is None or self._popup.isVisible():
            self._card.hide()
            return
        match, word = found
        logical, bounds = self._logical_and_bounds(word)
        self._card_word = (logical, bounds)
        self._card.show_for(match, logical, bounds, self._config_provider().tray_color, self._ai_available())

    def _logical_and_bounds(self, rect: ScreenRect) -> tuple[QRect, QRect]:
        """rect in logical coordinates, and the available area of the screen holding it."""
        screens = self._screens_provider()
        screen = screen_for(rect.left, rect.top, screens)
        logical = to_logical_rect(rect, screens)
        m = CARD_FALLBACK_MARGIN
        return logical, screen.available if screen else logical.adjusted(-m, -m, m, m)

    def _on_rephrase_link(self, match: Match) -> None:
        snapshot, placed = self._snapshot, self._card_word
        if snapshot is None or placed is None:
            return
        target = self._target_at(snapshot, match.offset, *placed)
        if target is not None:
            self.rephrase_requested.emit(target)

    def rephrase_target(
        self, snapshot: FieldSnapshot, offset: int, anchor: ScreenRect | None
    ) -> RephraseTarget | None:
        """The sentence at offset, with the card under anchor (or the field's corner); None if blank."""
        if anchor is not None:
            logical, bounds = self._logical_and_bounds(anchor)
        else:
            logical, bounds, _accent = self.field_anchor(snapshot)
        return self._target_at(snapshot, offset, logical, bounds)

    def _target_at(
        self, snapshot: FieldSnapshot, offset: int, anchor: QRect, bounds: QRect
    ) -> RephraseTarget | None:
        span = sentence_span(snapshot.text, offset)
        if span is None:
            return None
        return RephraseTarget(snapshot, span[0], span[1], anchor, bounds, self._config_provider().tray_color)

    def field_anchor(self, snapshot: FieldSnapshot) -> tuple[QRect, QRect, str]:
        """A zero-size anchor at the field's top-left corner, its screen's bounds, the accent."""
        corner = ScreenRect(snapshot.field_rect.left, snapshot.field_rect.top,
                            snapshot.field_rect.left, snapshot.field_rect.top)
        logical, bounds = self._logical_and_bounds(corner)
        return logical, bounds, self._config_provider().tray_color

    def _match_at_caret(self) -> tuple[Match, ScreenRect] | None:
        snapshot, measured = self._snapshot, self._measured
        if snapshot is None or snapshot.caret_rect is None or measured is None:
            return None
        if not measured.matches(self._target) or not self._target.applies_to(snapshot):
            return None
        found = span_at(measured, snapshot.caret_rect)
        if found is None:
            return None
        index, word = found
        return underlined_matches(self._matches)[index], word

    def _set_state(self, state: BadgeState, message: str = "") -> None:
        self._state = state
        self._message = message

    def _toggle_popup(self) -> None:
        if self._popup.isVisible() and not self._popup.is_pinned:
            self._popup.hide()
        elif self._snapshot is not None:
            self._show_popup()

    def _show_popup(self) -> None:
        snapshot = self._snapshot
        if snapshot is None:
            return
        self._hide_card()
        screen = screen_for(snapshot.field_rect.left, snapshot.field_rect.top, self._screens_provider())
        bounds = screen.available if screen else self._badge.geometry()
        self._popup.show_issues(
            self._matches, self._app_name_provider(snapshot), self._badge.geometry(), bounds,
            text=snapshot.text, accent=self._config_provider().tray_color,
            # No AI while the server is unreachable: findings would wait for a recheck that never comes.
            ai_available=self._ai_available() and self._state is not BadgeState.ERROR,
        )

    def _on_replacement_chosen(self, match: Match, replacement: str) -> None:
        if self._snapshot is None:
            return
        self.request_replace(ReplaceRequest.build(self._snapshot, match, replacement))

    def request_replace(self, request: ReplaceRequest) -> None:
        """Hand a correction to the monitor's checked replace path, as the card and popup do."""
        self._pending_edit = PendingEdit.from_request(request)
        self._release_popup(CHECKING_STATUS)
        self._set_state(BadgeState.CHECKING)
        self.refresh()
        self.replace_requested.emit(request)

    def apply_first_suggestion(self) -> bool:
        """Keyboard alternative to the popup: apply the first suggestion of the first issue that has one."""
        if self._snapshot is None:
            return False
        for match in self._matches:
            if match.replacements:
                self._on_replacement_chosen(match, match.replacements[0])
                return True
        return False

    def _on_add_word(self, match: Match) -> None:
        word = match.error_text.strip()
        self.add_word_requested.emit(word)
        self._popup.show_notice(f"Added “{word}” to your dictionary.", "personal_dictionary", word)

    def _on_disable_rule(self, match: Match) -> None:
        label = match.short_message or match.category or match.rule_id
        self.disable_rule_requested.emit(match.rule_id, label)
        self._popup.show_notice(f"Turned off “{label}” checks.", "disabled_rules", match.rule_id)

    def _on_disable_app(self) -> None:
        snapshot = self._snapshot
        if snapshot is None:
            return
        self.disable_app_requested.emit(snapshot.process_name)
        name = self._app_name_provider(snapshot)
        self._turned_off(f"Checking is off in {name}.", "disabled_apps", snapshot.process_name)

    def _on_disable_window(self) -> None:
        snapshot = self._snapshot
        if snapshot is None:
            return
        self.disable_window_requested.emit(snapshot.window_title)
        self._turned_off("Checking is off in this window.", "disabled_windows", snapshot.window_title)

    def _turned_off(self, message: str, field: str, value: str) -> None:
        """Forget the field and leave only the Undo notice on screen."""
        self._snapshot = None
        self._server_matches = ()
        self._matches = ()
        self._ai_key, self._ai_matches = None, ()
        self._set_state(BadgeState.CHECKING)
        self._sync_underlines()
        self._badge.hide()
        self._popup.show_notice_only(message, field, value)

    def _on_settings(self) -> None:
        if not self._popup.is_pinned:
            self._popup.hide()
        self.settings_requested.emit()


def badge_position(snapshot: FieldSnapshot, screens: Sequence[ScreenInfo]) -> QPoint:
    """Where to put the badge, in logical coordinates.

    - Single-line fields (search boxes, inputs): just outside the right edge, vertically
      centred, because sites put their own icons (clear, search) inside the right end.
    - Taller fields: inside the bottom-right corner of the visible part.
    - Fields too small or off screen: next to the caret.
    """
    field = to_logical_rect(snapshot.field_rect, screens)
    screen = screen_for(snapshot.field_rect.left, snapshot.field_rect.top, screens)
    visible = field.intersected(screen.available) if screen else field
    if visible.width() >= 2 * BADGE_SIZE and visible.height() > 0:
        centred_y = visible.center().y() - BADGE_SIZE // 2
        if visible.height() <= SINGLE_LINE_MAX_HEIGHT:
            outside_x = visible.right() + BADGE_MARGIN
            if screen is None or outside_x + BADGE_SIZE <= screen.available.right():
                return QPoint(outside_x, centred_y)
            return QPoint(visible.right() - BADGE_SIZE - BADGE_MARGIN, centred_y)
        return QPoint(
            visible.right() - BADGE_SIZE - BADGE_MARGIN,
            visible.bottom() - BADGE_SIZE - BADGE_MARGIN,
        )
    if snapshot.caret_rect is not None:
        caret = to_logical_rect(snapshot.caret_rect, screens)
        return QPoint(caret.right() + BADGE_MARGIN, caret.bottom() - BADGE_SIZE)
    return QPoint(field.right() - BADGE_SIZE, field.bottom() - BADGE_SIZE)

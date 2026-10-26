"""Render the README screenshots from the real widgets, with sample data.

Usage:  .venv\\Scripts\\python.exe scripts\\make_screenshots.py
Writes PNG files to docs/images/. Rendering is offscreen at 2x, so nothing appears on
screen and nothing from this PC (paths, apps, text) ends up in an image.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
os.environ.setdefault("QT_SCALE_FACTOR", "2")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import QApplication, QWidget

APP = QApplication(sys.argv[:1])

from proofline import issue_card, overlay_widgets, tray_flyout, ui_kit
from proofline.ai_jobs import AI_CATEGORY, AI_RULE_ID, AI_SHORT_MESSAGE
from proofline.ai_page_text import usage_text
from proofline.ai_providers import provider
from proofline.ai_usage import Totals
from proofline.badge import BadgeState, BadgeWidget
from proofline.config import Config
from proofline.issue_card import IssueCard
from proofline.lt_client import Match
from proofline.server_test import READY
from proofline.settings_window import SettingsWindow
from proofline.tray import make_icon
from proofline.tray_flyout import FlyoutState, TrayFlyout
from proofline.welcome import WelcomeWindow

OUT = ROOT / "docs" / "images"
SCALE = 2
SAMPLE_TEXT = "Thsi are a quick note to the team. I will send the report tomorow, in order to give everyone time."
MATCHES = (
    Match(0, 4, "Possible spelling mistake found.", "Spelling mistake", ("This", "Thus", "Thin"),
          "MORFOLOGIK_RULE_EN_US", "Possible Typo", "Thsi", "TYPOS"),
    Match(5, 3, "The verb 'are' does not agree with the subject. Did you mean 'is'?", "Grammatical problem",
          ("is",), "THIS_NNS_VB", "Grammar", "are"),
    Match(58, 7, "Possible spelling mistake found.", "Spelling mistake", ("tomorrow",),
          "MORFOLOGIK_RULE_EN_US", "Possible Typo", "tomorow", "TYPOS"),
)
AI_QUOTE = "in order to"
AI_MATCH = Match(SAMPLE_TEXT.index(AI_QUOTE), len(AI_QUOTE), "Wordy: 'to' says the same thing.", AI_SHORT_MESSAGE,
                 ("to",), AI_RULE_ID, AI_CATEGORY, AI_QUOTE, AI_CATEGORY)
STORAGE_HINT = Path("%LOCALAPPDATA%") / "Proofline" / "logs"  # shown instead of this PC's real path


def use_theme(dark: bool) -> None:
    tokens = ui_kit.DARK if dark else ui_kit.LIGHT
    for module in (ui_kit, overlay_widgets, tray_flyout, issue_card):
        module.current_tokens = lambda t=tokens: t


def save(widget: QWidget, name: str, rect: QRect | None = None) -> QImage:
    APP.processEvents()
    image = (widget.grab(rect) if rect else widget.grab()).toImage()
    image.save(str(OUT / name))
    print("wrote", name, image.width(), "x", image.height())
    return image


def popup(dark: bool) -> QImage:
    use_theme(dark)
    widget = overlay_widgets.IssuesPopup()
    widget.show_issues(MATCHES, "Notepad", QRect(900, 700, 30, 30), QRect(0, 0, 1920, 1040), text=SAMPLE_TEXT)
    image = save(widget, f"popup-{'dark' if dark else 'light'}.png")
    widget.hide()
    return image


def flyout(dark: bool) -> None:
    use_theme(dark)
    widget = TrayFlyout()
    widget.set_state(FlyoutState(enabled=True, picky=False, language="auto", server_ok=True,
                                 server_message="Connected to 127.0.0.1", current_app="Notepad",
                                 current_app_status="Checked"))
    widget.show_at(QRect(1800, 1050, 24, 24), QRect(0, 0, 1920, 1040))
    save(widget, f"flyout-{'dark' if dark else 'light'}.png")
    widget.hide()


def settings(dark: bool) -> None:
    use_theme(dark)
    window = SettingsWindow(lambda: Config(), lambda config: config, STORAGE_HINT)
    window.show_settings()
    window.general.show_test_result(READY)
    save(window, f"settings-general-{'dark' if dark else 'light'}.png")
    window.set_update_status("You are up to date (v0.1.0)")
    window.nav.setCurrentRow(window.pages.index(window.advanced))
    save(window, f"settings-advanced-{'dark' if dark else 'light'}.png")
    window.close()


AI_SENTENCE = "Me and him goes to the shop every morning."
AI_OPTIONS = ("He and I go to the shop every morning.", "He and I walk to the shop every morning.")
AI_ACCENT = "#2e7d32"


def ai_rephrase(dark: bool) -> None:
    """The issue card after AI Rephrase: the rewordings, changed words in bold."""
    use_theme(dark)
    card = IssueCard()
    card.show_waiting(AI_SENTENCE, QRect(40, 40, 30, 20), QRect(0, 0, 1920, 1080), AI_ACCENT)
    card.show_options(AI_OPTIONS, AI_SENTENCE)
    save(card, f"ai-rephrase-{'dark' if dark else 'light'}.png")
    card.hide()


def ai_find(dark: bool) -> None:
    """The issues popup after Find more issues: an AI suggestion row, with the AI links open."""
    use_theme(dark)
    widget = overlay_widgets.IssuesPopup()
    widget.show_issues((MATCHES[0], AI_MATCH), "Notepad", QRect(900, 700, 30, 30),
                       QRect(0, 0, 1920, 1040), text=SAMPLE_TEXT, ai_available=True)
    widget._ai_button.click()  # open the AI row (Find more issues)
    save(widget, f"ai-find-{'dark' if dark else 'light'}.png")
    widget.hide()


def ai_settings(dark: bool) -> None:
    """The AI page with a saved key (the key itself is never read: no Credential Manager access)."""
    use_theme(dark)
    window = SettingsWindow(lambda: Config(ai_enabled=True), lambda config: config, STORAGE_HINT)
    window.show_settings()
    window.nav.setCurrentRow(window.pages.index(window.ai))
    window.ai.set_key_saved("anthropic", True)
    window.ai.show_usage(usage_text(provider("anthropic"), "", "", Totals(today=0.0001, month=0.0021, requests_month=12), None, 100))
    save(window, f"ai-settings-{'dark' if dark else 'light'}.png")
    window.close()


def welcome() -> None:
    use_theme(False)
    window = WelcomeWindow(lambda: Config(), lambda config: config)
    window.show()
    window.status.show_result(READY)
    save(window, "welcome.png")
    window._finished = True  # closing a render must not count as the user seeing it
    window.close()


def badges() -> list[QImage]:
    images = []
    for state, count in ((BadgeState.CHECKING, 0), (BadgeState.CLEAN, 0), (BadgeState.ISSUES, 3), (BadgeState.ERROR, 0)):
        badge = BadgeWidget(animations_enabled=lambda: False)
        badge.set_state(state, count)
        badge.show()
        APP.processEvents()
        images.append(badge.grab().toImage())
        badge.hide()
    return images


def badge_strip(images: list[QImage]) -> None:
    labels = ("Checking", "No issues", "3 issues", "Server problem")
    cell_w, height = 150, 96
    strip = QImage(cell_w * len(images) * SCALE, height * SCALE, QImage.Format.Format_ARGB32)
    strip.setDevicePixelRatio(SCALE)
    strip.fill(Qt.GlobalColor.transparent)
    painter = QPainter(strip)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    font = QFont("Segoe UI", 10)
    painter.setFont(font)
    for index, (image, label) in enumerate(zip(images, labels, strict=True)):
        x = index * cell_w
        size = image.width() / image.devicePixelRatio() * 1.6
        target = QRectF(x + (cell_w - size) / 2, 8, size, size)
        painter.drawImage(target, image)
        painter.setPen(QColor("#57606a"))
        painter.drawText(QRectF(x, 66, cell_w, 24), Qt.AlignmentFlag.AlignCenter, label)
    painter.end()
    strip.save(str(OUT / "badge-states.png"))
    print("wrote badge-states.png")


def hero(popup_image: QImage, badge_image: QImage) -> None:
    """A text editor window with the flagged words underlined, the badge, and the issues popup."""
    popup_w = popup_image.width() / popup_image.devicePixelRatio()
    popup_h = popup_image.height() / popup_image.devicePixelRatio()
    editor_w, gap, margin = 560, 36, 24
    width, height = margin + editor_w + gap + popup_w + margin, popup_h + 2 * margin
    canvas = QImage(int(width * SCALE), int(height * SCALE), QImage.Format.Format_ARGB32)
    canvas.setDevicePixelRatio(SCALE)
    canvas.fill(Qt.GlobalColor.transparent)
    p = QPainter(canvas)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    window = QRectF(margin, (height - 300) / 2, editor_w, 300)
    _shadow(p, window, 10)
    p.setPen(QPen(QColor("#d0d7de"), 1))
    p.setBrush(QColor("#ffffff"))
    p.drawRoundedRect(window, 10, 10)
    title_bar = QRectF(window.left(), window.top(), window.width(), 38)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#f3f3f3"))
    p.drawRoundedRect(title_bar, 10, 10)
    p.drawRect(QRectF(title_bar.left(), title_bar.bottom() - 10, title_bar.width(), 10))
    p.setPen(QColor("#1f2328"))
    p.setFont(QFont("Segoe UI", 10))
    p.drawText(title_bar.adjusted(16, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, "Untitled - Notepad")

    text_rect = QRectF(window.left() + 24, window.top() + 60, window.width() - 48, 200)
    _paint_text(p, text_rect)
    badge_size = badge_image.width() / badge_image.devicePixelRatio() * 1.3
    badge_at = QRectF(window.right() - badge_size - 14, window.bottom() - badge_size - 14, badge_size, badge_size)
    p.drawImage(badge_at, badge_image)

    popup_at = QRectF(width - popup_w - margin, margin, popup_w, popup_h)
    _shadow(p, popup_at.adjusted(2, 2, -2, -2), 8)
    p.drawImage(popup_at, popup_image)
    p.end()
    canvas.save(str(OUT / "hero.png"))
    print("wrote hero.png")


def _paint_text(p: QPainter, rect: QRectF) -> None:
    """SAMPLE_TEXT word-wrapped, with every flagged span underlined by a red wave."""
    font = QFont("Segoe UI", 13)
    p.setFont(font)
    metrics = QFontMetricsF(font)
    flagged = [(m.offset, m.offset + m.length) for m in MATCHES]
    x, y = rect.left(), rect.top() + metrics.ascent()
    index = 0
    for word in SAMPLE_TEXT.split(" "):
        advance = metrics.horizontalAdvance(word + " ")
        if x + metrics.horizontalAdvance(word) > rect.right():
            x, y = rect.left(), y + metrics.height() * 1.5
        p.setPen(QColor("#1f2328"))
        p.drawText(QPointF(x, y), word)
        if any(start <= index < end for start, end in flagged):
            _wave(p, x, y + 4, metrics.horizontalAdvance(word))
        x += advance
        index += len(word) + 1


def _wave(p: QPainter, x: float, y: float, length: float) -> None:
    path = QPainterPath(QPointF(x, y))
    step, up = 3.0, True
    pos = x
    while pos < x + length:
        pos += step
        path.lineTo(QPointF(pos, y - 2 if up else y + 1))
        up = not up
    p.setPen(QPen(QColor("#d1242f"), 1.4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)


def _shadow(p: QPainter, rect: QRectF, radius: float) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    for step in range(10, 0, -1):
        p.setBrush(QColor(0, 0, 0, 5))
        p.drawRoundedRect(rect.adjusted(-step, -step + 4, step, step + 4), radius + step, radius + step)


def logo() -> None:
    make_icon("#2e7d32").pixmap(256, 256).save(str(OUT / "logo.png"))
    print("wrote logo.png")


SOCIAL_SIZE = (1280, 640)  # GitHub's recommended social preview size, in pixels
SOCIAL_TAGLINE = ("Grammar and spelling checking", "in every Windows app,", "against a LanguageTool", "server you control.")
SOCIAL_FOOTER = "Free  ·  Open source (GPL-3.0)  ·  Self-hosted"


def social_preview(popup_image: QImage) -> None:
    """The card GitHub, Reddit and chat apps show for a link to the repo (upload it by hand:
    repository Settings › Social preview)."""
    width, height = SOCIAL_SIZE
    canvas = QImage(width, height, QImage.Format.Format_ARGB32)
    canvas.fill(QColor("#f6f8fa"))
    p = QPainter(canvas)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#2e7d32"))
    p.drawRect(QRectF(0, height - 12, width, 12))
    p.drawPixmap(QRectF(80, 96, 112, 112).toRect(), make_icon("#2e7d32").pixmap(224, 224))
    p.setPen(QColor("#1f2328"))
    title = QFont("Segoe UI", 1)
    title.setPixelSize(76)
    title.setBold(True)
    p.setFont(title)
    p.drawText(QPointF(212, 182), "Proofline")
    body = QFont("Segoe UI", 1)
    body.setPixelSize(36)
    p.setFont(body)
    for index, line in enumerate(SOCIAL_TAGLINE):
        p.drawText(QPointF(84, 292 + index * 50), line)
    small = QFont("Segoe UI", 1)
    small.setPixelSize(24)
    p.setFont(small)
    p.setPen(QColor("#57606a"))
    p.drawText(QPointF(84, 560), SOCIAL_FOOTER)
    popup_h = height - 96
    popup_w = popup_image.width() * popup_h / popup_image.height()
    target = QRectF(width - popup_w - 56, 40, popup_w, popup_h)
    _shadow(p, target.adjusted(2, 2, -2, -2), 8)
    p.drawImage(target, popup_image)
    p.end()
    canvas.save(str(OUT / "social-preview.png"))
    print("wrote social-preview.png", width, "x", height)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    logo()
    light_popup = popup(dark=False)
    popup(dark=True)
    for dark in (False, True):
        flyout(dark)
        settings(dark)
        ai_rephrase(dark)
        ai_find(dark)
        ai_settings(dark)
    badge_images = badges()
    badge_strip(badge_images)
    welcome()
    use_theme(False)
    hero(light_popup, badge_images[2])
    social_preview(light_popup)
    return 0


if __name__ == "__main__":
    sys.exit(main())

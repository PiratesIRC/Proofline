"""Find and click the parts of an IssueCard in tests."""

from PyQt6.QtWidgets import QLabel, QPushButton


def link_texts(card):
    return [b.text() for b in card.findChildren(QPushButton, "linkButton") if b.isVisible()]


def click_link(card, text):
    next(b for b in card.findChildren(QPushButton, "linkButton") if b.text() == text and b.isVisible()).click()


def option_buttons(card):
    return [b for b in card.findChildren(QPushButton, "cardFix") if b.isVisible()]


def option_html(button):
    return button.findChild(QLabel, "cardOptionText").text()


def visible_label_texts(card):
    return [label.text() for label in card.findChildren(QLabel) if label.isVisible()]

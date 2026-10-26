from dataclasses import replace

import pytest
from factories import snapshot

from proofline import text_replace
from proofline.checker import GrammarChecker
from proofline.config import Config
from proofline.hidden_chars import (
    INVISIBLE_RULE,
    UNUSUAL_SPACE_RULE,
    codepoint_label,
    hidden_matches,
    merge_matches,
)
from proofline.lt_client import Match
from proofline.overlay_widgets import IssuesPopup, replacement_label
from proofline.replace_request import ReplaceRequest

ZWSP, BOM, SOFT_HYPHEN, RLO, WORD_JOINER = chr(0x200B), chr(0xFEFF), chr(0xAD), chr(0x202E), chr(0x2060)
OBJECT = chr(0xFFFC)  # what Chromium reports for an inline image
# Text read through UI Automation from Slate markup in Edge 156 (measured 2026-10-25): emoji image
# and mention wrapped in U+FEFF, and an empty line holding one.
SLATE_TEXT = ("\n  Hello there, see \n" + BOM + "\n" + OBJECT + "\n and the mention " + BOM + "@someone"
              + BOM + " here.\n  " + BOM + "\n\n")
THIN, EM, NARROW_NBSP, IDEOGRAPHIC = chr(0x2009), chr(0x2003), chr(0x202F), chr(0x3000)
NBSP, ZWJ = chr(0xA0), chr(0x200D)
SERVER_MATCH = Match(0, 4, "msg", "", ("This",), "RULE", "Grammar", "Thsi")


@pytest.mark.parametrize("char", [ZWSP, SOFT_HYPHEN, RLO])
def test_invisible_character_is_flagged_with_remove_fix(char):
    (match,) = hidden_matches("one" + char + "two")
    assert (match.offset, match.length, match.error_text) == (3, 1, char)
    assert match.rule_id == INVISIBLE_RULE
    assert match.replacements == ("",)
    assert f"U+{ord(char):04X}" in match.message


@pytest.mark.parametrize("char", [THIN, EM, NARROW_NBSP, IDEOGRAPHIC])
def test_unusual_space_is_flagged_with_normal_space_fix(char):
    (match,) = hidden_matches("one" + char + "two")
    assert match.rule_id == UNUSUAL_SPACE_RULE
    assert match.replacements == (" ",)
    assert "not a normal space" in match.message


def test_a_run_of_characters_is_one_match():
    (match,) = hidden_matches("a" + ZWSP * 3 + "b")
    assert (match.offset, match.length) == (1, 3)
    assert match.message.startswith("3 invisible characters")
    (spaces,) = hidden_matches("a" + EM * 2 + "b")
    assert spaces.replacements == ("  ",)


def test_editor_placeholders_are_not_flagged():
    assert hidden_matches(SLATE_TEXT) == ()
    assert hidden_matches("Quill " + BOM + OBJECT + BOM + " embed") == ()
    assert hidden_matches("CKEditor ab" + WORD_JOINER * 7 + "cd") == ()
    assert hidden_matches("Lexical typing" + ZWSP) == ()
    assert hidden_matches("widget " + ZWSP + OBJECT + " end") == ()


def test_direction_override_is_flagged_anywhere():
    (match,) = hidden_matches("file " + RLO + " gpj.exe")
    assert match.offset == 5


def test_no_break_space_and_emoji_joiner_are_not_flagged():
    family = chr(0x1F468) + ZWJ + chr(0x1F469)
    assert hidden_matches("10" + NBSP + "kg, plain text " + family) == ()


def test_matches_come_in_text_order():
    found = hidden_matches("a" + THIN + "b" + ZWSP + "c" + EM)
    assert [m.offset for m in found] == [1, 3, 5]
    merged = merge_matches((replace(SERVER_MATCH, offset=2),), found)
    assert [m.offset for m in merged] == [1, 2, 3, 5]


def test_codepoint_label_names_each_character():
    assert codepoint_label(ZWSP + THIN) == "[U+200B][U+2009]"


class FakeClient:
    def check(self, _text):
        return (SERVER_MATCH,)


@pytest.mark.parametrize(("flag", "expected_rules"), [(True, ["RULE", INVISIBLE_RULE]), (False, ["RULE"])])
def test_checker_adds_hidden_matches_only_when_the_setting_is_on(qtbot, flag, expected_rules):
    config = Config(flag_hidden_characters=flag)
    checker = GrammarChecker(lambda: config, lambda _config: FakeClient())
    with qtbot.waitSignal(checker.checked) as blocker:
        checker.check(snapshot(text="Thsi is fi" + ZWSP + "ne."))
    assert [m.rule_id for m in blocker.args[1]] == expected_rules


def test_setting_is_on_by_default():
    assert Config().flag_hidden_characters


@pytest.mark.parametrize(("replacement", "label"), [("", "(remove)"), (" ", "(normal space)"),
                                                    ("   ", "(3 normal spaces)"), ("is", "is")])
def test_replacement_label(replacement, label):
    assert replacement_label(replacement) == label


def test_popup_excerpt_shows_codepoints_for_invisible_characters(qtbot):
    popup = IssuesPopup()
    qtbot.addWidget(popup)
    text = "one" + ZWSP + "two"
    (match,) = hidden_matches(text)
    assert "[U+200B]" in popup._excerpt_label(match).text()


@pytest.mark.parametrize(("replacement", "expected"), [("", ["delete"]), ("is", ["paste is"])])
def test_empty_replacement_deletes_instead_of_pasting(monkeypatch, replacement, expected):
    keys = []

    class Control:
        NativeWindowHandle = 0

        def GetPattern(self, _id):
            return object()

    monkeypatch.setattr(text_replace, "_verified_control", lambda _request: Control())
    monkeypatch.setattr(text_replace, "_select_with_uia", lambda _pattern, _request: None)
    monkeypatch.setattr(text_replace, "paste_text", lambda text: keys.append(f"paste {text}"))
    monkeypatch.setattr(text_replace, "send_delete", lambda: keys.append("delete"))
    text_replace.replace_in_focused_field(ReplaceRequest((1,), "w", "a" + ZWSP + "b", 1, 1, ZWSP, replacement))
    assert keys == expected

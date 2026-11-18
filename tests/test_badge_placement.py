import hashlib
import hmac
import pathlib

from factories import snapshot
from PyQt6.QtCore import QPoint, QRect, QSize

from proofline import badge_placement
from proofline.badge import BADGE_SIZE
from proofline.badge_placement import (
    MAX_SAVED_SPOTS,
    SavedSpot,
    area_for,
    clamp,
    decode,
    encode,
    field_key,
    lookup,
    page_title,
    place,
    spot_for,
    tidy,
    with_spot,
    without_spot,
)
from proofline.screen_coords import ScreenInfo, to_logical_rect
from proofline.text_snapshot import ScreenRect

SECRET = "test-secret"


def field_key_s(snap):
    return field_key(snap, SECRET)


KEY_A = "a" * 32
KEY_B = "b" * 32
BIG = QRect(-10_000, -10_000, 30_000, 30_000)


def test_page_title_strips_browser_suffixes():
    assert page_title("Inbox - Gmail - Google Chrome") == "Inbox - Gmail"
    assert page_title("Docs - Personal - Microsoft Edge") == "Docs - Personal"
    assert page_title("Docs and 3 more pages - Personal - Microsoft Edge") == "Docs - Personal"
    assert page_title("Page \u2014 Mozilla Firefox") == "Page"
    assert page_title("Page - Opera GX") == "Page"
    assert page_title("notes.txt - Notepad") == "notes.txt - Notepad"


def test_page_title_strips_unread_counters():
    assert page_title("Inbox (3) - me@mail.example - Gmail") == "Inbox - me@mail.example - Gmail"
    assert page_title("(12) Chat") == "Chat"
    assert page_title("Report (draft) - Docs") == "Report (draft) - Docs"


def test_key_ignores_title_outside_browsers():
    assert field_key_s(snapshot(window_title="a.txt - Notepad")) == field_key_s(snapshot(window_title="b.txt - Notepad"))


def test_key_uses_page_title_in_browsers():
    def chrome(title, process="chrome.exe"):
        return snapshot(process_name=process, window_title=title)

    assert field_key_s(chrome("A - Google Chrome")) != field_key_s(chrome("B - Google Chrome"))
    assert field_key_s(chrome("Inbox (3) - Gmail - Google Chrome")) == field_key_s(chrome("Inbox (4) - Gmail - Google Chrome"))
    assert field_key_s(chrome("A - Google Chrome", "Chrome.EXE")) != field_key_s(chrome("B - Google Chrome", "Chrome.EXE"))


def test_key_ignores_generated_web_classes():
    assert field_key_s(snapshot(class_name="a b c")) == field_key_s(snapshot(class_name="x y"))
    assert field_key_s(snapshot(class_name="Edit")) != field_key_s(snapshot(class_name="RichEdit"))


def test_key_uses_automation_id():
    assert field_key_s(snapshot(automation_id="to")) != field_key_s(snapshot(automation_id="cc"))


def test_key_is_pinned_digest():
    snap = snapshot(process_name="chrome.exe", control_type="EditControl", class_name="a b",
                    automation_id="body", window_title="Inbox - Gmail - Google Chrome")
    expected = hmac.new(SECRET.encode(), b"chrome.exe|editcontrol|*|body|inbox - gmail", hashlib.sha256).hexdigest()[:32]
    assert field_key_s(snap) == expected


def test_key_depends_on_the_secret():
    snap = snapshot()
    assert field_key(snap, "one") != field_key(snap, "two")
    assert field_key(snap, "one") == field_key(snap, "one")


def test_spot_for_picks_nearest_corner():
    field = QRect(100, 100, 400, 200)  # bottomRight (499, 299)
    assert spot_for(QPoint(470, 270), field) == SavedSpot("br", -29, -29)
    assert spot_for(QPoint(90, 95), field) == SavedSpot("tl", -10, -5)


def test_spot_for_tie_prefers_bottom_right():
    field = QRect(100, 100, 400, 201)  # y 100..300, middle 200
    half = BADGE_SIZE // 2
    assert spot_for(QPoint(499 - half, 200 - half), field).corner == "br"


def test_place_follows_resized_field():
    assert place(SavedSpot("br", -30, -30), QRect(100, 100, 800, 500), (BIG,), BIG) == QPoint(869, 569)


def test_place_keeps_visual_offset_across_scaling():
    primary = ScreenInfo(QRect(0, 0, 1920, 1080), QRect(0, 0, 1920, 1040), 1.0)
    physical = ScreenRect(2000, 100, 2600, 500)
    for scale in (1.0, 1.5):
        second = ScreenInfo(QRect(1920, 0, 1920, 1080), QRect(1920, 0, 1920, 1040), scale)
        field = to_logical_rect(physical, (primary, second))
        placed = place(SavedSpot("br", -40, -40), field, (primary.available, second.available), second.available)
        assert placed == field.bottomRight() + QPoint(-40, -40)
    assert to_logical_rect(physical, (primary, second)).width() == 400  # the 1.5x conversion really ran


def test_place_clamps_to_available_area():
    available = QRect(0, 0, 1920, 1040)
    point = place(SavedSpot("br", 500, 500), QRect(1800, 900, 100, 100), (available,), available)
    rect = QRect(point, QSize(BADGE_SIZE, BADGE_SIZE))
    assert available.contains(rect)
    assert rect.right() == available.right()
    assert rect.bottom() == available.bottom()


def test_clamp_leaves_inside_point_alone():
    assert clamp(QPoint(10, 20), QRect(0, 0, 100, 100)) == QPoint(10, 20)


def test_encode_decode_round_trip():
    spot = SavedSpot("tr", -12, 7)
    assert encode(KEY_A, spot) == f"{KEY_A}=tr:-12:7"
    assert decode(encode(KEY_A, spot)) == (KEY_A, spot)


def test_decode_rejects_malformed():
    for entry in ("zz=br:1:2", f"{KEY_A}=xx:1:2", f"{KEY_A}=br:a:2", "no-equals", f"{'A' * 32}=br:1:2",
                  f"{KEY_A}=br:1", f"{KEY_A}=br:1:2:3"):
        assert decode(entry) is None, entry


def test_lookup_returns_last_match():
    entries = (encode(KEY_A, SavedSpot("br", 1, 1)), encode(KEY_B, SavedSpot("tl", 2, 2)),
               encode(KEY_A, SavedSpot("tr", 3, 3)))
    assert lookup(entries, KEY_A) == SavedSpot("tr", 3, 3)
    assert lookup(entries, "c" * 32) is None


def test_tidy_keeps_last_per_key_and_newest_200():
    a1, b, a2 = encode(KEY_A, SavedSpot("br", 1, 1)), encode(KEY_B, SavedSpot("tl", 0, 0)), encode(KEY_A, SavedSpot("tr", 2, 2))
    assert tidy((a1, "junk", b, a2)) == (b, a2)
    many = tuple(encode(f"{i:032x}", SavedSpot("br", 0, 0)) for i in range(250))
    assert tidy(many) == many[-MAX_SAVED_SPOTS:]


def test_with_spot_replaces_and_moves_last():
    a, b = encode(KEY_A, SavedSpot("br", 1, 1)), encode(KEY_B, SavedSpot("tl", 0, 0))
    assert with_spot((a, b), KEY_A, SavedSpot("bl", 5, 5)) == (b, encode(KEY_A, SavedSpot("bl", 5, 5)))
    full = tuple(encode(f"{i:032x}", SavedSpot("br", 0, 0)) for i in range(MAX_SAVED_SPOTS))
    grown = with_spot(full, KEY_A, SavedSpot("br", 9, 9))
    assert len(grown) == MAX_SAVED_SPOTS and grown[0] == full[1] and grown[-1] == encode(KEY_A, SavedSpot("br", 9, 9))


def test_without_spot_removes_only_that_key():
    a, b = encode(KEY_A, SavedSpot("br", 1, 1)), encode(KEY_B, SavedSpot("tl", 0, 0))
    assert without_spot((a, b), KEY_A) == (b,)


PRIMARY_AREA = QRect(0, 0, 1920, 1040)
SECOND_AREA = QRect(1920, 0, 1920, 1040)


def test_place_keeps_a_spot_on_another_screen():
    field = QRect(1500, 100, 300, 200)  # on the primary screen; topRight (1799, 100)
    point = place(SavedSpot("tr", 300, 50), field, (PRIMARY_AREA, SECOND_AREA), PRIMARY_AREA)
    assert point == QPoint(2099, 150)  # on the second screen, not pulled back onto the primary


def test_place_clamps_into_the_screen_it_lands_on():
    field = QRect(1500, 100, 300, 200)
    point = place(SavedSpot("tr", 300, 5000), field, (PRIMARY_AREA, SECOND_AREA), PRIMARY_AREA)
    assert point == QPoint(2099, 1040 - BADGE_SIZE)


def test_area_for_uses_the_screen_under_or_nearest_the_badge_centre():
    assert area_for(QPoint(1920 - 10, 10), (PRIMARY_AREA, SECOND_AREA), PRIMARY_AREA) == SECOND_AREA  # centre at 1928
    assert area_for(QPoint(-500, -500), (PRIMARY_AREA, SECOND_AREA), SECOND_AREA) == PRIMARY_AREA  # nearest
    assert area_for(QPoint(3000, 9000), (PRIMARY_AREA, SECOND_AREA), PRIMARY_AREA) == SECOND_AREA  # below it
    assert area_for(QPoint(5, 5), (), SECOND_AREA) == SECOND_AREA  # no screens: home


def test_decode_accepts_only_ascii_signed_integers():
    for offsets in ("+5:1", "5_0:1", chr(0x665) + ":1", " 5:1", "5 :1", "-:1"):
        assert decode(f"{KEY_A}=br:{offsets}") is None, offsets
    assert decode(f"{KEY_A}=br:-5:12") == (KEY_A, SavedSpot("br", -5, 12))


def test_placement_source_is_ascii():
    source = pathlib.Path(badge_placement.__file__).read_text(encoding="utf-8")
    assert source.isascii()

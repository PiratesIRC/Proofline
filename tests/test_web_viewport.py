"""A web text box is cut to the browser's page area, so the badge never lands on the toolbar."""

from factories import snapshot
from test_underlines import ARE, Harness

from proofline import uia_reader, web_viewport
from proofline.text_snapshot import ScreenRect
from proofline.web_viewport import clip_to_page

PAGE = ScreenRect(27, 113, 1317, 998)  # Edge's page area, measured 2026-11-26


def test_a_box_partly_behind_the_toolbar_keeps_only_its_visible_part():
    # Edge reported the box at top -160 after a scroll; the page area starts at 113.
    assert clip_to_page(ScreenRect(126, -160, 1372, 215), PAGE) == ScreenRect(126, 113, 1317, 215)


def test_a_box_inside_the_page_is_unchanged():
    box = ScreenRect(126, 215, 1200, 590)
    assert clip_to_page(box, PAGE) == box


def test_a_box_scrolled_out_of_the_page_has_no_visible_part():
    assert clip_to_page(ScreenRect(126, -400, 1200, 100), PAGE) is None
    assert clip_to_page(ScreenRect(126, 998, 1200, 1100), PAGE) is None  # touching is not inside


def test_the_badge_hides_for_a_box_scrolled_out_of_the_page(qtbot):
    h = Harness(qtbot)
    snap = snapshot()
    h.controller.on_field_changed(snap)
    h.controller.on_checked(snap, (ARE,))
    assert h.badge.isVisible()
    gone = snapshot(off_page=True)
    h.controller.on_field_changed(gone)
    h.controller.on_checked(gone, (ARE,))
    assert not h.badge.isVisible()


class FakeControl:
    def __init__(self, framework):
        self.FrameworkId = framework
        self.NativeWindowHandle = 0


def test_only_chromium_boxes_are_cut(monkeypatch):
    monkeypatch.setattr(web_viewport, "page_area", lambda _hwnd: PAGE)
    box = ScreenRect(126, -160, 1372, 215)
    assert uia_reader._visible_field_rect(FakeControl("Chrome"), box) == (ScreenRect(126, 113, 1317, 215), False)
    assert uia_reader._visible_field_rect(FakeControl("Win32"), box) == (box, False)
    gone = ScreenRect(126, -400, 1200, 100)
    assert uia_reader._visible_field_rect(FakeControl("Chrome"), gone) == (gone, True)


def test_a_box_cut_to_a_thin_strip_counts_as_hidden(monkeypatch):
    monkeypatch.setattr(web_viewport, "page_area", lambda _hwnd: PAGE)
    thin = ScreenRect(126, -300, 1200, 113 + web_viewport.MIN_CUT_VISIBLE_PX - 1)
    assert uia_reader._visible_field_rect(FakeControl("Chrome"), thin)[1] is True
    enough = ScreenRect(126, -300, 1200, 113 + web_viewport.MIN_CUT_VISIBLE_PX)
    assert uia_reader._visible_field_rect(FakeControl("Chrome"), enough)[1] is False


def test_a_short_box_that_is_fully_visible_keeps_its_badge(monkeypatch):
    monkeypatch.setattr(web_viewport, "page_area", lambda _hwnd: PAGE)
    search_box = ScreenRect(300, 200, 900, 232)  # 32 px tall, nothing cut
    assert uia_reader._visible_field_rect(FakeControl("Chrome"), search_box) == (search_box, False)


def test_no_page_area_keeps_the_full_box(monkeypatch):
    monkeypatch.setattr(web_viewport, "page_area", lambda _hwnd: None)
    box = ScreenRect(126, -160, 1372, 215)
    assert uia_reader._visible_field_rect(FakeControl("Chrome"), box) == (box, False)

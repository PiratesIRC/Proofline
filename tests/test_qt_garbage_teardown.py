"""A widget left in a reference cycle by one test is freed before Qt processes events again.

Measured 2026-11-13: test objects such as the Harness in test_integration_and_tabs.py hold their
windows in a reference cycle (Harness -> controller -> `lambda: self.config` -> Harness), so only
Python's cyclic collector frees them, at whatever moment it next runs. When that moment fell inside
Qt painting the badge, Qt used the freed widget and Python aborted (access violation in
QWidgetPrivate::shouldPaintOnScreen; a collection forced inside BadgeWidget.paintEvent aborted
3 of 3, one forced before painting 0 of 3). conftest.py collects right after each test body.

The two tests run in file order: the first leaves the cycle, the second checks it is gone.
"""

from __future__ import annotations

import gc
import weakref

import pytest
from PyQt6.QtWidgets import QWidget

_left_behind: list[weakref.ref] = []


class _HoldsItself:
    def __init__(self) -> None:
        self.widget = QWidget()
        self.provider = lambda: self  # the same shape as Harness's `lambda: self.config`


def test_a_leaves_a_shown_widget_in_a_reference_cycle(qtbot):
    holder = _HoldsItself()
    holder.widget.show()
    _left_behind.append(weakref.ref(holder.widget))
    gc.collect()  # holder is still referenced, so this only moves it to the oldest generation


def test_b_that_widget_was_freed_before_this_test_started():
    if not _left_behind:
        pytest.skip("runs only after test_a in the same session")
    assert _left_behind[0]() is None

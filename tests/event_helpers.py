"""Waiting for "nothing happened" without a fixed sleep.

A test that sleeps a fixed time and then asserts that something did not happen can pass on a slow
machine when it should fail: the event simply had not arrived yet. These helpers wait for a point
after which the event, had it been scheduled, must already have run.
"""

from __future__ import annotations

import time

from PyQt6.QtCore import QTimer


class PollCounter:
    """A clock for TextMonitor that counts its polls. The monitor reads the clock once per poll and
    sleeps poll_interval_s between polls, so n polls mean at least n * poll_interval_s has passed,
    however slow the machine is."""

    def __init__(self) -> None:
        self.count = 0

    def __call__(self) -> float:
        self.count += 1
        return time.monotonic()


def wait_for_polls(qtbot, clock: PollCounter, polls: int) -> None:
    """Wait until the monitor has polled `polls` more times, then handle the signals it sent."""
    target = clock.count + polls
    qtbot.waitUntil(lambda: clock.count >= target)
    run_events_posted_so_far(qtbot)


def run_events_posted_so_far(qtbot) -> None:
    """Process every event already in the main thread's queue, then return.

    Signals from finished worker threads and zero-delay QTimer.singleShot calls are posted events,
    handled in the order they were posted, so a marker posted now runs after all of them.
    """
    done = []
    QTimer.singleShot(0, lambda: done.append(True))
    qtbot.waitUntil(lambda: bool(done))

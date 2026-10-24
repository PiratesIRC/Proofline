"""Diagnostic: log what the UIA reader sees for whatever has keyboard focus.

Usage:  python -m proofline.probe [seconds]
Click into different text boxes while it runs; each change of focus, text, or
caret position is logged once.
"""

from __future__ import annotations

import logging
import sys
import time

from proofline.text_snapshot import FocusResult, preview

DEFAULT_SECONDS = 60
POLL_INTERVAL_S = 0.5

log = logging.getLogger("probe")


def format_result(result: FocusResult) -> str:
    lines = [f"FOCUS {result.description}", f"  -> {result.reason}"]
    snapshot = result.snapshot
    if snapshot:
        lines.append(f"  text:   {preview(snapshot.text)}")
        lines.append(f"  window: {snapshot.window_title!r}")
        lines.append(f"  field:  {snapshot.field_rect}")
        lines.append(f"  caret:  {snapshot.caret_rect} via {snapshot.caret_source}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    seconds = float(argv[1]) if len(argv) > 1 else DEFAULT_SECONDS
    from proofline import uia_reader  # after logging setup; sets DPI awareness

    log.info("Probing focused element for %.0f s. Click into text boxes now.", seconds)
    last = ""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        report = format_result(uia_reader.read_focused_field())
        if report != last:
            log.info("\n%s", report)
            last = report
        time.sleep(POLL_INTERVAL_S)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

"""Every tracked text file must be free of mojibake and invisible characters.

Both crept in on 2026-10-24/25: Bash heredocs re-encoded UTF-8 text as cp1252 (an ellipsis
became three Latin-1 characters, and a test asserted the garbled string and passed), and a
zero-width character list was written as literal invisible characters instead of escapes.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEXT_SUFFIXES = {".py", ".md", ".txt", ".json", ".toml", ".ini", ".iss", ".ps1", ".spec", ".yml", ".cfg"}

# UTF-8 lead bytes (U+00C2..U+00F4) read as cp1252, followed by a continuation byte read the same
# way: either Latin-1 U+0080..U+00BF or one of the cp1252 specials that 0x80..0x9F map to.
CP1252_SPECIALS = (0x152, 0x153, 0x160, 0x161, 0x178, 0x17D, 0x17E, 0x192, 0x2C6, 0x2DC, 0x2013, 0x2014,
                   0x2018, 0x2019, 0x201A, 0x201C, 0x201D, 0x201E, 0x2020, 0x2021, 0x2022, 0x2026,
                   0x2030, 0x2039, 0x203A, 0x20AC, 0x2122)
CONTINUATION = "".join(chr(c) for c in range(0x80, 0xC0)) + "".join(chr(c) for c in CP1252_SPECIALS)
MOJIBAKE = re.compile("[" + chr(0xC2) + "-" + chr(0xF4) + "][" + re.escape(CONTINUATION) + "]")
INVISIBLE = re.compile("[" + "".join(chr(c) for c in (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0xAD,
                                                      0x2028, 0x2029)) + "]")


def tracked_text_files() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git is not available")
    return [ROOT / name for name in out.splitlines() if Path(name).suffix.lower() in TEXT_SUFFIXES]


def problems(text: str) -> list[str]:
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        for pattern, label in ((MOJIBAKE, "mojibake"), (INVISIBLE, "invisible character")):
            for match in pattern.finditer(line):
                codes = " ".join(f"U+{ord(c):04X}" for c in match.group(0))
                found.append(f"line {number}: {label} {codes}")
    return found


def test_detector_catches_garbled_and_invisible_text():
    ellipsis, rsaquo = chr(0x2026), chr(0x203A)
    assert problems(("Checking" + ellipsis).encode("utf-8").decode("cp1252"))
    assert problems(rsaquo.encode("utf-8").decode("cp1252"))
    assert problems("one" + chr(0x200B) + "two")
    assert not problems("Settings " + rsaquo + " Checking" + ellipsis + " caf" + chr(0xE9) + " " + chr(0x2715))


def test_tracked_files_have_no_mojibake_or_invisible_characters():
    files = tracked_text_files()
    assert len(files) > 50  # control: the scan really reads the repository
    report = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        report += [f"{path.relative_to(ROOT)} {problem}" for problem in problems(text)]
    assert not report, "\n".join(report)

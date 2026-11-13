"""Every tracked text file must be free of mojibake and invisible characters.

Both crept in on 2026-10-24/25: Bash heredocs re-encoded UTF-8 text as cp1252 (an ellipsis
became three Latin-1 characters, and a test asserted the garbled string and passed), and a
zero-width character list was written as literal invisible characters instead of escapes.
"""

from __future__ import annotations

import os
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


# Without git (a source zip), the files are found by walking the folder, leaving out these.
SKIPPED_FOLDERS = {".git", ".venv", "venv", "build", "dist", "__pycache__", ".pytest_cache", ".ruff_cache",
                   "node_modules"}


def _walked_files() -> list[str]:
    names = []
    for folder, subfolders, files in os.walk(ROOT):
        subfolders[:] = [name for name in subfolders if name not in SKIPPED_FOLDERS]  # not entered at all
        names.extend((Path(folder) / name).relative_to(ROOT).as_posix() for name in files)
    return names


def tracked_text_files() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        names = out.splitlines()
    except (OSError, subprocess.CalledProcessError):
        names = _walked_files()
    return [ROOT / name for name in names if Path(name).suffix.lower() in TEXT_SUFFIXES]


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


def test_files_are_still_found_without_git(monkeypatch):
    def no_git(*args, **kwargs):
        raise OSError("git is not installed")

    monkeypatch.setattr(subprocess, "run", no_git)
    try:
        files = tracked_text_files()
    except pytest.skip.Exception:
        pytest.fail("the check was skipped instead of reading the files")
    names = {path.relative_to(ROOT).as_posix() for path in files}
    assert "tests/test_source_text.py" in names
    assert "README.md" in names
    assert not any(name.split("/")[0] in SKIPPED_FOLDERS for name in names)


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

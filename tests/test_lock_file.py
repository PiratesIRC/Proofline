"""requirements-lock.txt (exact versions and hashes for release builds) and scripts/check_lock.py."""

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "requirements-lock.txt"


@pytest.fixture
def check_lock():
    spec = importlib.util.spec_from_file_location("check_lock", ROOT / "scripts" / "check_lock.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _names(path: Path) -> set[str]:
    names = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            names.add(re.split(r"[<>=!~\[ ]", line, maxsplit=1)[0].lower().replace("_", "-"))
    return names


def test_lock_pins_every_runtime_and_build_requirement(check_lock):
    pins = check_lock.read_lock(LOCK)
    assert _names(ROOT / "requirements.txt") | _names(ROOT / "requirements-build.txt") <= set(pins)


def test_every_pin_has_a_hash():
    text = LOCK.read_text(encoding="utf-8")
    for block in re.split(r"\n(?=\S)", text):
        if "==" in block and not block.startswith("#"):
            assert "--hash=sha256:" in block, block.splitlines()[0]


def test_read_lock_normalises_names(check_lock, tmp_path):
    lock = tmp_path / "lock.txt"
    lock.write_text("# comment\nPyQt6_sip==13.13.0 \\n    --hash=sha256:ab\n", encoding="utf-8")
    assert check_lock.read_lock(lock) == {"pyqt6-sip": "13.13.0"}


def test_differences_names_missing_and_changed_packages(check_lock):
    pins = {"pyqt6": "6.11.0", "requests": "2.34.2", "anthropic": "2.3.0"}
    installed = {"pyqt6": "6.11.0", "requests": "2.35.0"}
    assert check_lock.differences(pins, installed) == [
        "anthropic: locked 2.3.0, not installed",
        "requests: locked 2.34.2, installed 2.35.0",
    ]


def test_this_venv_matches_the_lock(check_lock):
    assert check_lock.differences(check_lock.read_lock(LOCK), check_lock.installed_versions()) == []

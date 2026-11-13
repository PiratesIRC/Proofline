"""packaging/THIRD-PARTY-NOTICES.txt names every third-party package the build bundles.

scripts/check_notices.py reads the built exe and fails the build when a bundled package is
missing from the notices; these tests cover its logic and the files it depends on.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NOTICES = ROOT / "packaging" / "THIRD-PARTY-NOTICES.txt"
SPEC = ROOT / "packaging" / "Proofline.spec"
BUILD = ROOT / "packaging" / "build.ps1"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def check_notices():
    return _load("check_notices")


def test_reports_a_bundled_package_missing_from_the_notices(check_notices) -> None:
    owners = {"requests": ["requests"], "idna": ["idna"]}
    missing, unknown = check_notices.problems({"requests", "idna"}, "  requests  Apache-2.0\n", owners)
    assert missing == ["idna"]
    assert unknown == []


def test_compares_package_names_the_way_pip_does(check_notices) -> None:
    owners = {"pydantic_core": ["pydantic_core"], "typing_extensions": ["typing-extensions"]}
    notices = "  pydantic-core  MIT\n  typing_extensions  PSF-2.0\n"
    assert check_notices.problems({"pydantic_core", "typing_extensions"}, notices, owners) == ([], [])


def test_a_name_inside_another_name_does_not_count(check_notices) -> None:
    # "pydantic" appears inside "pydantic-core"; the notices must still list pydantic itself.
    missing, _ = check_notices.problems({"pydantic"}, "  pydantic-core  MIT\n", {"pydantic": ["pydantic"]})
    assert missing == ["pydantic"]


def test_every_package_behind_a_module_is_required(check_notices) -> None:
    owners = {"PyQt6": ["PyQt6", "PyQt6-Qt6", "PyQt6_sip"]}
    missing, _ = check_notices.problems({"PyQt6"}, "  PyQt6  GPL-3.0\n  PyQt6-sip  GPL-3.0\n", owners)
    assert missing == ["pyqt6-qt6"]


def test_loose_pywin32_modules_belong_to_pywin32(check_notices) -> None:
    # pywin32 installs win32con.py and friends outside its package folders, so the installed
    # metadata does not name an owner for them.
    missing, unknown = check_notices.problems({"win32con", "winerror"}, "  pywin32  PSF\n", {})
    assert (missing, unknown) == ([], [])


def test_pyinstaller_startup_helpers_belong_to_pyinstaller(check_notices) -> None:
    missing, unknown = check_notices.problems({"_pyi_rth_utils"}, "", {})
    assert (missing, unknown) == (["pyinstaller"], [])


def test_standard_library_and_the_app_itself_are_ignored(check_notices) -> None:
    assert check_notices.problems({"json", "zoneinfo", "proofline"}, "", {}) == ([], [])


def test_a_module_with_no_known_owner_is_reported(check_notices) -> None:
    assert check_notices.problems({"mystery"}, "", {}) == ([], ["mystery"])


def test_notices_list_every_runtime_package_in_the_lock() -> None:
    check_lock = _load("check_lock")
    check_notices = _load("check_notices")
    runtime = set(check_lock.read_lock()) - check_notices.BUILD_ONLY
    listed = check_notices.listed_names(NOTICES.read_text(encoding="utf-8"))
    assert sorted(runtime - listed) == []


def test_build_only_packages_are_in_the_lock() -> None:
    # A stale entry here would hide a runtime package from the check above.
    check_lock = _load("check_lock")
    check_notices = _load("check_notices")
    assert sorted(check_notices.BUILD_ONLY - set(check_lock.read_lock())) == []


def test_notices_cover_the_pyinstaller_bootloader() -> None:
    assert "bootloader" in NOTICES.read_text(encoding="utf-8")


def test_spec_leaves_out_packages_the_app_never_uses() -> None:
    # setuptools comes in through a PyInstaller hook and brings packaging, jaraco, wheel and
    # others; pygments comes in through httpx2's command-line tool. Both are present in the
    # development environment only, so a build would otherwise depend on what tools are installed.
    text = SPEC.read_text(encoding="utf-8")
    for name in ('"setuptools"', '"pkg_resources"', '"distutils"', '"pygments"'):
        assert name in text


def test_build_runs_the_notices_check() -> None:
    assert "scripts\\check_notices.py" in BUILD.read_text(encoding="utf-8")

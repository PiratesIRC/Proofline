"""The PyInstaller spec bundles modules that are imported too late for PyInstaller to find."""

from __future__ import annotations

from pathlib import Path

SPEC = Path(__file__).resolve().parent.parent / "packaging" / "Proofline.spec"


def test_spec_bundles_win32timezone() -> None:
    # win32cred.CredRead imports win32timezone at call time to build LastWritten; without it the
    # packaged app saves the API key but can never read it back (0.3.0).
    assert '"win32timezone"' in SPEC.read_text(encoding="utf-8")

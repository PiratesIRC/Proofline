"""Check that the running Python environment has exactly the versions in requirements-lock.txt.

packaging/build.ps1 runs this before a build, so a release is built from the locked versions:
  .venv\\Scripts\\python.exe scripts\\check_lock.py
Exit status 0 when every locked package is installed at its locked version, 1 otherwise.
Packages installed but not locked (pytest, ruff) are ignored.
"""

from __future__ import annotations

import re
import sys
from importlib import metadata
from pathlib import Path

LOCK_PATH = Path(__file__).resolve().parent.parent / "requirements-lock.txt"
PIN_PATTERN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s\\;]+)")
INSTALL_HINT = "Install the locked versions: .venv\\Scripts\\python.exe -m pip install --require-hashes -r requirements-lock.txt"


def normalise(name: str) -> str:
    """A package name as pip compares it (PEP 503): lower case, runs of - _ . as one -."""
    return re.sub(r"[-_.]+", "-", name).lower()


def read_lock(path: Path = LOCK_PATH) -> dict[str, str]:
    """{normalised name: version} for each `name==version` line of a lock file."""
    pins = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        found = PIN_PATTERN.match(line)
        if found:
            pins[normalise(found.group(1))] = found.group(2)
    return pins


def installed_versions() -> dict[str, str]:
    return {normalise(dist.metadata["Name"]): dist.version for dist in metadata.distributions()}


def differences(pins: dict[str, str], installed: dict[str, str]) -> list[str]:
    """One line per locked package that is missing or at another version, sorted by name."""
    problems = []
    for name, version in sorted(pins.items()):
        have = installed.get(name)
        if have is None:
            problems.append(f"{name}: locked {version}, not installed")
        elif have != version:
            problems.append(f"{name}: locked {version}, installed {have}")
    return problems


def main() -> int:
    problems = differences(read_lock(), installed_versions())
    for problem in problems:
        print(problem)
    if problems:
        print(INSTALL_HINT)
        return 1
    print("Installed packages match requirements-lock.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())

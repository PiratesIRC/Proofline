"""Check that packaging/THIRD-PARTY-NOTICES.txt names every third-party package in a built exe.

packaging/build.ps1 runs this after PyInstaller:
  .venv\\Scripts\\python.exe scripts\\check_notices.py dist\\Proofline\\Proofline.exe packaging\\THIRD-PARTY-NOTICES.txt
It reads the top-level module names from the exe's compressed module archive, finds the installed
package (distribution) that provides each one, and exits 1 when a package is missing from the
notices or a module has no known owner. Modules that exist only as compiled extensions (.pyd)
outside a package are not in that archive and are not checked.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping
from importlib import metadata
from pathlib import Path

APP_PACKAGE = "proofline"
# In requirements-lock.txt but used only to build, never bundled (the spec excludes setuptools).
BUILD_ONLY = frozenset({
    "altgraph", "packaging", "pefile", "pyinstaller", "pyinstaller-hooks-contrib",
    "pywin32-ctypes", "setuptools",
})
# pywin32 installs these modules outside its package folders, so its metadata names no owner.
PYWIN32_LOOSE = re.compile(r"^(win32\w*|winerror|pywin32_\w+|pythoncom|pywintypes)$")
# PyInstaller adds its own startup helpers (runtime hooks) to the bundle.
PYINSTALLER_HELPER = re.compile(r"^_?pyi_\w+$")
# A notices entry: an indented line whose first column is the package name.
ENTRY = re.compile(r"^ {2}(\S+)", re.MULTILINE)


def normalise(name: str) -> str:
    """A package name as pip compares it (PEP 503): lower case, runs of - _ . as one -."""
    return re.sub(r"[-_.]+", "-", name).lower()


def listed_names(notices: str) -> set[str]:
    """The normalised package names in the first column of the notices' entries."""
    return {normalise(name) for name in ENTRY.findall(notices)}


def _owners(module: str, module_owner: Mapping[str, list[str]]) -> list[str] | None:
    if module in module_owner:
        return module_owner[module]
    if PYWIN32_LOOSE.match(module):
        return ["pywin32"]
    if PYINSTALLER_HELPER.match(module):
        return ["pyinstaller"]
    return None


def problems(
    modules: set[str], notices: str, module_owner: Mapping[str, list[str]]
) -> tuple[list[str], list[str]]:
    """(packages missing from the notices, modules with no known owner), both sorted."""
    listed = listed_names(notices)
    missing: set[str] = set()
    unknown: set[str] = set()
    for module in modules:
        if module == APP_PACKAGE or module in sys.stdlib_module_names:
            continue
        owners = _owners(module, module_owner)
        if owners is None:
            unknown.add(module)
            continue
        missing.update(normalise(owner) for owner in owners if normalise(owner) not in listed)
    return sorted(missing), sorted(unknown)


def bundled_modules(exe: Path) -> set[str]:
    """Top-level module names in the exe's compressed module archive (PYZ)."""
    from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader

    archive = CArchiveReader(str(exe))
    pyz_name = next(name for name in archive.toc if name.endswith(".pyz"))
    # TOC offsets are relative to the start of the package inside the exe.
    position = archive._start_offset + archive.toc[pyz_name][0]
    pyz = ZlibArchiveReader(f"{exe}?{position}")
    return {name.split(".")[0] for name in pyz.toc}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_notices.py <Proofline.exe> <THIRD-PARTY-NOTICES.txt>")
        return 2
    exe, notices_path = Path(argv[0]), Path(argv[1])
    modules = bundled_modules(exe)
    missing, unknown = problems(modules, notices_path.read_text(encoding="utf-8"),
                                metadata.packages_distributions())
    print(f"Checked {len(modules)} top-level modules in {exe.name} against {notices_path.name}")
    if missing:
        print("Bundled but missing from the notices: " + ", ".join(missing))
    if unknown:
        print("Bundled modules with no known package (add an owner or exclude them): " + ", ".join(unknown))
    return 1 if missing or unknown else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

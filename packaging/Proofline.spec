# PyInstaller spec: a windowed, one-folder build of Proofline.
# Build with packaging/build.ps1, which also creates the icon and the zip.

from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

ROOT = Path(SPECPATH).parent
NAME = "Proofline"
DISPLAY_NAME = "Proofline"
ICON = ROOT / "build" / "app.ico"

namespace = {}
exec((ROOT / "proofline" / "__init__.py").read_text(encoding="utf-8"), namespace)
VERSION = namespace["__version__"]
VERSION_TUPLE = tuple(int(part) for part in VERSION.split(".")) + (0,)

version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=VERSION_TUPLE, prodvers=VERSION_TUPLE),
    kids=[
        StringFileInfo([
            StringTable("040904B0", [
                StringStruct("CompanyName", "PiratesIRC"),
                StringStruct("FileDescription", DISPLAY_NAME),
                StringStruct("FileVersion", VERSION),
                StringStruct("InternalName", NAME),
                StringStruct("OriginalFilename", f"{NAME}.exe"),
                StringStruct("ProductName", DISPLAY_NAME),
                StringStruct("ProductVersion", VERSION),
            ])
        ]),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    # uiautomation loads its helper DLLs from its own bin folder.
    binaries=collect_dynamic_libs("uiautomation", destdir="uiautomation/bin"),
    # comtypes wrappers for UIAutomationCore, generated in the venv, so the exe
    # never has to generate them at runtime. win32cred.CredRead imports
    # win32timezone when called, too late for PyInstaller to see it.
    hiddenimports=collect_submodules("comtypes.gen") + ["win32timezone"],
    excludes=["tkinter", "pytest", "pytestqt", "_pytest", "ruff"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NAME,
    console=False,
    icon=str(ICON) if ICON.exists() else None,
    version=version_info,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name=NAME, upx=False)

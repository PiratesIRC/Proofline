"""Friendly app names ("Microsoft Edge" instead of msedge.exe) from an executable's version info.

Safe to import on any thread: only ctypes and pywin32, no UI Automation.
"""

from __future__ import annotations

import ctypes
import logging
import os
from ctypes import wintypes
from functools import lru_cache

import pywintypes
import win32api

log = logging.getLogger(__name__)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PATH_BUFFER_CHARS = 1024
TRANSLATION_KEY = "\\VarFileInfo\\Translation"
DESCRIPTION_KEY = "\\StringFileInfo\\{:04x}{:04x}\\FileDescription"
FALLBACK_TRANSLATION = (0x0409, 0x04B0)  # US English, Unicode: what most apps ship
MAX_NAME_CHARS = 40

_kernel32 = ctypes.windll.kernel32


def display_name(process_id: int, process_name: str) -> str:
    """The app's own description of itself, or process_name if there is none.

    The executable's file name must still match process_name, so a reused process ID
    never names the wrong app.
    """
    path = process_path(process_id)
    if not path or os.path.basename(path).casefold() != process_name.casefold():
        return process_name
    return file_description(path) or process_name


@lru_cache(maxsize=256)
def process_path(pid: int) -> str:
    handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(PATH_BUFFER_CHARS)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not _kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return ""
        return buffer.value
    finally:
        _kernel32.CloseHandle(handle)


@lru_cache(maxsize=128)
def file_description(exe_path: str) -> str:
    """FileDescription from the version resource, trimmed; '' if missing or unreadable."""
    try:
        translations = win32api.GetFileVersionInfo(exe_path, TRANSLATION_KEY) or [FALLBACK_TRANSLATION]
        for language, codepage in (*translations, FALLBACK_TRANSLATION):
            description = win32api.GetFileVersionInfo(exe_path, DESCRIPTION_KEY.format(language, codepage))
            if isinstance(description, str) and description.strip():
                return description.strip()[:MAX_NAME_CHARS]
    except pywintypes.error as exc:
        log.debug("No version information in %s: %s", exe_path, exc)
    return ""

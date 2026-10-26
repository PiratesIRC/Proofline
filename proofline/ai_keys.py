"""The Claude API key, kept in Windows Credential Manager (never in config.json or the log)."""

from __future__ import annotations

import logging

import pywintypes
import win32cred

log = logging.getLogger(__name__)

KEY_TARGET = "Proofline/anthropic-api-key"
KEY_USER = "Proofline"
ERROR_NOT_FOUND = 1168
QUOTES = "\"'"


def clean_key(text: str) -> str:
    """The key without surrounding whitespace or one pair of quotes, as pasted keys often have."""
    key = text.strip()
    if len(key) >= 2 and key[0] == key[-1] and key[0] in QUOTES:
        key = key[1:-1].strip()
    return key


def save_key(key: str, target: str = KEY_TARGET) -> None:
    """Store key under target, replacing any saved one; ValueError when it is empty."""
    cleaned = clean_key(key)
    if not cleaned:
        raise ValueError("The API key is empty.")
    win32cred.CredWrite({
        "Type": win32cred.CRED_TYPE_GENERIC,
        "TargetName": target,
        "UserName": KEY_USER,
        "CredentialBlob": cleaned,
        "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
    }, 0)
    log.info("API key saved")


def load_key(target: str = KEY_TARGET) -> str | None:
    try:
        credential = win32cred.CredRead(target, win32cred.CRED_TYPE_GENERIC, 0)
    except pywintypes.error as exc:
        if exc.winerror == ERROR_NOT_FOUND:
            return None
        raise
    blob = credential["CredentialBlob"]
    return blob.decode("utf-16-le") if isinstance(blob, bytes) else str(blob)


def delete_key(target: str = KEY_TARGET) -> None:
    """Remove the saved key; nothing happens when none is saved."""
    try:
        win32cred.CredDelete(target, win32cred.CRED_TYPE_GENERIC, 0)
    except pywintypes.error as exc:
        if exc.winerror != ERROR_NOT_FOUND:
            raise
        return
    log.info("API key removed")


def has_key(target: str = KEY_TARGET) -> bool:
    return load_key(target) is not None

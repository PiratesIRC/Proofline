"""The AI provider API keys, one per provider, kept in Windows Credential Manager (never in config.json or the log)."""

from __future__ import annotations

import logging

import pywintypes
import win32cred

from proofline.ai_providers import key_target

log = logging.getLogger(__name__)

KEY_TARGET = key_target("anthropic")
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


def load_provider_key(pid: str) -> str | None:
    """The API key saved for provider pid, or None when none is saved."""
    return load_key(key_target(pid))


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


class KeyStore:
    """One API key per provider, kept under prefix/<provider>-api-key in Credential Manager.

    The app uses the default prefix; tests pass ProoflineTest so no real entry is touched.
    """

    def __init__(self, prefix: str = "Proofline") -> None:
        self._prefix = prefix

    def save(self, pid: str, key: str) -> None:
        """Store key for pid, replacing any saved one; ValueError when it is empty."""
        save_key(key, key_target(pid, self._prefix))

    def load(self, pid: str) -> str | None:
        return load_key(key_target(pid, self._prefix))

    def delete(self, pid: str) -> None:
        delete_key(key_target(pid, self._prefix))

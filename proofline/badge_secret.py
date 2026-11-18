"""The secret mixed into saved badge-position keys, kept in Windows Credential Manager.

config.json (and a diagnostics report, which can include the saved positions) holds only keyed
hashes; without this secret nobody can test a guessed page title against them.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable

import win32cred

from proofline.ai_keys import KEY_USER, load_key

log = logging.getLogger(__name__)

SECRET_TARGET = "Proofline/badge-position-key"
SECRET_BYTES = 32


def _write(target: str, secret: str) -> None:
    win32cred.CredWrite({
        "Type": win32cred.CRED_TYPE_GENERIC,
        "TargetName": target,
        "UserName": KEY_USER,
        "CredentialBlob": secret,
        "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
    }, 0)


def load_secret(
    target: str = SECRET_TARGET,
    read: Callable[[str], str | None] = load_key,
    write: Callable[[str, str], None] = _write,
) -> str:
    """The saved secret, created on first use. If Credential Manager fails, a secret for this
    session only, so dragging still works but the spots are not found after a restart."""
    try:
        secret = read(target)
        if secret:
            return secret
        secret = secrets.token_hex(SECRET_BYTES)
        write(target, secret)
        log.info("Created the badge position key")
        return secret
    except Exception as exc:  # noqa: BLE001 - any store failure: degrade, never stop the badge
        log.warning("Could not read or save the badge position key (%s); saved badge positions will not "
                    "be found after a restart", type(exc).__name__)
        return secrets.token_hex(SECRET_BYTES)

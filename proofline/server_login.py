"""The LanguageTool server login (the user:password part of the server address), kept in
Windows Credential Manager instead of config.json.

The app still works with one address string that holds the login. Only the file differs: when
settings are saved, the login is taken out of the address and stored under a credential named
for the server's host and port; when settings are loaded, it is put back for that same host
and port only. A file from an older version, with the login still in it, is read as before and
rewritten without it.

If Credential Manager cannot be written, the login stays in config.json (as before 0.4.8) and a
warning is logged: a server the user cannot reach any more would be worse than the old storage.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse, urlunparse

import win32cred

from proofline.ai_keys import KEY_USER, delete_key, load_key

log = logging.getLogger(__name__)

TARGET_PREFIX = "Proofline"
TARGET_NAME = "server-login"
# "://user:password@" in any text, for scrubbing a file that could not be parsed
LOGIN_IN_TEXT = re.compile(r"(://)[^/@\s\"']*@")


def split_login(url: str) -> tuple[str, str]:
    """(the address without its login, the login as written: "user:password" or "")."""
    parsed = urlparse(url)
    login, at, host = parsed.netloc.rpartition("@")
    if not at:
        return url, ""
    return urlunparse(parsed._replace(netloc=host)), login


def join_login(url: str, login: str) -> str:
    """The address with login put in front of its host; unchanged when login is empty."""
    if not login:
        return url
    parsed = urlparse(url)
    return urlunparse(parsed._replace(netloc=f"{login}@{parsed.netloc}"))


def host_key(url: str) -> str:
    """The host and port a login belongs to, lower-cased; "" when the address has none."""
    return split_login(url)[0] and urlparse(split_login(url)[0]).netloc.casefold()


def scrub_logins(text: str) -> str:
    """text with every "user:password@" after "://" removed (for a backup of an unreadable file)."""
    return LOGIN_IN_TEXT.sub(r"\1", text)


class LoginStore:
    """One login per server host and port, under prefix/server-login/<host:port>.

    The app uses the default prefix; tests pass ProoflineTest so no real entry is touched.
    """

    def __init__(self, prefix: str = TARGET_PREFIX) -> None:
        self._prefix = prefix

    def _target(self, host: str) -> str:
        return f"{self._prefix}/{TARGET_NAME}/{host}"

    def save(self, host: str, login: str) -> None:
        win32cred.CredWrite({
            "Type": win32cred.CRED_TYPE_GENERIC,
            "TargetName": self._target(host),
            "UserName": KEY_USER,
            "CredentialBlob": login,
            "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
        }, 0)

    def load(self, host: str) -> str | None:
        return load_key(self._target(host))

    def delete(self, host: str) -> None:
        delete_key(self._target(host))


def stored_address(url: str, store: LoginStore | None) -> str:
    """The address to write to config.json: without its login once the store holds it.

    An address without a login removes any login stored for that host, so a login the user
    deleted from the address does not come back at the next start.
    """
    if store is None:
        return url
    bare, login = split_login(url)
    host = host_key(url)
    try:
        if login:
            store.save(host, login)
        elif host:
            store.delete(host)
    except Exception:  # noqa: BLE001 - any Credential Manager failure keeps the old storage
        log.warning("Could not use Credential Manager for the server login; it stays in the settings file")
        return url
    return bare


def loaded_address(url: str, store: LoginStore | None) -> str:
    """The address the app works with: the file's address with its stored login put back."""
    if store is None or split_login(url)[1]:
        return url
    try:
        login = store.load(host_key(url))
    except Exception:  # noqa: BLE001 - unreadable store: the server will answer that a login is needed
        log.warning("Could not read the server login from Credential Manager")
        return url
    return join_login(url, login or "")

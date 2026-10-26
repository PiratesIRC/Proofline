"""Create a GitHub release for Proofline and upload its files, each verified by download.

Usage:
  .venv\\Scripts\\python.exe scripts\\gh_release.py show v0.2.2
  .venv\\Scripts\\python.exe scripts\\gh_release.py create v0.2.3 notes.md ^
      dist\\Proofline-0.2.3-setup.exe dist\\Proofline-0.2.3-portable.zip

`create` titles the release "Proofline <version>" and stops if the tag is not on origin yet
(GitHub would otherwise create the tag from the default branch, so push the tag first).
The token comes from `git credential fill` for github.com and is never printed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

DESCRIPTION = "Create a GitHub release for Proofline and upload its files, each verified by download."
REPO = "PiratesIRC/Proofline"
API = f"https://api.github.com/repos/{REPO}"
USER_AGENT = "proofline-release"


def github_token() -> str:
    out = subprocess.run(
        ["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
        capture_output=True, text=True, check=True,
    ).stdout
    fields = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    if not fields.get("password"):
        sys.exit("git credential fill returned no token for github.com")
    return fields["password"]


def request(method: str, url: str, token: str, data: bytes | None = None,
            content_type: str = "application/json") -> dict[str, Any]:
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "Content-Type": content_type, "User-Agent": USER_AGENT,
    })
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read() or b"null")


def tag_exists(tag: str) -> bool:
    out = subprocess.run(["git", "ls-remote", "origin", f"refs/tags/{tag}"],
                         capture_output=True, text=True, check=True).stdout
    return bool(out.strip())


def show(tag: str, token: str) -> None:
    release = request("GET", f"{API}/releases/tags/{tag}", token)
    print(release["name"], release["html_url"], "draft" if release["draft"] else "published")
    print(release["body"])
    for asset in release["assets"]:
        print(f"asset {asset['name']} {asset['size']} bytes")


def upload_verified(upload_url: str, path: Path, token: str) -> bool:
    """Upload one file, download it back, and compare sha256."""
    data = path.read_bytes()
    local = hashlib.sha256(data).hexdigest()
    asset = request("POST", f"{upload_url}?name={path.name}", token, data, "application/octet-stream")
    req = urllib.request.Request(asset["browser_download_url"], headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req) as response:
        remote = hashlib.sha256(response.read()).hexdigest()
    print(f"{path.name} {asset['size']} bytes sha256 {local} download match: {local == remote}")
    return local == remote


def create(tag: str, notes: Path, files: list[Path], token: str) -> bool:
    if not tag_exists(tag):
        sys.exit(f"tag {tag} is not on origin; push it first")
    missing = [str(f) for f in files if not f.is_file()]
    if missing:
        sys.exit(f"missing files: {', '.join(missing)}")
    body = json.dumps({
        "tag_name": tag, "name": f"Proofline {tag.removeprefix('v')}",
        "body": notes.read_text(encoding="utf-8"), "draft": False, "prerelease": False,
    }).encode("utf-8")
    release = request("POST", f"{API}/releases", token, body)
    print("release:", release["html_url"])
    upload_url = release["upload_url"].split("{")[0]
    # A list, not a generator: upload and check every file even when an earlier one fails.
    return all([upload_verified(upload_url, f, token) for f in files])  # noqa: C419


def main() -> int:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show").add_argument("tag")
    create_parser = sub.add_parser("create")
    create_parser.add_argument("tag")
    create_parser.add_argument("notes", type=Path)
    create_parser.add_argument("files", type=Path, nargs="+")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # release notes hold characters cp1252 cannot encode
    token = github_token()
    if args.command == "show":
        show(args.tag, token)
        return 0
    return 0 if create(args.tag, args.notes, args.files, token) else 1


if __name__ == "__main__":
    sys.exit(main())

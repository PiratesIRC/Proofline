"""Create a GitHub release for Proofline and upload its files, each verified by download.

Usage:
  .venv\\Scripts\\python.exe scripts\\gh_release.py show v0.2.2
  .venv\\Scripts\\python.exe scripts\\gh_release.py sums dist\\SHA256SUMS.txt <file> <file>
  .venv\\Scripts\\python.exe scripts\\gh_release.py create v0.2.3 notes.md ^
      dist\\Proofline-0.2.3-setup.exe dist\\Proofline-0.2.3-portable.zip

`create` titles the release "Proofline <version>" and stops if the tag is not on origin yet
(GitHub would otherwise create the tag from the default branch, so push the tag first), or if
the tag, `proofline.__version__` and the newest CHANGELOG version heading differ, or if the
files do not include a SHA256SUMS.txt (written by `sums`, which packaging/build.ps1 runs) that
lists every other file with its current sha256. The release
is created as a draft, each file is uploaded and verified by download, and only then is the
release published; after a failed upload it stays a draft (delete or fix it on GitHub).
The token comes from `git credential fill` for github.com and is never printed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DESCRIPTION = "Create a GitHub release for Proofline and upload its files, each verified by download."
REPO = "PiratesIRC/Proofline"
API = f"https://api.github.com/repos/{REPO}"
USER_AGENT = "proofline-release"
ROOT = Path(__file__).resolve().parent.parent
SUMS_NAME = "SHA256SUMS.txt"
VERSION_PATTERN = re.compile(r'^__version__ = "([^"]+)"', re.MULTILINE)


def version_problems(tag: str, root: Path = ROOT) -> list[str]:
    """Why the tag does not match proofline.__version__ and a CHANGELOG heading; [] when it does."""
    version = tag.removeprefix("v")
    problems = []
    found = VERSION_PATTERN.search((root / "proofline" / "__init__.py").read_text(encoding="utf-8"))
    if not found or found.group(1) != version:
        problems.append(f"proofline.__version__ is {found.group(1) if found else 'missing'}, not {version}")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    if not re.search(rf"^## {re.escape(version)} \(", changelog, re.MULTILINE):
        problems.append(f"CHANGELOG.md has no heading '## {version} (date)'")
    return problems


def write_sums(sums: Path, files: list[Path]) -> None:
    """SHA256SUMS.txt in the format `sha256sum -c` reads: digest, two spaces, file name."""
    lines = [f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.name}" for f in files]
    sums.write_text("".join(line + "\n" for line in lines), encoding="ascii", newline="\n")


def sums_problems(files: list[Path]) -> list[str]:
    """Why the release files lack a matching SHA256SUMS.txt; [] when it lists each one correctly."""
    sums = [f for f in files if f.name == SUMS_NAME]
    if not sums:
        return [f"{SUMS_NAME} is not among the files"]
    listed: dict[str, str] = {}  # file name -> sha256
    for line in sums[0].read_text(encoding="ascii").splitlines():
        digest, separator, name = line.partition("  ")
        if separator:
            listed[name] = digest
    problems = []
    for f in files:
        if f.name != SUMS_NAME and listed.get(f.name) != hashlib.sha256(f.read_bytes()).hexdigest():
            problems.append(f"{f.name} is missing from {SUMS_NAME} or has changed since it was written")
    return problems


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


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def download_asset(asset_id: int, token: str) -> bytes:
    """A draft's file through the API (drafts have no public download link). GitHub answers with
    a redirect to signed storage, fetched without the token: the storage refuses a second login."""
    req = urllib.request.Request(f"{API}/releases/assets/{asset_id}", headers={
        "Authorization": f"Bearer {token}", "Accept": "application/octet-stream", "User-Agent": USER_AGENT,
    })
    try:
        with urllib.request.build_opener(_NoRedirect).open(req) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        if exc.code not in (301, 302, 307, 308):
            raise
        location = exc.headers["Location"]
    with urllib.request.urlopen(urllib.request.Request(location, headers={"User-Agent": USER_AGENT})) as response:
        return response.read()


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
    remote = hashlib.sha256(download_asset(asset["id"], token)).hexdigest()
    print(f"{path.name} {asset['size']} bytes sha256 {local} download match: {local == remote}")
    return local == remote


def create(tag: str, notes: Path, files: list[Path], token: str) -> bool:
    problems = version_problems(tag)
    if problems:
        sys.exit("version mismatch: " + "; ".join(problems))
    problems = sums_problems(files)
    if problems:
        sys.exit("checksums: " + "; ".join(problems))
    if not tag_exists(tag):
        sys.exit(f"tag {tag} is not on origin; push it first")
    missing = [str(f) for f in files if not f.is_file()]
    if missing:
        sys.exit(f"missing files: {', '.join(missing)}")
    body = json.dumps({
        "tag_name": tag, "name": f"Proofline {tag.removeprefix('v')}",
        "body": notes.read_text(encoding="utf-8"), "draft": True, "prerelease": False,
    }).encode("utf-8")
    release = request("POST", f"{API}/releases", token, body)
    print("draft release:", release["html_url"])
    upload_url = release["upload_url"].split("{")[0]
    # A list, not a generator: upload and check every file even when an earlier one fails.
    if not all([upload_verified(upload_url, f, token) for f in files]):  # noqa: C419
        print("not published: a file did not verify; the release is still a draft")
        return False
    published = request("PATCH", f"{API}/releases/{release['id']}", token, json.dumps({"draft": False}).encode())
    print("published:", published["html_url"])
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show").add_argument("tag")
    sums_parser = sub.add_parser("sums")
    sums_parser.add_argument("sums", type=Path)
    sums_parser.add_argument("files", type=Path, nargs="+")
    create_parser = sub.add_parser("create")
    create_parser.add_argument("tag")
    create_parser.add_argument("notes", type=Path)
    create_parser.add_argument("files", type=Path, nargs="+")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # release notes hold characters cp1252 cannot encode
    if args.command == "sums":
        write_sums(args.sums, args.files)
        print(f"wrote {args.sums}")
        return 0
    token = github_token()
    if args.command == "show":
        show(args.tag, token)
        return 0
    return 0 if create(args.tag, args.notes, args.files, token) else 1


if __name__ == "__main__":
    sys.exit(main())

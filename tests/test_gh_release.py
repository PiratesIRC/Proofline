"""scripts/gh_release.py: version checks and the draft-then-publish order. No network is used."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "gh_release.py"


@pytest.fixture
def gh_release():
    spec = importlib.util.spec_from_file_location("gh_release", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_repo(root: Path, version: str, heading: str) -> Path:
    (root / "proofline").mkdir()
    (root / "proofline" / "__init__.py").write_text(f'__version__ = "{version}"\n', encoding="utf-8")
    (root / "CHANGELOG.md").write_text(f"# Changelog\n\n{heading}\n\n- a fix\n", encoding="utf-8")
    return root


def test_matching_tag_version_and_changelog_pass(gh_release, tmp_path):
    root = make_repo(tmp_path, "0.4.4", "## 0.4.4 (2026-11-12)")
    assert gh_release.version_problems("v0.4.4", root) == []


@pytest.mark.parametrize(("version", "heading"), [
    ("0.4.3", "## 0.4.4 (2026-11-12)"),  # __version__ not bumped
    ("0.4.4", "## Unreleased"),  # CHANGELOG heading not renamed
    ("0.4.4", "## 0.4.40 (2026-11-12)"),  # a heading that only starts with the version
])
def test_a_mismatch_is_reported(gh_release, tmp_path, version, heading):
    root = make_repo(tmp_path, version, heading)
    assert gh_release.version_problems("v0.4.4", root)


class FakeGitHub:
    """Records API calls; uploads verify unless their file name is in `bad`."""

    def __init__(self, bad=()):
        self.calls = []
        self.bad = set(bad)

    def request(self, method, url, token, data=None, content_type="application/json"):
        self.calls.append((method, url, json.loads(data) if data and content_type.endswith("json") else None))
        if method == "POST" and url.endswith("/releases"):
            return {"id": 7, "html_url": "https://example.invalid/r", "upload_url": "https://up.invalid/a{?name}"}
        return {"html_url": "https://example.invalid/r"}

    def upload_verified(self, upload_url, path, token):
        self.calls.append(("UPLOAD", path.name, None))
        return path.name not in self.bad


@pytest.fixture
def release_files(tmp_path):
    files = [tmp_path / "Proofline-0.4.4-setup.exe", tmp_path / "Proofline-0.4.4-portable.zip"]
    for f in files:
        f.write_bytes(b"x")
    notes = tmp_path / "notes.md"
    notes.write_text("notes", encoding="utf-8")
    return notes, files


def run_create(gh_release, monkeypatch, fake, release_files):
    monkeypatch.setattr(gh_release, "request", fake.request)
    monkeypatch.setattr(gh_release, "upload_verified", fake.upload_verified)
    monkeypatch.setattr(gh_release, "tag_exists", lambda tag: True)
    monkeypatch.setattr(gh_release, "version_problems", lambda tag, root=None: [])
    monkeypatch.setattr(gh_release, "sums_problems", lambda files: [])
    notes, files = release_files
    return gh_release.create("v0.4.4", notes, files, "token")


def test_release_is_created_as_draft_and_published_after_every_upload(gh_release, monkeypatch, release_files):
    fake = FakeGitHub()
    assert run_create(gh_release, monkeypatch, fake, release_files)
    method, _url, body = fake.calls[0]
    assert (method, body["draft"]) == ("POST", True)
    assert [c[0] for c in fake.calls] == ["POST", "UPLOAD", "UPLOAD", "PATCH"]
    assert fake.calls[-1][2] == {"draft": False}


def test_a_failed_upload_leaves_the_release_a_draft(gh_release, monkeypatch, release_files):
    fake = FakeGitHub(bad={"Proofline-0.4.4-setup.exe"})
    assert not run_create(gh_release, monkeypatch, fake, release_files)
    assert "PATCH" not in [c[0] for c in fake.calls]


def test_create_refuses_a_version_mismatch_before_any_request(gh_release, monkeypatch, release_files):
    fake = FakeGitHub()
    monkeypatch.setattr(gh_release, "request", fake.request)
    monkeypatch.setattr(gh_release, "tag_exists", lambda tag: True)
    monkeypatch.setattr(gh_release, "version_problems", lambda tag, root=None: ["__version__ is 0.4.3"])
    notes, files = release_files
    with pytest.raises(SystemExit):
        gh_release.create("v0.4.4", notes, files, "token")
    assert fake.calls == []


def test_sums_file_lists_each_file_with_its_sha256(gh_release, tmp_path):
    a, b = tmp_path / "Proofline-0.4.4-setup.exe", tmp_path / "Proofline-0.4.4-portable.zip"
    a.write_bytes(b"setup")
    b.write_bytes(b"zip")
    sums = tmp_path / "SHA256SUMS.txt"
    gh_release.write_sums(sums, [a, b])
    import hashlib

    assert sums.read_text(encoding="ascii").splitlines() == [
        f"{hashlib.sha256(b'setup').hexdigest()}  Proofline-0.4.4-setup.exe",
        f"{hashlib.sha256(b'zip').hexdigest()}  Proofline-0.4.4-portable.zip",
    ]


def test_sums_problems_accepts_a_matching_sums_file(gh_release, release_files):
    _notes, files = release_files
    sums = files[0].with_name("SHA256SUMS.txt")
    gh_release.write_sums(sums, files)
    assert gh_release.sums_problems([*files, sums]) == []


def test_sums_problems_reports_a_missing_sums_file(gh_release, release_files):
    _notes, files = release_files
    assert gh_release.sums_problems(files)


def test_sums_problems_reports_a_file_changed_after_the_sums(gh_release, release_files):
    _notes, files = release_files
    sums = files[0].with_name("SHA256SUMS.txt")
    gh_release.write_sums(sums, files)
    files[0].write_bytes(b"rebuilt")
    assert gh_release.sums_problems([*files, sums])


def test_create_refuses_bad_sums_before_any_request(gh_release, monkeypatch, release_files):
    fake = FakeGitHub()
    monkeypatch.setattr(gh_release, "request", fake.request)
    monkeypatch.setattr(gh_release, "tag_exists", lambda tag: True)
    monkeypatch.setattr(gh_release, "version_problems", lambda tag, root=None: [])
    notes, files = release_files
    with pytest.raises(SystemExit):
        gh_release.create("v0.4.4", notes, files, "token")  # no SHA256SUMS.txt among the files
    assert fake.calls == []

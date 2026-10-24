import json

import pytest
import requests

from proofline.update_check import (
    FAILURE_TTL_S,
    SUCCESS_TTL_S,
    VersionInfo,
    cached_info,
    check_for_update,
    compare_versions,
    fetch_latest_version,
)

NOW = 1_800_000_000.0


class FakeResponse:
    def __init__(self, status=200, payload=None, bad_json=False):
        self.status_code = status
        self._payload = payload if payload is not None else {}
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("not json")
        return self._payload


def getter(response=None, error=None, calls=None):
    def get(url, headers, timeout):
        if calls is not None:
            calls.append((url, headers, timeout))
        if error:
            raise error
        return response
    return get


# ----- comparison ------------------------------------------------------------

def test_latest_greater_is_outdated():
    info = compare_versions("0.1.0", "0.2.0")
    assert info.status == "outdated"
    assert info.message == "Update available: 0.2.0 (current: v0.1.0)"
    assert info.latest == "0.2.0"


@pytest.mark.parametrize(("current", "latest"), [("0.2.0", "0.2.0"), ("v0.2.0", "0.2.0"), ("0.2.0", "v0.2.0")])
def test_equal_versions_are_current(current, latest):
    info = compare_versions(current, latest)
    assert info.status == "current"
    assert info.message == "You are up to date (v0.2.0)"


def test_local_build_newer_than_release_is_current():
    assert compare_versions("0.3.0", "v0.2.9").status == "current"


@pytest.mark.parametrize(("current", "latest", "status"), [
    ("1.26.2971048", "1.26.2971931", "outdated"),
    ("1.26.2971931", "1.26.2971048", "current"),
    ("0.9.0", "0.10.0", "outdated"),  # numeric, not string, comparison
])
def test_calver_and_multi_digit_parts_compare_numerically(current, latest, status):
    assert compare_versions(current, latest).status == status


def test_unparseable_version_is_unknown_with_both_shown():
    info = compare_versions("0.1.0", "nightly")
    assert info.status == "unknown"
    assert "nightly" in info.message and "0.1.0" in info.message


# ----- fetching --------------------------------------------------------------

def test_fetch_reads_tag_name_with_user_agent_and_timeout():
    calls = []
    assert fetch_latest_version(getter(FakeResponse(payload={"tag_name": "v1.2.3"}), calls=calls)) == "v1.2.3"
    url, headers, timeout = calls[0]
    assert url.endswith("/repos/PiratesIRC/Proofline/releases/latest")
    assert headers["User-Agent"] and timeout == 10


@pytest.mark.parametrize("get", [
    getter(FakeResponse(status=404)),
    getter(error=requests.ConnectionError("offline")),
    getter(error=requests.Timeout("slow")),
    getter(FakeResponse(payload={"name": "no tag"})),
    getter(FakeResponse(bad_json=True)),
])
def test_fetch_failures_return_none_without_raising(get):
    assert fetch_latest_version(get) is None


# ----- caching ---------------------------------------------------------------

def fetcher(result, calls):
    def fetch():
        calls.append(1)
        return result
    return fetch


def test_failure_gives_unavailable_and_is_cached(tmp_path):
    path = tmp_path / "version_check.json"
    info = check_for_update("0.1.0", path, NOW, fetcher(None, []))
    assert info == VersionInfo("unknown", "Version check unavailable (v0.1.0)")
    assert json.loads(path.read_text(encoding="utf-8"))["version_info"]["status"] == "unknown"


def test_success_cache_reused_for_24_hours(tmp_path):
    path, calls = tmp_path / "version_check.json", []
    check_for_update("0.1.0", path, NOW, fetcher("0.2.0", calls))
    info = check_for_update("0.1.0", path, NOW + SUCCESS_TTL_S - 1, fetcher("0.3.0", calls))
    assert len(calls) == 1 and info.latest == "0.2.0"
    info = check_for_update("0.1.0", path, NOW + SUCCESS_TTL_S + 1, fetcher("0.3.0", calls))
    assert len(calls) == 2 and info.latest == "0.3.0"


def test_failure_cache_reused_for_2_hours(tmp_path):
    path, calls = tmp_path / "version_check.json", []
    check_for_update("0.1.0", path, NOW, fetcher(None, calls))
    check_for_update("0.1.0", path, NOW + FAILURE_TTL_S - 1, fetcher("0.2.0", calls))
    assert len(calls) == 1
    info = check_for_update("0.1.0", path, NOW + FAILURE_TTL_S + 1, fetcher("0.2.0", calls))
    assert len(calls) == 2 and info.status == "outdated"


def test_changed_installed_version_forces_a_recheck(tmp_path):
    path, calls = tmp_path / "version_check.json", []
    check_for_update("0.1.0", path, NOW, fetcher("0.2.0", calls))
    info = check_for_update("0.2.0", path, NOW + 60, fetcher("0.2.0", calls))
    assert len(calls) == 2 and info.status == "current"


def test_corrupt_cache_is_treated_as_missing(tmp_path):
    path, calls = tmp_path / "version_check.json", []
    path.write_text("{not json", encoding="utf-8")
    assert cached_info("0.1.0", path) is None
    check_for_update("0.1.0", path, NOW, fetcher("0.1.0", calls))
    assert len(calls) == 1


def test_cache_write_is_atomic_and_leaves_no_temp_files(tmp_path):
    path = tmp_path / "version_check.json"
    check_for_update("0.1.0", path, NOW, fetcher("0.2.0", []))
    assert [p.name for p in tmp_path.iterdir()] == ["version_check.json"]


def test_cached_info_reads_without_fetching(tmp_path):
    path = tmp_path / "version_check.json"
    assert cached_info("0.1.0", path) is None
    check_for_update("0.1.0", path, NOW, fetcher("0.2.0", []))
    assert cached_info("0.1.0", path).status == "outdated"
    assert cached_info("0.2.0", path) is None  # cached for another installed version


# ----- background checker ----------------------------------------------------

def test_checker_runs_in_background_and_announces_a_new_version_once(qtbot, tmp_path):
    from proofline.update_check import UpdateChecker

    results = iter([VersionInfo("outdated", "Update available: 0.2.0 (current: v0.1.0)", "0.2.0")] * 2)
    checker = UpdateChecker(lambda: True, "0.1.0", tmp_path / "c.json", check=lambda current, path: next(results))
    announced = []
    checker.newer_version.connect(announced.append)
    with qtbot.waitSignal(checker.checked) as first:
        checker.check_now()
    assert first.args[0].status == "outdated"
    with qtbot.waitSignal(checker.checked):
        checker.check_now()
    assert announced == ["0.2.0"]


def test_checker_does_nothing_when_turned_off(tmp_path):
    from proofline.update_check import UpdateChecker

    calls = []
    checker = UpdateChecker(lambda: False, "0.1.0", tmp_path / "c.json", check=lambda *a: calls.append(a))
    checker.check_now()
    assert calls == []


def test_forced_check_ignores_a_fresh_cache(tmp_path):
    path, calls = tmp_path / "version_check.json", []
    check_for_update("0.1.0", path, NOW, fetcher("0.1.0", calls))
    info = check_for_update("0.1.0", path, NOW + 60, fetcher("0.2.0", calls), force=True)
    assert len(calls) == 2 and info.status == "outdated"


def test_manual_check_runs_even_when_automatic_checks_are_off(qtbot, tmp_path):
    from proofline.update_check import UpdateChecker

    seen = []

    def check(current, path, force=False):
        seen.append(force)
        return VersionInfo("current", "You are up to date (v0.1.0)", "0.1.0")

    checker = UpdateChecker(lambda: False, "0.1.0", tmp_path / "c.json", check=check)
    checker.check_now()
    assert seen == []
    with qtbot.waitSignal(checker.checked):
        checker.check_now(force=True)
    assert seen == [True]

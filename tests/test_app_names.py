import os

from proofline import app_names
from proofline.app_names import display_name, file_description


def test_display_name_reads_the_running_executable_description():
    exe = os.path.basename(__import__("sys").executable)
    assert display_name(os.getpid(), exe)  # some description or the exe name, never empty


def test_display_name_falls_back_when_exe_name_does_not_match():
    assert display_name(os.getpid(), "other.exe") == "other.exe"


def test_display_name_falls_back_for_missing_process():
    assert display_name(0, "ghost.exe") == "ghost.exe"


def test_file_description_of_missing_file_is_empty():
    assert file_description(r"C:\does\not\exist.exe") == ""


def test_file_description_of_notepad():
    assert file_description(os.path.expandvars(r"%WINDIR%\System32\notepad.exe")) == "Notepad"


class FakeKernel32:
    """OpenProcess fails while `path` is ''; otherwise the process image is `path`."""

    def __init__(self):
        self.path = ""

    def OpenProcess(self, _access, _inherit, _pid):
        return 1 if self.path else 0

    def QueryFullProcessImageNameW(self, _handle, _flags, buffer, _size):
        buffer.value = self.path
        return 1

    def CloseHandle(self, _handle):
        return 1


def test_a_reused_process_id_gets_the_new_program_path(monkeypatch):
    fake = FakeKernel32()
    monkeypatch.setattr(app_names, "_kernel32", fake)
    fake.path = r"C:\Apps\first.exe"
    assert app_names.process_path(4242) == r"C:\Apps\first.exe"
    fake.path = r"C:\Apps\second.exe"  # the first program exited; Windows reused its id
    assert app_names.process_path(4242) == r"C:\Apps\second.exe"


def test_a_failed_lookup_is_not_remembered(monkeypatch):
    fake = FakeKernel32()
    monkeypatch.setattr(app_names, "_kernel32", fake)
    assert app_names.process_path(4243) == ""
    fake.path = r"C:\Apps\later.exe"
    assert app_names.process_path(4243) == r"C:\Apps\later.exe"

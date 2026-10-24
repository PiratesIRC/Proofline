import os

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

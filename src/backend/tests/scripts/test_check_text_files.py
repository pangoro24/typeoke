"""Tests for scripts/check_text_files.py.

Sensitive-looking values are built at run time so this file holds no literal match.
"""

from pathlib import Path

import pytest

from tests.scripts.loader import load_script

checker = load_script("check_text_files")

FAKE_EMAIL = "someone" + "@" + "example.invalid"
FAKE_ACCOUNT = "".join(["0000", "0000", "0000"])
FAKE_KEY_ID = "AK" + "IA" + "0" * 16
FAKE_TEMP_KEY_ID = "AS" + "IA" + "Z" * 16
KEY_HEADER = "-----" + "BEGIN RSA PRIVATE" + " KEY-----"


def write(directory: Path, name: str, data: bytes) -> str:
    path = directory / name
    path.write_bytes(data)
    return str(path)


def run(paths: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code: int = checker.main(paths)
    return code, capsys.readouterr().err


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        (f"contact: {FAKE_EMAIL}\n", "email address"),
        (f"account {FAKE_ACCOUNT}\n", "12-digit AWS account id"),
        (f"arn:aws:iam::{FAKE_ACCOUNT}:root\n", "12-digit AWS account id"),
        (f"key={FAKE_KEY_ID}\n", "AWS access key id"),
        (f"key: {FAKE_TEMP_KEY_ID}\n", "AWS access key id"),
        (f"{KEY_HEADER}\n", "private key header"),
    ],
)
def test_pattern_is_reported_on_its_line_without_the_value(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], text: str, reason: str
) -> None:
    path = write(tmp_path, "a.txt", ("clean\n" + text).encode())
    code, err = run([path], capsys)
    assert code == 1
    assert f"a.txt:2: {reason}" in err
    for secret in (FAKE_EMAIL, FAKE_ACCOUNT, FAKE_KEY_ID, FAKE_TEMP_KEY_ID):
        assert secret not in err


@pytest.mark.parametrize(
    "text",
    [
        "sha256: " + "a" * 7 + FAKE_ACCOUNT + "b" * 7 + "\n",
        "id " + FAKE_ACCOUNT + "0\n",
        "ts 2026-11-19T10:20:30Z version 1.2.3 pkg@1.2.3 @override\n",
        "AK" + "IA" + "SHORT\n",
    ],
)
def test_digit_runs_inside_longer_tokens_do_not_match(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], text: str
) -> None:
    code, _ = run([write(tmp_path, "ok.txt", text.encode())], capsys)
    assert code == 0


def test_carriage_return_is_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path, "crlf.txt", b"one\ntwo\r\nthree\n")
    code, err = run([path], capsys)
    assert code == 1
    assert "crlf.txt:2: carriage return" in err


def test_invalid_utf8_is_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path, "bad.txt", b"ok\n\xff\xfe\n")
    code, err = run([path], capsys)
    assert code == 1
    assert "bad.txt:2: invalid UTF-8" in err


def test_binary_from_gitattributes_is_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".gitattributes").write_text("* text=auto\n*.png binary\n", encoding="utf-8")
    write(tmp_path, "image.png", b"\x89PNG\r\n\xff\x00")
    monkeypatch.chdir(tmp_path)
    code, _ = run(["image.png"], capsys)
    assert code == 0


def test_clean_file_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path, "clean.md", b"# Title\n\nPlain text.\n")
    assert checker.main([path]) == 0
    assert "passed: 1 files" in capsys.readouterr().out


def test_missing_file_is_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, err = run([str(tmp_path / "missing.txt")], capsys)
    assert code == 1
    assert "cannot read file" in err


def test_is_binary_matches_paths_and_basenames() -> None:
    patterns = ["*.png", "assets/raw/*", "/fonts/*.ttf"]
    assert checker.is_binary("deep/dir/pic.png", patterns)
    assert checker.is_binary("assets/raw/data.bin", patterns)
    assert checker.is_binary("fonts/a.ttf", patterns)
    assert not checker.is_binary("src/readme.md", patterns)


def test_git_listing_uses_arguments_or_git(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a.txt").write_text("fine\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        checker, "list_git_files", lambda include: ["a.txt", "b.txt"][: 1 + include]
    )
    assert checker.main([]) == 0
    assert "passed: 1 files" in capsys.readouterr().out
    assert checker.main(["--include-untracked"]) == 1
    assert "b.txt:1: cannot read file" in capsys.readouterr().err


def test_git_failure_is_an_error(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(include: bool) -> list[str]:
        raise checker.GitError("no git")

    monkeypatch.setattr(checker, "list_git_files", fail)
    code, err = run([], capsys)
    assert code == 1
    assert "no git" in err


def test_list_git_files_with_and_without_untracked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    git = checker.subprocess
    git.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "tracked.txt").write_text("x\n", encoding="utf-8")
    git.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
    (tmp_path / "new.txt").write_text("y\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("z\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert checker.list_git_files(False) == ["tracked.txt"]
    assert checker.list_git_files(True) == [".gitignore", "new.txt", "tracked.txt"]

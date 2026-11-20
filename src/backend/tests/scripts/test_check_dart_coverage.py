"""Tests for scripts/check_dart_coverage.py with small lcov samples."""

from pathlib import Path

import pytest

from tests.scripts.loader import load_script

checker = load_script("check_dart_coverage")


def record(path: str, hits: list[int]) -> str:
    body = "".join(f"DA:{number},{count}\n" for number, count in enumerate(hits, start=1))
    return f"SF:{path}\n{body}LF:{len(hits)}\nLH:{sum(1 for h in hits if h)}\nend_of_record\n"


def run(tmp_path: Path, content: str, *extra: str) -> int:
    lcov = tmp_path / "lcov.info"
    lcov.write_text(content, encoding="utf-8")
    result: int = checker.main([str(lcov), *extra])
    return result


def test_all_above_limits_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    content = record("lib/scoring/rules.dart", [1] * 10) + record(
        "lib/game/session.dart", [1] * 9 + [0]
    )
    assert run(tmp_path, content) == 0
    assert "passed" in capsys.readouterr().out


def test_logic_below_85_fails_and_lists_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    content = record("lib/game/session.dart", [1] * 8 + [0] * 2)
    assert run(tmp_path, content) == 1
    assert "lib/game/session.dart: 8/10" in capsys.readouterr().err


def test_scoring_file_at_99_percent_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    content = record("lib/scoring/engine.dart", [1] * 99 + [0]) + record(
        "lib/game/session.dart", [1] * 100
    )
    assert run(tmp_path, content) == 1
    err = capsys.readouterr().err
    assert "lib/scoring/engine.dart: 99/100" in err
    assert "overall" not in err


def test_excluded_widget_file_at_zero_is_ignored(tmp_path: Path) -> None:
    content = (
        record("lib/ui/game_screen.dart", [0] * 20)
        + record("lib/player/youtube_player.dart", [0] * 5)
        + record("lib/main.dart", [0])
        + record("lib/l10n/app_localizations_en.dart", [0] * 3)
        + record("lib/game/session.dart", [1] * 10)
    )
    assert run(tmp_path, content) == 0


def test_windows_separators_are_normalized(tmp_path: Path) -> None:
    content = record("lib\\ui\\game_screen.dart", [0] * 4) + record("lib\\scoring\\a.dart", [1, 0])
    assert run(tmp_path, content) == 1


def test_only_excluded_files_reports_and_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(tmp_path, record("lib/viability/metrics.dart", [1, 0])) == 0
    assert "no non-excluded" in capsys.readouterr().out


def test_only_excluded_files_fails_with_require_files(tmp_path: Path) -> None:
    assert run(tmp_path, record("lib/viability/metrics.dart", [1]), "--require-files") == 1


def test_arguments_override_defaults(tmp_path: Path) -> None:
    content = record("lib/ui/a.dart", [0, 0]) + record("lib/game/b.dart", [1, 0])
    assert run(tmp_path, content, "--exclude", "lib/game/*", "--min-percent", "10") == 1
    assert run(tmp_path, content, "--exclude", "lib/ui/*", "--min-percent", "50") == 0


@pytest.mark.parametrize(
    "content",
    [
        "",
        "garbage\n",
        "SF:lib/a.dart\nDA:1,1\n",
        "SF:lib/a.dart\nDA:x,1\nend_of_record\n",
        "SF:lib/a.dart\nDA:1\nend_of_record\n",
        "SF:lib/a.dart\nDA:1,y\nend_of_record\n",
        "DA:1,1\nend_of_record\n",
        "end_of_record\n",
        "SF:lib/a.dart\nSF:lib/b.dart\nend_of_record\n",
    ],
)
def test_malformed_file_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: str
) -> None:
    assert run(tmp_path, content) == 1
    assert "error: cannot read coverage" in capsys.readouterr().err


def test_missing_file_is_an_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert checker.main([str(tmp_path / "absent.info")]) == 1
    assert "error: cannot read coverage" in capsys.readouterr().err


def test_file_without_instrumented_lines_passes(tmp_path: Path) -> None:
    content = record("lib/scoring/empty.dart", []) + record("lib/game/a.dart", [1])
    assert run(tmp_path, content) == 0

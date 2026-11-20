"""Check Dart line coverage from the lcov.info written by ``flutter test --coverage``.

Format (Flutter 3.47.5): one record per source file, ``SF:<path relative to the
package root>`` (backslashes on Windows, slashes on Linux), one ``DA:<line>,<hits>``
per instrumented line, ``LF``/``LH`` totals, and ``end_of_record``. Line counts
are taken from the ``DA`` lines, the totals are not trusted.

The overall figure is aggregate: covered lines over instrumented lines of all
files that are not excluded. Files under the strict prefix must be fully covered
by themselves. When no file remains after the exclusions there is nothing to
measure: the script says so and exits 0 unless ``--require-files`` is given.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

DEFAULT_EXCLUDES = (
    "lib/ui/*",
    "lib/player/*",
    "lib/viability/*",
    "lib/main.dart",
    "lib/l10n/app_localizations*.dart",
)
DEFAULT_MIN_PERCENT = 85.0
DEFAULT_STRICT_PREFIX = "lib/scoring/"
DEFAULT_STRICT_PERCENT = 100.0


class LcovError(ValueError):
    """The lcov file is missing, unreadable or malformed."""


@dataclass(frozen=True)
class FileCoverage:
    """Instrumented and covered line counts of one source file."""

    path: str
    total: int
    covered: int

    def below(self, percent: float) -> bool:
        """Return True when the covered share is under ``percent`` (empty files pass)."""
        return self.covered * 100 < percent * self.total


def parse_lcov(text: str) -> list[FileCoverage]:
    """Parse lcov text into per-file counts; raise LcovError when malformed."""
    files: list[FileCoverage] = []
    path: str | None = None
    lines: dict[int, int] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if line.startswith("SF:"):
            if path is not None:
                raise LcovError(f"line {number}: SF before end_of_record")
            path = line[3:].replace("\\", "/")
            lines = {}
        elif line.startswith("DA:"):
            if path is None:
                raise LcovError(f"line {number}: DA outside a record")
            line_number, hits = _parse_da(line, number)
            lines[line_number] = hits
        elif line == "end_of_record":
            if path is None:
                raise LcovError(f"line {number}: end_of_record without SF")
            covered = sum(1 for hits in lines.values() if hits > 0)
            files.append(FileCoverage(path, len(lines), covered))
            path = None
    if path is not None:
        raise LcovError(f"record for {path} has no end_of_record")
    if not files:
        raise LcovError("no coverage records found")
    return files


def _parse_da(line: str, number: int) -> tuple[int, int]:
    parts = line[3:].split(",")
    if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
        raise LcovError(f"line {number}: invalid DA entry {line!r}")
    return int(parts[0]), int(parts[1])


def is_excluded(path: str, patterns: list[str]) -> bool:
    """Return True when the path matches any exclusion glob."""
    return any(fnmatchcase(path, pattern) for pattern in patterns)


def evaluate(
    files: list[FileCoverage],
    excludes: list[str],
    min_percent: float,
    strict_prefix: str,
    strict_percent: float,
) -> tuple[list[str], str]:
    """Return (failure messages, summary line) for the files that are not excluded."""
    kept = [f for f in files if not is_excluded(f.path, excludes)]
    if not kept:
        return [], NO_FILES_MESSAGE
    failures: list[str] = []
    total = sum(f.total for f in kept)
    covered = sum(f.covered for f in kept)
    summary = f"{len(kept)} files, {covered}/{total} lines covered ({_percent(covered, total)})"
    if covered * 100 < min_percent * total:
        low = [f for f in kept if f.below(min_percent)]
        failures.append(
            f"overall line coverage {_percent(covered, total)} is below {min_percent:g} %"
            + _listing(low)
        )
    strict = [f for f in kept if f.path.startswith(strict_prefix) and f.below(strict_percent)]
    if strict:
        header = f"files under {strict_prefix} below {strict_percent:g} %"
        failures.append(header + _listing(strict))
    return failures, summary


NO_FILES_MESSAGE = "no non-excluded Dart files in the coverage report"


def _percent(covered: int, total: int) -> str:
    return "n/a" if total == 0 else f"{covered * 100 / total:.1f} %"


def _listing(files: list[FileCoverage]) -> str:
    return "".join(
        f"\n  {f.path}: {f.covered}/{f.total} ({_percent(f.covered, f.total)})" for f in files
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the command line parser."""
    parser = argparse.ArgumentParser(description="Check Dart line coverage from an lcov file.")
    parser.add_argument("lcov", type=Path, help="path to lcov.info")
    parser.add_argument(
        "--exclude",
        action="append",
        help="glob of an excluded file (repeatable; replaces the defaults)",
    )
    parser.add_argument("--min-percent", type=float, default=DEFAULT_MIN_PERCENT)
    parser.add_argument("--strict-prefix", default=DEFAULT_STRICT_PREFIX)
    parser.add_argument("--strict-percent", type=float, default=DEFAULT_STRICT_PERCENT)
    parser.add_argument(
        "--require-files",
        action="store_true",
        help="fail when no non-excluded file is present",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the check; return the process exit code."""
    args = build_parser().parse_args(argv)
    excludes: list[str] = args.exclude if args.exclude is not None else list(DEFAULT_EXCLUDES)
    try:
        files = parse_lcov(args.lcov.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, LcovError) as error:
        print(f"error: cannot read coverage from {args.lcov}: {error}", file=sys.stderr)
        return 1
    failures, summary = evaluate(
        files, excludes, args.min_percent, args.strict_prefix, args.strict_percent
    )
    if failures:
        print("Dart coverage check failed: " + summary, file=sys.stderr)
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    if args.require_files and summary == NO_FILES_MESSAGE:
        print(f"error: {summary}", file=sys.stderr)
        return 1
    print(f"Dart coverage check passed: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

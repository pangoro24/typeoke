"""Check the text files of the repository for encoding, line endings and sensitive content.

A text file fails when it is not valid UTF-8, contains a carriage return, or matches
one of these patterns: an email address, a 12-digit AWS account identifier, an AWS
access key identifier, a private key header. The 12-digit and key patterns are
bounded by letters and digits, so digit runs inside longer numbers, hashes and
lockfile checksums do not match.

Files are the arguments, or, when none are given, the output of ``git ls-files``
(``--include-untracked`` adds files that are not yet tracked and not ignored, so the
check also covers what is about to be committed). Run it from the repository root.
Files marked ``binary`` or ``-text`` in ``.gitattributes`` are skipped.

Every finding is printed as ``path:line: reason``. The matched value is never printed.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath

BOUNDARY_BEFORE = r"(?<![0-9A-Za-z])"
BOUNDARY_AFTER = r"(?![0-9A-Za-z])"

CONTENT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "email address",
        re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"),
    ),
    ("12-digit AWS account id", re.compile(BOUNDARY_BEFORE + r"[0-9]{12}" + BOUNDARY_AFTER)),
    (
        "AWS access key id",
        re.compile(
            BOUNDARY_BEFORE
            + r"(?:AKIA|ASIA|ABIA|ACCA|AGPA|AIDA|AIPA|ANPA|ANVA|AROA)[A-Z0-9]{16}"
            + BOUNDARY_AFTER
        ),
    ),
    (
        "private key header",
        re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----"),
    ),
)

GITATTRIBUTES = ".gitattributes"
BINARY_ATTRIBUTES = frozenset({"binary", "-text"})


class GitError(RuntimeError):
    """The list of files could not be read from git."""


def binary_patterns(attributes: Path) -> list[str]:
    """Return the path patterns marked ``binary`` or ``-text`` in a .gitattributes file."""
    try:
        text = attributes.read_text(encoding="utf-8")
    except OSError:
        return []
    patterns: list[str] = []
    for raw in text.splitlines():
        parts = raw.split()
        if len(parts) >= 2 and not parts[0].startswith("#") and BINARY_ATTRIBUTES & set(parts[1:]):
            patterns.append(parts[0])
    return patterns


def is_binary(path: str, patterns: list[str]) -> bool:
    """Return True when a path matches a binary pattern (basename when it has no slash)."""
    name = PurePosixPath(path).name
    return any(
        fnmatchcase(path if "/" in pattern.strip("/") else name, pattern.lstrip("/"))
        for pattern in patterns
    )


def list_git_files(include_untracked: bool) -> list[str]:
    """Return the files known to git, existing in the working tree, sorted."""
    command = ["git", "ls-files", "-z"]
    if include_untracked:
        command += ["--cached", "--others", "--exclude-standard"]
    try:
        result = subprocess.run(command, capture_output=True, check=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as error:
        raise GitError(f"cannot run {' '.join(command)}: {error}") from error
    names = {name for name in result.stdout.decode("utf-8").split("\0") if name}
    return sorted(name for name in names if Path(name).is_file())


def check_content(data: bytes) -> list[tuple[int, str]]:
    """Return (line, reason) findings for the bytes of one text file."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        return [(data.count(b"\n", 0, error.start) + 1, "invalid UTF-8")]
    findings: list[tuple[int, str]] = []
    carriage_return = text.find("\r")
    if carriage_return >= 0:
        findings.append((text.count("\n", 0, carriage_return) + 1, "carriage return (use LF)"))
    for number, line in enumerate(text.split("\n"), start=1):
        for reason, pattern in CONTENT_PATTERNS:
            if pattern.search(line):
                findings.append((number, reason))
    return findings


def check_files(paths: list[str], patterns: list[str]) -> list[str]:
    """Return one ``path:line: reason`` string per finding for the given files."""
    report: list[str] = []
    for path in paths:
        if is_binary(path, patterns):
            continue
        try:
            data = Path(path).read_bytes()
        except OSError as error:
            report.append(f"{path}:1: cannot read file ({error.strerror or 'error'})")
            continue
        report.extend(f"{path}:{line}: {reason}" for line, reason in check_content(data))
    return report


def build_parser() -> argparse.ArgumentParser:
    """Build the command line parser."""
    parser = argparse.ArgumentParser(description="Check text files of the repository.")
    parser.add_argument("files", nargs="*", help="files to check (default: git ls-files)")
    parser.add_argument(
        "--include-untracked",
        action="store_true",
        help="when no files are given, also list untracked files that are not ignored",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the check; return the process exit code."""
    args = build_parser().parse_args(argv)
    try:
        paths: list[str] = args.files or list_git_files(args.include_untracked)
    except GitError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    report = check_files(paths, binary_patterns(Path(GITATTRIBUTES)))
    if report:
        print("\n".join(report), file=sys.stderr)
        print(f"Text file check failed: {len(report)} finding(s)", file=sys.stderr)
        return 1
    print(f"Text file check passed: {len(paths)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())

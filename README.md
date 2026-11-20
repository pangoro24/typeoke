# Typeoke

Typeoke is a typing game played along with a song. The player types the lyrics
while the official YouTube player plays the video. The scoring rules are written
once, implemented in Python (authoritative) and in Dart (live in the browser),
and proven equal by shared golden test vectors.

This repository holds the baseline: layout, automatic checks, decision records,
the scoring rule book and a game screen playable in a desktop browser against two
local fixture songs. There is no cloud resource and no backend API yet.

## Prerequisites

- Flutter stable channel (3.47.5 with Dart 3.13.4 at the time of writing), web target enabled.
- `uv` for the Python environment and lockfile.
- Python: the newest version supported by AWS Lambda; it is pinned in
  `src/backend/.python-version`.
- WSL (Ubuntu) on Windows for the Python checks, so they run on the same operating
  system as the CI.

## Checks

Run every check from the repository root before pushing. The commands are the
ones the CI runs. Each subsection is filled in by the task that creates the check.

### Python

The project lives in `src/backend` (Python 3.14, the newest AWS Lambda runtime
at the time of writing; no runtime dependencies; dev tools pinned in `uv.lock`).
Run these in WSL from the repository root; `--directory src/backend` makes `uv`
use that project and its `src/backend/.venv`.

```
uv --directory src/backend sync --locked
uv --directory src/backend run ruff check . ../../scripts
uv --directory src/backend run ruff format --check . ../../scripts
uv --directory src/backend run mypy --strict
uv --directory src/backend run pytest --cov --cov-fail-under=85
```

Second coverage gate, 100 % of `typeoke_core/scoring.py` and
`typeoke_core/timeline.py` (run after the pytest command, which writes the
coverage data). It is enabled in task 3.4; until those files exist it reports
"No data to report" and exits 1, so it is not part of the CI before then:

```
uv --directory src/backend run coverage report --include="typeoke_core/scoring.py,typeoke_core/timeline.py" --fail-under=100
```

Notes:

- The virtual environment is created by WSL (`src/backend/.venv`, Linux layout).
  Do not run `uv sync` for this project from Windows: it would replace that
  environment with a Windows one.
- The helper scripts in `scripts/` are checked by `ruff` (explicit `../../scripts`
  argument), `mypy` (the `files` setting in `pyproject.toml`) and coverage.

### Dart coverage

Run after `flutter test --coverage` in `src/frontend` (standard library only;
exit code 1 and a list of the files below the limits on failure):

```
python3 scripts/check_dart_coverage.py src/frontend/coverage/lcov.info
```

Defaults: `lib/ui/`, `lib/player/`, `lib/viability/`, `lib/main.dart` and generated
localization files are excluded; the aggregate line coverage of the rest must be
at least 85 % and every file under `lib/scoring/` 100 %. Options: `--exclude GLOB`
(repeatable, replaces the defaults), `--min-percent`, `--strict-prefix`,
`--strict-percent`, `--require-files`. When no file remains after the exclusions
(for example while only prototype code exists) the script reports it and exits 0;
`--require-files` turns that into a failure.

### Text files and content

Checks that every text file is valid UTF-8 with LF line endings and holds no
email address, 12-digit AWS account id, AWS access key id or private key header.
Files marked `binary` or `-text` in `.gitattributes` are skipped. Findings are
printed as `path:line: reason`; the matched value is never printed. It uses only
the standard library, so it needs no virtual environment.

CI form, on the files tracked by git:

```
python3 scripts/check_text_files.py
```

Before committing (also covers new files that are not ignored and not yet added):

```
python3 scripts/check_text_files.py --include-untracked
```

Explicit files can be given as arguments instead. Run it from the repository root.

### Flutter

Run these in `src/frontend` (Flutter 3.47.5 stable). On Windows, run them
from an uppercase drive path: building from a lowercase `c:\` working directory
leaves `build/web/assets` empty (for example
`cmd /c "cd /d C:\path\to\typeoke\src\frontend && flutter build web --release --csp --no-web-resources-cdn"`).
The coverage script then runs from the repository root, as in the Dart coverage
section above.

```
flutter pub get --enforce-lockfile
flutter analyze
dart format --output=none --set-exit-if-changed lib test
flutter test --coverage
flutter build web --release --csp --no-web-resources-cdn
```

The flags of the build are the ones recorded in ADR 0001. The CI runs the same
commands in `.github/workflows/ci.yml` (jobs `python`, `flutter` and `security`, Ubuntu 24.04).

### Security

The `security` job of the CI runs three scanners with pinned versions and no
account, token or secret. Dependabot (`.github/dependabot.yml`, weekly, target
branch `develop`, 14-day cooldown) opens the update pull requests.

- gitleaks 8.30.1 scans the full git history; any finding fails the job.
- pip-audit 2.10.1 audits `src/backend/uv.lock` (development tools included);
  any known vulnerability fails the job.
- osv-scanner 2.7.0 scans `src/backend/uv.lock` and `src/frontend/pubspec.lock`;
  any known vulnerability fails the job.

The release binaries of gitleaks and osv-scanner are downloaded in the job and
checked against the SHA-256 values written in `ci.yml`. Neither pip-audit nor
osv-scanner filters by severity, so the gate is "any vulnerability", which is
stricter than "high or critical".

Local equivalents (WSL, from the repository root; install gitleaks and
osv-scanner from the release pages of the versions above, they are not part of
the repository):

```
gitleaks git --redact --no-banner --exit-code 1 .
gitleaks dir --redact --no-banner --exit-code 1 .
uv --directory src/backend export --frozen --no-emit-project --format requirements-txt --output-file /tmp/requirements.txt
uvx pip-audit==2.10.1 --requirement /tmp/requirements.txt --no-deps --disable-pip
osv-scanner scan source -L src/backend/uv.lock -L src/frontend/pubspec.lock
```

The second `gitleaks` line scans the working tree including untracked files.

## Running the game against the fixture songs

To be completed in the documentation sync group.

## Known limitations

To be completed in the documentation sync group.

## Branching model

Gitflow. Work happens on short-lived branches merged into `develop` by pull
request. `develop` will deploy the `dev` environment from spec 003. `main` is
reserved for `prod` and deploys nothing yet.

## Legal notice

Song lyrics are copyrighted. A legal review is recommended before any public
launch. The repository contains no real lyrics. The game never downloads, stores
or re-streams YouTube audio or video; it only embeds the official player.

## License

Apache License 2.0, see `LICENSE`.

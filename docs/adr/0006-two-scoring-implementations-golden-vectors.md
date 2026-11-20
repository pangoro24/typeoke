# ADR 0006: Two scoring implementations kept equal by golden vectors

## Status

Accepted (2026-11-19).

## Date

2026-11-19 (spec 001-create-baseline, task 2.8; requirement 4.1 (f)).

## Context

The frontend is Flutter web (Dart) and the backend is Python (ADR 0001, deviation STACK-01). Live scoring must run in the browser so the game answers keystrokes at once, while the server must recompute the score from the event log, because the client cannot be trusted. A single shared scoring library, as the original brief assumed with one language, is therefore not possible: the rules exist twice.

## Decision

1. There is one written rule book, `docs/scoring.md` (written in milestone 3 of spec 001). It is the only definition of the rules.
2. The Dart implementation (`src/frontend/lib/scoring/`) is the live scoring shown to the player. The Python implementation (`src/backend/typeoke_core/scoring.py` and `timeline.py`) is authoritative: its result is the one stored.
3. The two are kept equal by golden vectors in `testdata/scoring/`: shared inputs with expected outputs, run by both test suites in CI. A difference in any vector fails the build.
4. A change to a scoring rule is made in one pull request that updates the rule book, the vectors and both implementations together.
5. The reason is the stack choice (STACK-01): two languages, one set of rules.

## Consequences

- Every rule is written and tested twice; the cost is accepted in exchange for live scoring in the browser and an authoritative server.
- The vectors must cover boundaries and rounding exactly as the rule book states them, otherwise the two can diverge without a failing test.
- Scoring modules carry a stricter coverage bar in CI (100 %) than the rest of the code.
- A rule cannot be changed in one language only; a pull request that does so is rejected by the vectors.
- Open items, not decided here: none for this decision.

## Sources

- Owner decision STACK-01 (2026-11-19, see ADR 0001). No external service facts are stated.

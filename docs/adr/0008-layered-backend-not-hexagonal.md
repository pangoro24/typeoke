# ADR 0008: Simple layered backend instead of a hexagonal architecture

## Status

Accepted (2026-11-19). Accepted deviation ARCH-01, decided by the owner on 2026-11-16.

## Date

2026-11-19 (spec 001-create-baseline, task 2.8; requirement 4.1 (h)).

## Context

The usual standard of the team for Python backends is a hexagonal architecture: ports, adapters, a composition root and an import checker that enforces the boundaries. The owner wants a fast first version with few files. For a backend of this size, with a small number of external systems, that structure adds many files and indirection before it adds value.

## Decision

The backend is a simple layered design, which departs from the team's usual hexagonal standard (deviation ARCH-01):

1. Handlers are thin entry points: they read the request, call the logic and shape the response.
2. Logic modules hold the rules and import neither `boto3` nor any HTTP client, so they are tested without network or cloud.
3. Each external system has one flat integration module that owns every call to that system.
4. There are no ports, no interfaces and no composition root.
5. Tests use `moto` for AWS and stubbed HTTP for other services.
6. The reason is a fast first version with few files.

## Consequences

- Fewer files and less indirection, so the first version is quicker to write and read.
- Logic modules do not import `boto3` or HTTP clients; this is held by review and tests, not by a boundary-checking tool.
- Integration modules are not swappable behind an interface; replacing an external system means editing its module and the callers' expectations.
- If the backend grows beyond what this structure carries, moving to ports and adapters is a later refactoring that needs its own decision.
- Open items, not decided here: the lyrics pipeline and the integration modules are written in spec 002.

## Sources

- Owner decision ARCH-01 (2026-11-16). No external service facts are stated.

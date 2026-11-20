# ADR 0007: Gitflow and the Apache-2.0 license

## Status

Accepted (2026-11-19). The license may be revisited by a legal review, which the owner deferred to future work outside specs 001 to 003 (2026-11-19).

## Date

2026-11-19 (spec 001-create-baseline, task 2.8; requirements 3.12 and 4.1 (g)).

## Context

The project needs a branching model that keeps a branch always ready to deploy the development environment, and a license for the source code. Deployment arrives in spec 003; spec 001 only prepares the model.

## Decision

1. The repository uses gitflow. Work happens on short-lived `feature/*` branches that are merged into `develop` by pull request. `main` receives nothing but merges from `develop`, or from `release/*` and `hotfix/*` branches when needed.
2. `develop` will deploy the `dev` environment from spec 003. `main` is reserved for `prod` and deploys nothing yet.
3. The default branch stays `main` and no branch protection or required checks are configured in spec 001. The default branch and the branch protection are decided in spec 003; the values proposed for them are listed in the closing report of spec 001.
4. The source code is licensed under Apache-2.0. The `LICENSE` file carries the official text.

## Consequences

- Pull requests to `develop` and `main` run the CI on Linux (requirement 3.2); nothing deploys until spec 003.
- Without branch protection, the rules above rest on discipline until spec 003.
- Apache-2.0 allows commercial use and carries an explicit patent grant; third-party content (lyrics, video) is not covered by it and is handled in ADR 0002 and ADR 0003.
- Open items, not decided here: default branch and branch protection (spec 003); deployment of `dev` and `prod` (spec 003); a legal review that may revisit the license (future work, outside specs 001 to 003).

## Sources

- Owner decisions of 2026-11-19. The Apache-2.0 properties above are a general description and not legal advice; no external document was consulted for this ADR.

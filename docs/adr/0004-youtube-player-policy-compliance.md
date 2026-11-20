# ADR 0004: YouTube player policy compliance

## Status

Accepted (2026-11-19). To be re-read before any public launch because the policies change.

## Date

2026-11-19 (spec 001-create-baseline, task 2.7; requirements 4.1 (d) and 4.2). This is also the date on which the policies listed below were read.

## Context

The game shows a YouTube video through the official IFrame Player API beside a typing area. The use of that player is governed by the YouTube API Services Terms of Service and Developer Policies. Both pages were read in full on 2026-11-19 and show "Last updated 2026-11-06 UTC". The Required Minimum Functionality page (same date and "last updated") and the IFrame Player API reference (consulted 2026-11-19, "Last updated 2026-10-15 UTC") were read for the player rules.

## Decision

The game relies on the clauses below (paraphrased; section names as on the pages) and is built to comply with them. The right-hand column is what the code and the screens must do.

| Clause (source) | Game rule |
|---|---|
| Developer Policies III.I: do not modify, build upon or block any portion or functionality of a YouTube player; do not block or interfere with ads served by YouTube | The embedded player is used as is: standard controls, no ad blocking, no hiding of branding or links |
| Required Minimum Functionality, "Overlays and frames": no overlays, frames or visual elements in front of, or obscuring, any part of the embedded player, including its controls | No widget, popup, notice or animation covers the player; the layout reserves its rectangle and nothing intersects it, in every game state |
| Required Minimum Functionality, "YouTube Player attributes": no changes to the player that the API documentation does not explicitly describe | Only documented IFrame API methods and events are used |
| Required Minimum Functionality, player size: viewport at least 200 x 200 px, large enough to show the controls; 16:9 players recommended at least 480 x 270 px | The game reserves at least 480 x 270 CSS px (the recommended size, stricter than the minimum) |
| Required Minimum Functionality, "Autoplay and scripted playbacks": no automatic playback until the player is visible and more than half of it is visible | Playback starts only when the player is fully visible, and only after the user starts the game |
| Developer Policies III.F, incentives: no incentives, rewards or compensation for viewing; no gating of a video behind actions other than pressing play (login is allowed when it is not specific to YouTube API Services) | Points come from typing performance only; nothing is awarded for watching; no prizes tied to views |
| Developer Policies III.I: no features that play content from a background player, one that is not displayed in the page, tab or screen the user is viewing | When the tab or window is hidden, the game and the player are paused and do not resume by themselves |
| Developer Policies III.E and III.I: no download, storage, caching or separation of audio or video | See ADR 0002 |

IFrame Player API facts used (page https://developers.google.com/youtube/iframe_api_reference, consulted 2026-11-19):

- Requires the page to define `onYouTubeIframeAPIReady`; the player has `onReady` and `onStateChange` events.
- Player states: -1 unstarted, 0 ended, 1 playing, 2 paused, 3 buffering, 5 video cued.
- `getCurrentTime()` returns elapsed seconds; `playVideo()`, `pauseVideo()` and `seekTo(seconds, allowSeekAhead)` exist. `seekTo` moves to the closest keyframe before the time unless the part is already downloaded, so the reported position after a seek can differ from the requested one.
- Adding `enablejsapi=1` to an iframe URL enables the API; the optional `origin` parameter is documented as protection against injected third-party scripts.
- An `onAutoplayBlocked` event fires when the browser blocks autoplay or scripted playback.

Open items, none decided here: legal review before outside users, domain, and Google federation (deferred by the owner to future work, outside specs 001 to 003, 2026-11-19); Amazon Nova model and Region for Bedrock, and whether Snyk is added to CI (spec 002); branch protection (spec 003).

## Consequences

- The game screen is designed around a reserved player rectangle; layout tests assert that no other widget intersects it in any state.
- The game never waits on or hides the player's own controls; when the user seeks or pauses with them, the game reacts (pause, seek notice) instead of preventing it.
- Anything in the policies or the API can change; re-reading them before launch is a task of the closing and launch work, and this ADR is then superseded or amended with the new date.
- **Not verified or not found:** the Developer Policies page lists the IFrame Player API among the YouTube API services, but whether an embed without credentials needs a separate acceptance of the Terms was not examined in detail. The wording about hiding or customizing the player's standard controls (for example the `controls` parameter) was not found on the pages read and is not assumed; the game keeps the standard controls. The size 480 x 270 px is a YouTube recommendation (stated by both the IFrame reference and the Required Minimum Functionality page) and a stricter project rule, not a mandatory minimum. Advertising behavior inside the embedded player was not tested in this spec. Any YouTube embedded-player terms outside these pages were not read. This ADR is not legal advice.

## Sources

All consulted 2026-11-19:

- YouTube API Services Terms of Service, https://developers.google.com/youtube/terms/api-services-terms-of-service (last updated 2026-11-06 UTC).
- YouTube API Services Developer Policies, https://developers.google.com/youtube/terms/developer-policies (last updated 2026-11-06 UTC), sections III.E, III.F and III.I.
- Required Minimum Functionality, https://developers.google.com/youtube/terms/required-minimum-functionality (last updated 2026-11-06 UTC).
- YouTube IFrame Player API reference, https://developers.google.com/youtube/iframe_api_reference (last updated 2026-10-15 UTC).

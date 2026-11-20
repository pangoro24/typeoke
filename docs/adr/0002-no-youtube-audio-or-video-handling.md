# ADR 0002: No handling of YouTube audio or video

## Status

Accepted (2026-11-19). Binding for every component of the project. Audio transcription is described below as parked and is not accepted for any work.

## Date

2026-11-19 (spec 001-create-baseline, task 2.7; requirement 4.1 (b)).

## Context

The game plays a song from YouTube and asks the player to type its lyrics in time. A tempting way to obtain timed lyrics would be to take the audio of the video and transcribe it. The YouTube Developer Policies forbid the operations that this needs, and the owner's rule for this project is to stay inside them.

What the policies say (read on 2026-11-19, see Sources; paraphrased):

- Section III.E, "Audiovisual Content": clients must not download, import, back up, cache or store copies of YouTube audiovisual content without YouTube's prior written approval, and must not make content available for offline playback.
- Section III.I, "Additional Prohibitions": clients must not separate, isolate or modify the audio or video components of YouTube audiovisual content (the example given is applying alternate audio tracks), and must not promote those components separately.

The policy pages describe the rules of the YouTube API Services. Whether a given technical act (for example, a server fetching a stream) falls under them was not analysed in detail; the project does not need that analysis because it avoids the acts altogether.

## Decision

1. No component of the project (browser, backend, scripts, tests, tooling) downloads, stores, caches, proxies, re-streams, extracts, separates or otherwise processes YouTube audio or video. Playback happens only inside the official YouTube IFrame player embedded in the page (see ADR 0004).
2. No test, fixture or sample in the repository contains YouTube audio or video, and no script fetches them.
3. **Audio transcription is parked.** It is the idea of obtaining word-level timings or text from the audio of a song. It stays out of scope because there is no audio source for it that is compliant with the rules above today. It may be reconsidered only when both conditions hold: (a) the owner records a written decision to do so, and (b) a compliant audio source exists (for example, audio the owner has the rights to, supplied outside YouTube). Until then there is no interface, abstract class, placeholder module, feature flag or configuration for it anywhere in the code. This ADR is the only place where it exists.
4. Timed lyrics come only from the source in ADR 0003; titles and metadata come from the YouTube API data the owner's specs allow, never from media.

## Consequences

- Songs without synced lyrics in the chosen source cannot be played; the product reports that the song is not available instead of generating timings. This limits the catalogue and is accepted.
- Cost and complexity of speech processing are avoided entirely.
- Reviewers can reject any change that adds media handling by pointing to this ADR; lifting the rule requires a new ADR that supersedes this one, after the owner's written decision.
- The practice songs of spec 001 use local fixtures of timings and text written for the project, not real lyrics and not media.

## Sources

- YouTube API Services Developer Policies, https://developers.google.com/youtube/terms/developer-policies (sections III.E and III.I; page shows "Last updated 2026-11-06 UTC"); consulted 2026-11-19.
- YouTube API Services Terms of Service, https://developers.google.com/youtube/terms/api-services-terms-of-service (defines "YouTube API Services", including audiovisual content provided through the APIs); consulted 2026-11-19.
- Not verified: the interpretation of these clauses by YouTube in specific technical cases, and whether any "written approval" process exists for the use cases discussed here. The legal review is deferred to future work, outside specs 001 to 003 (owner decision, 2026-11-19); it is not decided here.

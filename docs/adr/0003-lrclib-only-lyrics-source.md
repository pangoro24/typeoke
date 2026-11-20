# ADR 0003: LRCLIB as the only lyrics source

## Status

Accepted (2026-11-19). The choice of source is for version 1; a licensed source is a possible later decision of the owner and is not made here.

## Date

2026-11-19 (spec 001-create-baseline, task 2.7; requirement 4.1 (c)).

## Context

The game needs lyrics with line timestamps so that typed words can be scored against the song. No audio may be used to produce them (ADR 0002). LRCLIB is a free, community-maintained lyrics database that serves synchronized lyrics in LRC format and can be searched by track, artist, album and duration. Its documentation says no API key is required and anonymous access is available.

Facts about LRCLIB, from its official API documentation (https://lrclib.net/docs, read as the Markdown rendering https://lrclib.net/docs.md; consulted 2026-11-19):

- Base URL `https://lrclib.net`; the API is CORS-enabled.
- `GET /api/get` needs `track_name` and `artist_name`; `album_name` and `duration` (seconds, 1 to 3600) are optional and recommended. The documentation says a match is returned only when the duration is equal or within 2 seconds of the stored record. A miss returns 404.
- `GET /api/get/{id}` returns one record by id. `GET /api/search` takes `q` or `track_name` (plus optional artist and album), returns at most 20 results, no pagination.
- A record includes `plainLyrics`, `syncedLyrics` (LRC with line timestamps), `instrumental` and `hasWordSync`; synced and plain lyrics are `null` for instrumental tracks.
- A beta `GET /api/v2/search` returns summaries without lyrics text; it is documented as subject to change and is not relied on.
- **User-Agent:** clients are required to identify themselves with a `User-Agent` stating application name, version and a link to a homepage or an email address; `X-User-Agent` or `Lrclib-Client` may be used where the header cannot be set.
- **Rate limits** (documented as approximate, not part of the contract, may change without notice): about 45 requests per minute per IP for a generic client; about 90 per minute per IP for an identified client; higher for applications registered in the developer portal (about 180 per minute per IP for client-side, about 6,000 per minute application-wide). Exceeding a limit returns 429 with a `Retry-After` header that clients must honor, with a small random jitter; ignoring it may lead to a temporary ban. The documentation also advises sequential requests with a 200 to 500 ms delay in batch work.
- Not verified: the page read has no license statement or usage terms for the lyrics content itself (rights of the lyrics belong to their owners). Whether LRCLIB data may be used in a commercial service and how the content is licensed were not found and are not assumed.

## Decision

1. LRCLIB is the only lyrics source of version 1. There is no lyrics-provider interface; the integration is one flat module in spec 002 and the pure functions around it are written there. Spec 001 contains no lyrics code.
2. The project treats lyrics as copyrighted content, whatever LRCLIB's own terms are:
   - the server caches lyrics per `videoId` with a 30-day time to live and refreshes them on expiry;
   - lyrics are served only to authenticated users, only through the game endpoints;
   - there are no public lyric pages, no bulk lyric endpoints, and no lyrics in leaderboards or share cards;
   - the README carries a legal notice that a legal review is recommended before any public launch.
3. The client calls LRCLIB with an identifying `User-Agent` (application name, version, project link) set by the server-side integration, honors `Retry-After` with jitter, and keeps well under the identified-client rate through the cache and per-user limits of spec 002.
4. No real lyrics are stored in the repository, its tests, fixtures or documentation; fixtures use text written for the project.

## Consequences

- Only songs present in LRCLIB with synced lyrics can be played; coverage depends on a community database whose accuracy and availability the project does not control. A song without a match is reported as not available.
- The documented rate limits are approximate and may change; the integration must handle 429 and 503 without failing the whole request.
- Because the documentation gives no license for the lyrics, the 30-day cache and the access limits are a conservative policy, not a legal conclusion.
- Open items, not decided here: the legal review before inviting outside users and the evaluation of licensed lyrics sources (deferred by the owner to future work, outside specs 001 to 003, 2026-11-19). Whether to register a LRCLIB application for higher rate limits is evaluated in the design of spec 002.

## Sources

- LRCLIB API documentation, https://lrclib.net/docs and https://lrclib.net/docs.md; consulted 2026-11-19.
- The facts above come only from those pages. Anything about the licensing of LRCLIB data is not verified.

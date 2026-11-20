# ADR 0001: Frontend stack, Flutter web

- **Status:** Accepted (2026-11-19). Gate result NOT PASS (see "Result"); the owner chose to keep Flutter web with the failures accepted (deviation VIAB-01).
- **Date:** 2026-11-19
- **Spec:** 001-create-baseline, milestone 1 (tasks 1.5 and 1.6)

## Result

**NOT PASS.** On Chrome, criteria 1.5 (frame rate), 1.7 (resume reaction) and 1.8 (seek detection) failed; Firefox was NOT RUN (deviation VIAB-FF-01, pending). The owner accepted this result and kept Flutter web (2026-11-19, see "Decision"). The prototype in `src/frontend/lib/viability/` is kept as is.

## Context

The brief proposed TypeScript end to end. The owner chose Flutter web for the frontend and Python for the backend (deviation STACK-01), with scoring written twice (Dart for live scoring, Python as the authority) and kept equal by shared golden vectors. Because a Flutter web canvas app might not meet the latency and frame-rate needs of a typing game next to the official YouTube IFrame player, milestone 1 is a gate: a disposable release-build prototype is measured against the thresholds of requirements 1.3 to 1.12 before any game code is written.

## Method

- **Prototype:** release build, default (non-WebAssembly) build mode, served from a local static server on `127.0.0.1` so the page runs under its own-origin Content Security Policy (a meta tag). The official YouTube IFrame player (640 x 360 CSS px) sits beside a typing area and scrolling synthetic lyric lines.
- **Video (A22):** a public Blender Foundation video, embeddable; its id was typed at run time and is not stored in any file. The owner's own video was not yet available. No advertisement was recorded in the run notes; this was not checked explicitly.
- **How the run was done (read this before the numbers).** The run was an automated browser-driven run: a browser automation tool drove the page through the browser debugger protocol, not a person at a keyboard. The owner accepted this second automated run as the evidence for this ADR instead of a manual run. This approach distorts frame rate and timing, so criteria 1.5, 1.7 and 1.8 in particular are not clean measurements (the debugger protocol adds work to the page and the window was not driven as a user would). Their failures may be partly or wholly artefacts of the method, or real; this run cannot tell. Generated keystrokes (criteria 1.3 and 1.4) go through the same keyboard path as real keys, but physical keyboard delay is not included.
- **Hand-typed latency excluded.** The run also recorded text typed through the automation tool (75 keystrokes, median 882.8 ms, p95 910.9 ms). That number comes from the automation tool's synthetic input and is not meaningful; it is excluded from every verdict.
- **Earlier run:** a first automated run (same method, measurement bugs since fixed, not valid for the verdict) saw the player resume in 283.8 ms after `playVideo()`, which corroborates the 1.7 resume failure of the second run (298.3 ms). Its 1.3 values (median 34.3 ms, p95 56.5 ms) were over the limits, unlike the second run; the difference is not explained and shows how method-sensitive the numbers are.
- **Duration:** 180 s continuous run, as required by 1.2.
- **Repetition:** the 1.7 resume was measured four times through the API inside the run; 1.5 and 1.8 were measured once per run (two runs in total, both failing). The measurement is unreliable for 1.5, 1.7 and 1.8 in the sense above; they are recorded as FAIL, never as passing.

## Environment

| Item | Value |
|---|---|
| Date | 2026-11-19 |
| Machine | Windows 10 desktop (development PC), 6-core laptop-class CPU, 16 GB RAM |
| Chrome | 157 (from the user agent of the run; devicePixelRatio 1) |
| Firefox | NOT RUN, pending (VIAB-FF-01) |
| Flutter | 3.47.5, stable channel, framework revision 6a19cca564 (2026-09-17), engine revision af7e796e16, Dart 3.13.4 (`flutter --version` on 2026-11-19) |
| Renderer | the default web renderer of that Flutter version, without the WebAssembly option; the exact renderer name was not verified in the documentation |

## Measured values (Chrome 157, 180 s run, against thresholds)

| Criterion | Measure | Threshold | Value | Outcome |
|---|---|---|---|---|
| 1.3 | key-to-paint latency, 500 generated keystrokes | median <= 33 ms, p95 <= 50 ms | median 24.8 ms, p95 35.3 ms | PASS |
| 1.4 | burst 15 chars/s for 10 s | none lost, duplicated or reordered | 150 sent, 10 008.6 ms, 0 lost, 0 duplicated, 0 out of order, 0 unexpected | PASS |
| 1.5 | frame rate while lines scroll | average >= 50 fps, < 1 % frames over 50 ms | 33.6 fps average, 5.58 % slow frames (about 49 fps mid-run, falling during seeks and the end credits) | FAIL (distorted method) |
| 1.6 | playhead drift | p95 <= 50 ms, max <= 150 ms | p95 1.1 ms, max 51.2 ms | PASS |
| 1.7 | pause / buffering / resume reaction | <= 250 ms | pause 13.9 ms, buffering 0 ms (no buffering event observed), resume 298.3 ms | FAIL (resume; distorted method; corroborated by 283.8 ms in the earlier run) |
| 1.8 | seek detection | <= 500 ms | 2 098.2 ms (jump to a part of the video not yet loaded) | FAIL (distorted method) |
| 1.9 | hidden tab pauses the player | <= 500 ms | 8 ms | PASS |
| 1.10 | player size and visibility | >= 480 x 270 CSS px, not covered | 640 x 360 | PASS |
| 1.11 | focus: one click on the typing area restores typing | one click | worked | PASS |
| 1.12 | CSP | no violation, no `unsafe-inline` or `unsafe-eval` for scripts | meta tag present, no violation reported | PASS |

The buffering value of 0 ms means no buffering transition was seen during the run; it is not evidence that buffering reacts quickly.

### Informational values (A3)

| Value | Result |
|---|---|
| Release build transferred | 8 245 478 bytes encoded (served by a plain static server, probably uncompressed; a compressed figure was not measured) |
| First frame, cold load | 1 580.6 ms (page not served from cache) |
| Warm load time | not measured |
| JS heap after 3 minutes | 80 983 847 bytes (about 81 MB; 73 368 231 bytes at the end of the sample taken earlier) |

## Content Security Policy

Used (meta tag in `web/index.html`): `default-src 'none'; script-src 'self' 'wasm-unsafe-eval' https://www.youtube.com; frame-src https://www.youtube.com https://www.youtube-nocookie.com; connect-src 'self' https://www.youtube.com; img-src 'self' data: blob: https://i.ytimg.com; style-src 'self' 'unsafe-inline'; font-src 'self' data:; worker-src 'self' blob:; manifest-src 'self'; object-src 'none'; base-uri 'self'; form-action 'none'`.

- No `unsafe-eval`, no inline scripts. `wasm-unsafe-eval` is present as allowed by A4; whether the default build mode runs without it was not tested, so "needed" is not verified.
- `style-src 'unsafe-inline'` is present because the engine sets inline styles; whether it can be removed was not tested.
- Build flags: `--csp` (avoids code that needs `unsafe-eval`) and `--no-web-resources-cdn` (engine assets served from our origin). Not re-verified against the Flutter documentation on 2026-11-19; they are the flags found and used during task 1.2.
- The bootstrap is an external `flutter_bootstrap.js` loaded with a script tag, so no inline script is needed.

## Findings from the prototype

1. **DOM focus stayed in the YouTube iframe** after a click on the player, so typing was lost. Fixed: the iframe is blurred and focus goes to the Flutter view on the next click (criterion 1.11 passes).
2. **`getCurrentTime` was polled before the player's `onReady`** and failed. Fixed: polling starts after `onReady`.
3. **No text rendered under the CSP**, because Flutter fetched Roboto and fallback fonts from `fonts.gstatic.com`. Fixed: Roboto is bundled from the Flutter SDK (Apache-2.0, with its license file). `fonts.gstatic.com` stays unlisted in the CSP; a glyph outside the bundled font falls back to the engine's default, and enabling the `fonts.gstatic.com` fallback only for such glyphs remains a decision for the game screen.
4. **Accented characters (open item, unconfirmed).** Text typed through the automation tool with o-acute, n-tilde and u-umlaut arrived without those characters. This could be the synthetic key events of the automation tool or a real defect in the typing capture. It is NOT marked as passing. The owner must type accented letters and n-tilde once on a real keyboard to confirm. This matters for a typing game in Spanish and Portuguese.

## Decision

**Keep Flutter web (owner decision, 2026-11-19), accepting the NOT PASS result** (deviation VIAB-01). Reading of the evidence: the criteria that depend on the page itself (latency, burst, drift, focus, CSP, player size, hidden tab) pass; resume (1.7) and seek to an unbuffered position (1.8) depend mainly on the YouTube player and the network, and would likely be similar in another frontend stack; frame rate (1.5) is the one failure tied to Flutter, and it is the measurement the automated method distorts most (about 49 fps mid-run).

Flutter web (Dart) for the frontend, Python for the backend (replacing the brief's TypeScript stack, STACK-01), scoring in both languages tied by golden vectors. Fallback if the open checks below fail badly: Svelte + TypeScript.

Open checks, to run before game code relies on them: frame rate with the window in front on a real run, accented letters and n-tilde typed on a real keyboard, and Firefox (VIAB-FF-01).

The owner commits to review stack performance for scalability at the closing of spec 001 and after the first real usage data.

## Consequences

- **Build must not run from a lowercase `c:\` working directory.** `flutter build web` started from a `c:\...` path (as an editor terminal may give) reports success but leaves `build/web/assets` empty: no FontManifest, fonts, shaders or service worker, and the page renders without text. Build through `cmd /c "cd /d C:\...\src\frontend && flutter build web --release --csp --no-web-resources-cdn"` (uppercase drive letter), and check that `build/web/assets` is not empty. CI on Linux is not affected.
- Frontend assets (Roboto and any other font) are bundled; the app does not depend on a font CDN, and the CSP stays strict.
- The release build is large (about 8 MB uncompressed transfer), which matters for the cold load time; compression and the stack review will revisit it.
- Firefox is not covered. Until it runs, the result cannot be PASS (criteria 1.14 and 1.15 require every browser of A1).
- `src/frontend/lib/viability/` stays in the repository until the open checks above have run (it is the tool that runs them); its removal or reuse (A2) is decided then.
- Facts about Flutter web (CSP flags, renderer defaults) and the YouTube IFrame API (state events, `getCurrentTime`) were taken from the prototype work and not re-checked against the documentation pages on the date of this ADR: not verified.

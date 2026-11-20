# Typeoke scoring rule book

This document is the single definition of how a Typeoke play is judged and scored. Two programs implement it: the Python module `src/backend/typeoke_core/scoring.py` (authoritative, recomputes a play from its event log) and the Dart module `src/frontend/lib/scoring/` (live score in the browser). A set of golden vectors in `testdata/scoring/` proves that both give the same result (ADR 0006). If a sentence here can be read in two ways, that is a defect of this document and it is fixed here, never in one implementation only.

A change to any rule or constant is made in one pull request that updates this document, the golden vectors and both implementations.

## 1. Conventions

1. **Integers only.** Every value used by the rules is an integer: times in milliseconds (`ms`), percentages as integers (`80` means 0.80), ratios as a numerator and a denominator, accuracy and hit rate in basis points (`bp`, 10000 bp = 100 %). No floating point number appears in any rule, and an implementation must not use one for scoring.
2. **Rounding.** `round_half_up(n / d)`, for integers `n >= 0` and `d > 0`, is `floor((2n + d) / (2d))` computed with integer division: a fraction exactly halfway between two integers goes to the larger one (`2.5` gives `3`, `62.5` gives `63`). Every rounded quantity in this document is non-negative; no rule rounds a negative value. If a later rule needs one, it must state its rounding explicitly (half toward positive infinity, that is `floor(x + 1/2)`, would be the natural choice) and this convention must be extended in the same change. Every rounding in the rules is named where it occurs; a quantity that is not said to be rounded is exact.
3. **Boundaries.** Every comparison states `<`, `<=`, `>` or `>=` explicitly. When a value lies exactly on a limit, it belongs to the better outcome for the player (decision A8): a delta of exactly 600 ms is PERFECT, exactly 3500 ms is OK, an accuracy of exactly 60 % is accepted, an accuracy of exactly 80 % meets the combo threshold, a combo of exactly 10 reaches the next step.
4. **Characters.** The length of a text is the number of Unicode code points (not UTF-16 code units, not grapheme clusters). Dart implementations must iterate code points (runes), never `String.length`. Indexes are 0-based.
5. **JSON numbers.** Validity is defined on the *decoded value* that the scoring receives, not on how the JSON text was written (decision D22). Every number in the formats below must be an integer in the range 0 to 9007199254740991 (2^53 - 1), unless a field is stated to allow another range; any other decoded value is malformed. In Python a value is an integer when `type(x) is int` (so `True` and `False` are not integers, and `float` values such as `1.5` or `1.0` are malformed). In Dart, where the vectors run on the Dart VM, a value is an integer when `x is int`. The decoded form of `-0` is the integer 0 in Python and is accepted as 0; a golden vector never contains `-0`, a fraction or an exponent. The range is the one that Dart on the web (where integers are double precision numbers) can represent exactly. The live engine never parses JSON: it receives integers from the game, so the web decoding limits do not apply to it. A JSON file that holds `NaN`, `Infinity`, `-Infinity` or an object with a duplicate key is not valid JSON for this project: in vectors it is a test-file error (the vector fails the schema check, it is never a scoring rejection). The canonical decoder of the Python side is `json.loads` with `parse_constant` set to a function that raises and `object_pairs_hook` set to a function that raises on a duplicate key; the Dart decoder must reject the same inputs. The server decoding of a submitted play (spec 002) rejects such input as `MALFORMED_EVENT_LOG` at the JSON-decoding layer; that layer belongs to spec 002.
6. **Magnitudes.** With a valid configuration (section 2), the formulas below stay below 2^53 for expected words of at most 10000 code points after normalization (under the longest form, the one with the accent option off, which is also the longest for `L`) and typed texts of at most `max_typed_chars` (at most 64) code points before normalization, which are at most 256 code points after NFD (the longest canonical decomposition of one code point has 4). A timeline whose expected word is longer than 10000 code points is invalid (section 16). The only exact sum that can exceed that range is the one of section 14.3, which therefore uses arbitrary precision integers (Python `int`, Dart `BigInt`).
7. **Unicode version.** All Unicode properties used below (decomposition, combining class, general category, lowercase mapping) are those of **Unicode 16.0.0**. The Python test suite asserts `unicodedata.unidata_version == "16.0.0"`; moving to another Unicode version is a rule change (same pull request: this document, the Dart tables, the vectors). Vectors and every Unicode-dependent generated file (the Dart tables of section 3.3) are generated only with the project's `uv` Python 3.14, which has Unicode 16.0.0, never with the system `python3` of WSL (3.10, Unicode 13.0.0), which gives different results.
8. **Determinism.** The scoring uses no clock, no randomness, no locale, no input and no output. The same timeline, play settings, event log and configuration always give the same result, in either language.
9. **Word.** A *word* is an element of the timeline (section 16). A word is *scorable* when its song-normalized text (section 3.2, whatever the play settings are) is not empty. Only scorable words are ever current, can be committed, give points or count in a total. The *global word index* of a word is its 0-based position among all words of the timeline in order, across lines, counting the words that are not scorable.

## 2. Constants

All constants live in one configuration object. The key of each one is stable, in `snake_case`, and is the key used in `testdata/scoring/config.json`, in `ScoringConfig` (Python, task 3.2) and in the Dart configuration (task 4.1). `config.json` is a flat JSON object with exactly these keys and these values, no others; every value is an integer except `default_accent_insensitive` and `default_case_insensitive`, which are booleans.

| Key | Value | Unit | Meaning |
|---|---|---|---|
| `lead_in_ms` | 1500 | ms | A line accepts commits from `line start - lead_in_ms` (inclusive) |
| `miss_window_ms` | 3500 | ms | A word expires when the playhead is more than this after its expected time |
| `min_accuracy_pct` | 60 | % | A commit with accuracy below this is a MISS |
| `tier_perfect_limit_ms` | 600 | ms | Largest absolute delta of tier PERFECT (inclusive) |
| `tier_great_limit_ms` | 1200 | ms | Largest absolute delta of tier GREAT (inclusive) |
| `tier_good_limit_ms` | 2200 | ms | Largest absolute delta of tier GOOD (inclusive) |
| `tier_ok_limit_ms` | 3500 | ms | Largest absolute delta of tier OK (inclusive) |
| `tier_perfect_pct` | 100 | % | Timing multiplier of PERFECT |
| `tier_great_pct` | 80 | % | Timing multiplier of GREAT |
| `tier_good_pct` | 55 | % | Timing multiplier of GOOD |
| `tier_ok_pct` | 30 | % | Timing multiplier of OK |
| `tier_early_pct` | 10 | % | Timing multiplier of EARLY |
| `base_points_per_char` | 10 | points | Base points per character of the expected word |
| `combo_base_pct` | 100 | % | Combo multiplier with no step reached |
| `combo_step_words` | 10 | words | Combo length that adds one step |
| `combo_step_pct` | 25 | % | Multiplier added per step |
| `combo_cap_pct` | 200 | % | Largest combo multiplier |
| `combo_accuracy_pct` | 80 | % | Accuracy needed to extend the combo and to qualify for the line bonus |
| `line_bonus` | 50 | points | Line bonus, never multiplied |
| `default_accent_insensitive` | true | flag | Initial state of the "ignore accents" toggle of the game screen; never read by the scoring |
| `default_case_insensitive` | true | flag | Initial state of the "ignore letter case" toggle of the game screen; never read by the scoring |
| `rank_s_pct` | 90 | % | Rank S from this percentage of the maximum base score |
| `rank_a_pct` | 75 | % | Rank A from this percentage |
| `rank_b_pct` | 55 | % | Rank B from this percentage |
| `rank_c_pct` | 35 | % | Rank C from this percentage (below it: D) |
| `expected_time_pct` | 90 | % | Share of the line window used by the expected-time rule (the 0.9 factor) |
| `max_line_window_ms` | 6000 | ms | Longest line window before the next line (instrumental gap cap, A11) |
| `last_line_window_ms` | 5000 | ms | Window of the last line (A11) |
| `max_typed_chars` | 64 | characters | Longest accepted typed text of a commit (A12) |

Validity of a configuration: the four tier limits are strictly increasing; the five timing percentages are between 0 and 100; every other number is at least 0; `base_points_per_char >= 1` (so the maximum base score is above 0 whenever the song has a scorable word, section 14.4); `combo_step_words >= 1`; the rank percentages strictly decrease from S to C. Upper bounds, so that the magnitudes of section 1.6 hold: `base_points_per_char <= 100`; every other percentage (the combo and rank ones) `<= 1000`; every value in `ms` `<= 3600000`; `combo_step_words <= 1000000`; `1 <= max_typed_chars <= 64`. A configuration that is not valid is a programming error, not a rejection reason (decision D20).

The multiplier percentages of tiers and combo, and the accuracy percentages, are the integer forms of the factors 1.00 / 0.80 / 0.55 / 0.30 / 0.10, 0.25, 2.0, 0.6 and 0.8 of the requirements.

The two options that change how words are compared are not constants: they are chosen by the player for each play and travel with the play as the *play settings* (section 15.6). The scoring takes them only from there and never reads `default_accent_insensitive` or `default_case_insensitive`, which only give the game screen the initial state of its two toggles (so changing a default never changes a score).

Two constants share the value 3500 and are kept apart on purpose: `miss_window_ms` decides when a word expires (section 11), `tier_ok_limit_ms` decides which tier a commit gets (section 7). With the default values they coincide.

## 3. Text handling

### 3.1 Whitespace and words

*Whitespace* is exactly these code points: U+0009 to U+000D, U+0020, U+0085, U+00A0, U+1680, U+2000 to U+200A, U+2028, U+2029, U+202F, U+205F and U+3000 (the general categories Zs, Zl and Zp plus the control characters U+0009 to U+000D and U+0085). An implementation must not use the whitespace definition of its standard library, which differs.

A line text is split into words by cutting at every run of whitespace: a word is a maximal run of non-whitespace code points; leading, trailing and repeated whitespace produce no empty word. A text with no non-whitespace code point has no words (an *empty line*, allowed).

### 3.2 Normalization

`normalize(text, settings)` takes the play settings of section 15.6 (`accent_insensitive` and `case_insensitive`) and gives the *comparison normalization*. Steps, in this order, on the sequence of code points:

1. **Decompose**: canonical decomposition into Unicode Normalization Form D (NFD, Unicode Standard Annex #15, including canonical ordering of combining marks and the algorithmic decomposition of Hangul syllables). NFD is applied whatever the options are (decision D2).
2. **Remove marks** (only when `accent_insensitive` is true): delete every code point whose general category is Mn (nonspacing mark). Marks of other categories (Mc, Me) are kept. With the option off the marks stay and count as code points.
3. **Lowercase** (only when `case_insensitive` is true): replace each code point, one at a time and with no context, by its *simple lowercase mapping* (field 13 of `UnicodeData.txt`; a code point without a mapping is unchanged). In Python this is `c.lower()` applied to a single code point, with the single exception U+0130, whose simple mapping is U+0069 (Python's `lower()` would give two code points); after step 1 no U+0130 is left in the text (NFD turns it into `I` + U+0307), so the exception matters only for a lowercase table built on its own, such as the Dart one. Never call `lower()` on the whole string: it applies the final-sigma context rule (`ΟΔΟΣ` would give `οδος`; code point by code point gives `οδοσ`). This is lowercasing, not case folding (`str.casefold` is not used, because Dart has no equivalent). With the option off this step is skipped entirely and nothing else replaces it: the exact case of the lyric is required everywhere, including the first letter of each lyric line (decision D1 then does not apply).
4. **Remove ignorable characters** (always): delete every code point whose general category is P* (Pc, Pd, Ps, Pe, Pi, Pf, Po), S* (Sm, Sc, Sk, So), Z* (Zs, Zl, Zp), Cc or Cf. Everything else is kept: letters, numbers (N*), marks that were not removed, private use and unassigned code points. Punctuation is ignored whatever the options are.

The same comparison normalization, with the same settings, applies to the expected word and to the typed text. Whitespace inside a typed text is removed by step 4, so a typed text is compared as one string.

The *song normalization* is `normalize(text, {accent_insensitive: true, case_insensitive: true})`, always, whatever the play settings are. It decides which words are scorable (1.9), the expected time of each word and its character counts (section 6), the base word length `Lexp` of the points formula (section 8) and the maximum base score (section 14.2), so these values belong to the song and never change with the player's options (6.11). The comparison normalization is used only for the play pair of the accuracy of a commit (section 4), including its length `L` (A5); the final accuracy is the lower of that pair and the song pair, which is computed with the song normalization.

A property of the two normalizations, checked over every code point of Unicode 16.0.0: lowercasing never changes whether a code point is kept by step 4 and never changes the number of code points, so the case option never changes a length; and a code point kept by the song normalization is also kept by every comparison normalization (the accent option off only keeps more code points). Hence a scorable word has `len(e) >= 1` under any settings.

Consequences and known limits, all intended:

- With both options on (the default), `canción`, `Canción,` and `CANCION` normalize to `cancion`. `ñ` becomes `n` (NFD gives `n` + U+0303 and the mark is removed).
- With the accent option off, the NFD form is kept: `canción` normalizes to `canción` of 8 code points (`o` + U+0301 counts as two), `cancion` has 7, so they differ by one edit; `ñ` counts as two code points. This is the stated choice for 6.2.
- With the case option off, `Hello` and `hello` differ by one edit; `Hello,` and `Hello` are equal (punctuation is still removed); the accent option still acts independently (`Canción` and `cancion` differ by one edit with accents ignored and case respected).
- **German ß** (case option on): its lowercase is itself, so `ß` is not folded to `ss`: `Straße` and `STRASSE` differ by two edits. `ẞ` (U+1E9E) lowercases to `ß`, so `STRAẞE` matches `Straße`. A full case folding would equate them; it is not used because Dart cannot reproduce it without a large table of special cases.
- **Turkish** (case option on): no locale rule applies. `İ` (U+0130) is decomposed by NFD to `I` + U+0307 before lowercasing: with the accent option on the mark is removed and the result is `i`; with the accent option off the result is `i` + U+0307 (two code points, one edit from `i`). The dotless `ı` (U+0131) stays `ı` and does not match `i`; `I` becomes `i`.
- **Greek sigma** (case option on): `Σ` becomes `σ`; the final form `ς` is a different letter and does not match `σ`.
- **Apostrophes and quotes** (`'`, U+2019, `"`) are P* and removed: `Don’t` becomes `dont`. Emoji and symbols are S* and removed: a word made only of them is not scorable (6.8).
- Only the two play settings change the output of the comparison normalization; no other option exists, and the song normalization has no input but the text.

### 3.3 Table for Dart

Dart has no Unicode normalization, no general category lookup and no lowercase mapping that is fixed to a Unicode version, and the rules need no third-party package. The Dart implementation therefore uses **generated tables** (produced only with the `uv` Python 3.14, Unicode 16.0.0, never with the WSL system `python3`, section 1.7), produced by a script from the Python `unicodedata` module running with Unicode 16.0.0 (or directly from the Unicode Character Database 16.0.0 files), committed with the Dart sources: (a) the canonical decomposition mapping, applied recursively, plus the canonical combining class, plus the Hangul algorithm; (b) the code point ranges of general category Mn; (c) the ranges of categories P*, S*, Z*, Cc and Cf; (d) the simple lowercase mapping. The runtime `RegExp` Unicode classes, `toLowerCase` and `normalize`-like functions of Dart must not be used for these rules, because their Unicode version is not under the project's control.

### 3.4 Examples

In the table, "accent" and "case" are the two play settings (on = the option ignores the difference); unless said, the row uses the comparison normalization of those settings, and "song" means the song normalization (both on).

| Input | Accent | Case | Steps | Normalized |
|---|---|---|---|---|
| `Canción,` | on | on (also the song normalization) | NFD: `Cancio` U+0301 `n,`; remove U+0301; lowercase; remove `,` | `cancion` (7) |
| `Canción,` | off | on | NFD kept: `Cancio` U+0301 `n,`; lowercase; remove `,` | `cancio` U+0301 `n` (8) |
| `Canción,` | on | off | NFD; remove U+0301; lowercase skipped; remove `,` | `Cancion` (7) |
| `Canción,` | off | off | NFD kept; lowercase skipped; remove `,` | `Cancio` U+0301 `n` (8) |
| `Canción,` | off | off, song normalization | the song normalization ignores the settings | `cancion` (7) |
| `Ñandú!` | on | on | NFD: `N` U+0303 `andu` U+0301 `!`; marks removed; lowercase; `!` removed | `nandu` (5) |
| `Don’t` | on | on | U+2019 is Pf, removed | `dont` (4) |
| `İstanbul` | on | on | NFD: `I` U+0307 `stanbul`; mark removed; lowercase | `istanbul` (8) |
| `İstanbul` | off | on | NFD: `I` U+0307 `stanbul`; marks kept; lowercase | `i` U+0307 `stanbul` (9) |
| `STRAẞE` | on | on | lowercase of U+1E9E is `ß` | `straße` (6) |
| `—` (em dash) | any | any | U+2014 is Pd, removed under every setting | empty: not scorable |
| `Hello,` | on | on | `,` removed | `hello` (5) |
| `Hello,` | on | off | `,` removed, lowercase skipped | `Hello` (5) |

## 4. Word accuracy

For an expected word and a typed text, two *candidate pairs* are computed and the lower one is the accuracy (6.11, A5, decision D17). For a normalization `N` (a function of the text), let `e = N(expected)` and `t = N(typed)`:

- `d` is the Levenshtein distance between `e` and `t` over code points: the least number of single-code-point insertions, deletions and substitutions, each of cost 1 (no transposition: swapping two neighbors costs 2).
- `L = max(len(e), len(t))`. Since `e` is not empty for a scorable word (section 3.2), `L >= 1`. The candidate is the pair `(L - d, L)`, **not reduced**. Because `d <= L`, its ratio is between 0 and 1.
- The **play pair** `(a_p, L_p)` is the candidate under the comparison normalization of the play settings `s` (`N = normalize(., s)`, section 3.2). The **song pair** `(a_o, L_o)` is the candidate under the song normalization (both options on).
- The **accuracy** is the lower of the two ratios, compared exactly by cross-multiplication of integers: the play pair is selected when `a_p x L_o < a_o x L_p` (strictly lower); in every other case (equal ratios, or the song pair lower) the **song pair is selected**, so that equal ratios with different denominators always report the song pair, in both implementations. The selected pair `(L - d, L)` (written `(a, L)` with `a = L - d` when only it is meant) is the pair of the word result and the one used by sections 8, 9, 10 and 14. With both options on the two pairs are the same pair, and nothing changes.
- The base word length `Lexp` of the points (section 8) is not the `L` of the selected pair: it is the length of the expected word under the song normalization.
- The accuracy meets a percentage `p` when `a x 100 >= p x L` for the selected pair (so exactly `p` percent meets it). The MISS-by-accuracy check (section 8), the combo threshold (section 9) and the line bonus (section 10) all use the selected pair.
- **Property (6.11):** for the same expected word and typed text, the accuracy under any play settings is never greater than the accuracy under both options on, "greater" meaning the ratio compared by cross-multiplication, not the numerator or the pair (a selected pair 7/9 has a larger numerator than 4/5 but a lower ratio), because it is the lower of the play ratio and the song ratio, and the latter is the both-on ratio. The runners check it (section 17).
- A typed text that normalizes to empty (for example `!!!`) is not an empty commit: it gives `d = len(e)`, `L = len(e)` and the ratio 0 for each candidate; the ratios are equal, so the song pair `0 / L_o` is selected.
- The expired, skipped and never-reached words (sections 11, 12 and 14) have the accuracy `(0, 1)`.

Examples (both options on unless said):

- `canción` expected, `cancion` typed: `e = t = cancion`, `d = 0`, `L = 7`: accuracy 7/7.
- `canción` expected, `cansion` typed: `d = 1`, `L = 7`: accuracy 6/7.
- Accent option off, `canción` expected, `cancion` typed: play pair: `e` has 8 code points, `t` has 7, `d = 1`, `L = 8`, 7/8; song pair 7/7. `7 x 7 = 49 < 7 x 8 = 56`: the play pair is lower and is selected: accuracy 7/8.
- Case option off, `Hello` expected, `hello` typed: play pair `e = Hello`, `t = hello`, `d = 1`, `L = 5`, 4/5; song pair 5/5; `4 x 5 = 20 < 5 x 5 = 25`: selected 4/5, and `400 >= 80 x 5 = 400`: exactly 80 %, meets the combo threshold. With the case option on the same commit is 5/5.
- Accent option on, case option off, `Canción` expected, `cancion` typed: play pair `e = Cancion`, `t = cancion`, `d = 1`, `L = 7`, 6/7; song pair 7/7: selected 6/7.
- Both options off, `Canción` expected, `cancion` typed: play pair `e = Cancio` U+0301 `n` (8), `t = cancion` (7), two edits (`C` to `c`, delete U+0301), `d = 2`, `L = 8`, 6/8; song pair 7/7; `6 x 7 = 42 < 7 x 8 = 56`: selected 6/8 (75 %: accepted, below 80 %).
- Accent option off, `áéíb` expected, `áéíc` typed (the marks are the same, the last letter differs): play pair: `e` and `t` have 7 code points (each of the three marks kept), `d = 1`, `L = 7`, 6/7; song pair: `aeib` and `aeic`, `d = 1`, `L = 4`, 3/4. `6 x 4 = 24 > 3 x 7 = 21`: the play ratio is higher, so the **song pair 3/4 is selected**. Without the rule the longer length of the kept marks would raise the accuracy of a word whose typed text shares every mark with the expected word; with it the accuracy is the one of the default play.
- Tie rule: if a play pair and the song pair have equal ratios with different denominators, the song pair is reported (for example 6/8 and 3/4: `6 x 4 = 24 = 3 x 8`, selected 3/4).
- `hello` / `helxx`: `d = 2`, `L = 5`: 3/5, and `3 * 100 = 300 >= 60 * 5 = 300`: exactly 60 %, accepted. `hello` / `hexxx`: `d = 3`: 2/5, `200 < 300`: below 60 %, MISS.
- `hello` / `hellx`: `d = 1`: 4/5, `400 >= 80 * 5 = 400`: exactly 80 %, meets the combo threshold. `melody` / `melxxy`: `d = 2`, `L = 6`: 4/6, `400 < 480`: 66.7 %, below 80 % and above 60 %.
- `bright` / `brigth`: two substitutions, `d = 2`, `L = 6`: 4/6.
- `no` / `nonsense`: `d = 6`, `L = 8`: 2/8 (never negative however long the typed text is).
- `hello` / `helloo`: `d = 1`, `L = 6`: 5/6 (the denominator is the longer length).

## 5. Typing model

1. The words of the song are typed in order. The *current word* is the first scorable word that has no result yet. There is no other cursor, and a commit can never be applied to another word (6.5).
2. A commit carries the typed text. A commit applies to the current word only. Space or Enter with nothing typed produces no commit at all: the game records no event and nothing changes (6.9); a log that contains a commit with an empty text is malformed (section 15).
3. A word that is not scorable is skipped: it is never current, gets no result, gives no points and counts in no total (6.8). It still has a global word index.
4. **Lead-in** (6.7): the current word accepts a commit at playhead `t` only when `t >= line start - lead_in_ms`, where *line start* is the start of the line that holds the word. The limit is inclusive: at exactly `line start - 1500` the word is open. Before that the word is *locked*. The game does not record a commit attempted while the word is locked (A20); an event log that contains one is rejected as `INCONSISTENT_WORD_INDEX` (section 15). Only the current word needs checking: every other word of the song comes after it.
5. When a commit is applied, the word gets a result (sections 4, 7, 8), the combo is updated (section 9), the line bonus may be decided (section 10) and the current word becomes the next scorable word without a result.
6. No points are given for time passing: the score changes only when a commit is applied (7.10).
7. The game rules A30 (Space and Enter do nothing while paused or locked and the text stays typed) belong to the game screen and are not scoring rules.

Examples:

- Line start 10000. The word is open from playhead 8500: a commit at `t = 8500` is accepted; at `t = 8499` it is locked.
- Typing nothing and pressing Space records nothing; typing `!!` and pressing Space records a commit with accuracy 0/L (a MISS that advances).

## 6. Expected time per word

This rule is implemented in Python only (`timeline.py`, 9.10); Dart only reads timelines that already carry the times. It builds the timeline from the lines of a song, each with a start time `start_ms` and a text.

### 6.1 Line end (A11)

For line `i` of `n` lines (starts in non-decreasing order, otherwise the input is invalid):

- if `i < n - 1`: `end = min(start[i + 1], start[i] + max_line_window_ms)`, that is the start of the next line, but the line never lasts more than 6000 ms (a longer wait is an instrumental gap);
- if `i = n - 1` (last line): `end = start + last_line_window_ms` (5000 ms).

Empty lines have a start and an end by the same rule and no words. The duration of the video is not used by the rule.

### 6.2 Expected time (brief 8.2 formula)

For a scorable word `w` of a line:

```
expected_ms(w) = start + (chars_through(w) / total_chars) x (end - start) x 0.9
```

written out with integers, with `W = end - start` and `p = expected_time_pct = 90`:

```
expected_ms(w) = start + round_half_up( chars_through(w) x W x p / (total_chars x 100) )
```

- `chars_through(w)` is the sum of the lengths (code points) of the **song-normalized** texts (section 3.2) of the scorable words of the line from the first one up to and including `w`; `total_chars` is the same sum over all scorable words of the line. Spaces, punctuation and removed marks are not counted. The play settings never change these lengths or the times (6.11): one timeline serves every play of the song.
- A word whose song-normalized text is empty gets no expected time (`null`), even if a source supplies a time for it; it is not counted in either sum.
- The rounding is done once, on the offset from `start`, to integer milliseconds, half up (section 1). `start` is an integer, so rounding the offset or the sum gives the same value.
- **Word times supplied by a source take precedence**: when a source provides a time for a word, that integer is used as is and the rule is not applied to that word; the other words of the line still use the rule, with the same `chars_through` and `total_chars` (supplied words are counted in both sums). Scoring only reads `expected_ms` and does not know where it came from.
- Precondition of every timeline (computed or supplied): the `expected_ms` of the scorable words, taken in global word order, never decrease. The rule above guarantees it.

### 6.3 Examples

Lines of the running example (the text is synthetic):

| Line | Start | Next start | End | Window `W` |
|---|---|---|---|---|
| 0 `Hello, bright moon` | 10000 | 20000 | `min(20000, 10000 + 6000) = 16000` (gap capped) | 6000 |
| 1 `Sky up` | 20000 | 24025 | `min(24025, 26000) = 24025` | 4025 |
| 2 `La la la` (last) | 24025 | none | `24025 + 5000 = 29025` | 5000 |

Line 0: normalized words `hello` (5), `bright` (6), `moon` (4), `total_chars = 15`.

- `hello`: through 5: `5 x 6000 x 90 = 2700000`, `15 x 100 = 1500`, `2700000 / 1500 = 1800` exactly: `10000 + 1800 = 11800`.
- `bright`: through 11: `11 x 6000 x 90 = 5940000`, `/ 1500 = 3960`: `13960`.
- `moon`: through 15: `15 x 6000 x 90 = 8100000`, `/ 1500 = 5400`: `15400`.

Line 1: `sky` (3), `up` (2), `total_chars = 5`, `W = 4025`. Both offsets end in a half:

- `sky`: `3 x 4025 x 90 = 1086750`, `5 x 100 = 500`, `1086750 / 500 = 2173.5`, half up `2174`: `22174`.
- `up`: `5 x 4025 x 90 = 1811250`, `/ 500 = 3622.5`, half up `3623`: `23623`.

Line 2: `la` (2) three times, `total_chars = 6`, `W = 5000`: `2 x 5000 x 90 / 600 = 1500` gives `25525`; `4 x 5000 x 90 / 600 = 3000` gives `27025`; `6 x 5000 x 90 / 600 = 4500` gives `28525`.

A line `Oh — yes`: the word `—` normalizes to empty, so it gets `null`, `total_chars` counts only `oh` (2) and `yes` (3).

A line with accents, start 30000, next start 34000 (`W = 4000`): `Canción` (song-normalized `cancion`, 7) and `sí` (`si`, 2), `total_chars = 9`. `Canción`: `7 x 4000 x 90 = 2520000`, `9 x 100 = 900`, `2520000 / 900 = 2800` exactly: `32800`. `sí`: `9 x 4000 x 90 / 900 = 3600`: `33600`. These times are the same whatever the play settings are; with the accent option off a comparison would count 8 and 3 code points (`canción`, `sí` with their marks), but the times do not use that count.

## 7. Timing tiers

`delta = playhead time of the commit - expected_ms of the word` (negative: early). The tier is chosen by `abs_delta = |delta|` and the sign:

| Condition | Tier | Timing multiplier |
|---|---|---|
| `abs_delta <= tier_perfect_limit_ms` (600) | PERFECT | `tier_perfect_pct` (100) |
| `600 < abs_delta <= tier_great_limit_ms` (1200) | GREAT | 80 |
| `1200 < abs_delta <= tier_good_limit_ms` (2200) | GOOD | 55 |
| `2200 < abs_delta <= tier_ok_limit_ms` (3500) | OK | 30 |
| `delta < -tier_ok_limit_ms` | EARLY | `tier_early_pct` (10) |
| `delta > tier_ok_limit_ms` | MISS | 0 |

Every limit belongs to the better tier (A8). The tiers are symmetrical around 0 for `abs_delta <= 3500`: the same limits apply before and after the expected time.

Examples (expected time 22174): commit at 22774 (`delta = 600`) PERFECT; 22775 (601) GREAT; 23374 (1200) GREAT; 23375 (1201) GOOD; 24374 (2200) GOOD; 24375 (2201) OK; 25674 (3500) OK; 25675 (3501) MISS (never reached in normal play, because the word expired at `delta > 3500`, section 11, so in a replay with the default constants a commit to it is rejected as an inconsistent index). Before: 21574 (`-600`) PERFECT; 18674 (`-3500`) OK; 18673 (`-3501`) EARLY.

## 8. Word points

When a commit is applied to the current word, in this order:

1. Compute the accuracy (section 4): the lower of the play pair and the song pair, giving the selected pair `(L - d, L)`.
2. If `(L - d) x 100 < min_accuracy_pct x L` (below 60 %, on the selected pair): the word is a **MISS** with 0 points, the combo resets (section 9) and the current word advances (6.4). Accuracy exactly 60 % is not below.
3. Otherwise compute the tier (section 7). If the tier is MISS (late by more than 3500 ms): MISS, 0 points, combo resets; the word keeps its selected pair `(L - d, L)` as accuracy (D7).
4. Otherwise the word is scored with the tier and the points are:

```
N = base_points_per_char x Lexp x (L - d) x tier_pct x combo_pct
D = L x 100 x 100
points = round_half_up(N / D) = floor((2N + D) / (2D))
```

where `Lexp = len(song_normalize(expected))` (the length of the **expected** word under the song normalization, whatever the play settings are, 6.11 and 7.4), `L - d` and `L` come from the **selected accuracy pair** of section 4 (the lower of the play pair and the song pair; `L` is the longer of the two lengths of the normalization of that pair, A5), `tier_pct` is the integer percentage of the tier and `combo_pct` is the combo multiplier of section 9 computed with the combo count **before** this word (A7). This is the brief formula `10 x length x accuracy x timing x combo` with the multipliers as integer percentages, a single multiplication and a **single rounding per word, half up** (A6). The score of the play is the sum of the integer word points plus the line bonuses.

Examples:

- `hello` (`Lexp = 5`) typed `Hello` at `delta = -500` (PERFECT, 100), combo 0 (100): `N = 10 x 5 x 5 x 100 x 100 = 2500000`, `D = 5 x 10000 = 50000`, `N / D = 50` exactly: 50 points.
- `bright` typed `brigth` at `delta = +700` (GREAT, 80), combo 1 (100): accuracy 4/6, `N = 10 x 6 x 4 x 80 x 100 = 1920000`, `D = 6 x 10000 = 60000`: 32 points exactly.
- `moon` typed `moon` at `delta = +3500` (OK, 30), combo 1: `N = 10 x 4 x 4 x 30 x 100 = 480000`, `D = 40000`: 12 points.
- A longer typed text, `hello` expected, `helloo` typed, PERFECT, combo 0: accuracy 5/6, `Lexp = 5`, `L = 6`: `N = 10 x 5 x 5 x 100 x 100 = 2500000`, `D = 60000`, `N / D = 41.67`, `(2 x 2500000 + 60000) / 120000 = 42.17`, floor 42: 42 points.
- Half rounding: `hello` PERFECT with combo 10 (125): `N = 10 x 5 x 5 x 100 x 125 = 3125000`, `D = 50000`, `N / D = 62.5`, `(6250000 + 50000) / 100000 = 63`: 63 points.
- Accuracy exactly 60 %: `hello` typed `helxx` at PERFECT, combo 0: `N = 10 x 5 x 3 x 100 x 100 = 1500000`, `/ 50000 = 30` points (accepted). `hello` typed `hexxx` (40 %): MISS, 0 points.

Examples with the play settings. In every one `canción` or `Canción` has `Lexp = 7` (song normalization), the tier is PERFECT (100) and the combo is 0 (100); only the comparison changes:

- Both options on, `canción` typed `cancion`: accuracy 7/7, `N = 10 x 7 x 7 x 100 x 100 = 4900000`, `D = 7 x 10000 = 70000`: 70 points.
- Accent option off (case on), `canción` typed `cancion`: `d = 1`, `L = 8`, accuracy 7/8, `N = 10 x 7 x 7 x 100 x 100 = 4900000`, `D = 8 x 10000 = 80000`, `N / D = 61.25`, `(9800000 + 80000) / 160000 = 61.75`, floor 61: 61 points (`Lexp` stays 7 although the expected word has 8 code points under this comparison).
- Case option off (accent on), `Hello` expected and typed `hello`: `Lexp = 5`, `L = 5`, `d = 1`, accuracy 4/5: `N = 10 x 5 x 4 x 100 x 100 = 2000000`, `D = 50000`: 40 points (50 with the case option on). Accuracy 80 %: the combo increases by 1.
- Case option off (accent on), `Canción` typed `cancion`: `L = 7`, `d = 1`, accuracy 6/7: `N = 10 x 7 x 6 x 100 x 100 = 4200000`, `D = 70000`: 60 points.
- Both options off, `Canción` typed `cancion`: `L = 8`, `d = 2`, accuracy 6/8: `N = 10 x 7 x 6 x 100 x 100 = 4200000`, `D = 80000`, `N / D = 52.5`, `(8400000 + 80000) / 160000 = 53`: 53 points, half up. Accuracy 75 %: accepted, the combo is unchanged.

The accuracy of every example above is the lower of the play pair and the song pair (section 4); in each option-off one the play pair is the lower one, so it is the pair used (with both options on the two pairs coincide).

The mixed case: `áéíb` expected, `áéíc` typed, accent option off (case on), PERFECT, combo 0, `Lexp = 4`. The play pair is 6/7 and the song pair 3/4 (section 4); the song pair is lower, so `L = 4`, `d = 1`, `N = 10 x 4 x 3 x 100 x 100 = 1200000`, `D = 4 x 10000 = 40000`: 30 points, the same as with both options on (30). The play pair alone would have given `N = 2400000`, `D = 70000`, 34 points; the rule of section 4 prevents it.

**Property (6.11, D17).** For the same timeline and event log, a word never gets more accuracy, a word never gets more points, and the play never gets a larger score under any play settings than with both options on. Reasons: the options never change `Lexp`, the scorable words, the expected times or the maximum base score; the accuracy is never above the both-on accuracy (section 4); the points formula, the tier checks and the half-up rounding are non-decreasing in the accuracy ratio for fixed `Lexp`, tier and combo; the combo count and a line bonus (which needs every word at or above 80 %) can only be lower or equal. Typed exactly, a word gets the same points under every setting. The runners check this property (section 17).

## 9. Combo

The combo is a count of words, starting at 0, with the maximum `max_combo` kept for the result.

**Multiplier** (7.8), from the combo count `c`:

```
combo_pct(c) = min(combo_cap_pct, combo_base_pct + (c div combo_step_words) x combo_step_pct)
```

`c div 10` is the integer division. The multiplier used for a word is the one of the combo **before** the word is added (A7): the first ten words of a streak (`c = 0..9`) are at 100, the eleventh (`c = 10`, the boundary belongs to the higher step) at 125.

| `c` | 0 | 9 | 10 | 19 | 20 | 30 | 39 | 40 | 41 | 50 |
|---|---|---|---|---|---|---|---|---|---|---|
| `combo_pct` | 100 | 100 | 125 | 125 | 150 | 175 | 175 | 200 | 200 | 200 |

At `c = 40`: `100 + 4 x 25 = 200`, equal to the cap; at 50: `min(200, 225) = 200`.

**Transition** after a commit is applied (the combo changes only here and in the expiry rules):

| Case | Effect |
|---|---|
| The word is a MISS for any reason (accuracy below 60 %, too late, expired, skipped, never reached) | combo becomes 0 |
| Tier PERFECT, GREAT or GOOD **and** accuracy meets `combo_accuracy_pct` (`(L - d) x 100 >= 80 x L`) | combo increases by 1 |
| Tier OK or EARLY (any accuracy of 60 % or more), or tier PERFECT, GREAT or GOOD with accuracy from 60 % up to but not including 80 % | combo unchanged |

`max_combo` is the highest value the combo reaches at any time.

Examples: ten PERFECT words of accuracy 1 in a row score at `combo_pct` 100 and leave the combo at 10; the eleventh is scored at 125 (the 63 points above for a 5-letter word); a MISS then sets it to 0 and the next word is at 100 again. `hello`/`hellx` GOOD (accuracy 80 %): +1. `melody`/`melxxy` PERFECT (66.7 %): unchanged. A PERFECT with accuracy 1 is +1; an OK with accuracy 1 is unchanged.

## 10. Line bonus

A line has a *bonus* of `line_bonus` (50) points, **not multiplied by the combo**, under these conditions, decided at the moment the **last scorable word of the line** gets its result (by commit, expiry, seek or the end of the play):

- every scorable word of the line has a result that is not MISS, and
- every one of them has accuracy meeting `combo_accuracy_pct` (80 %, boundary included); tier does not matter (OK and EARLY words qualify).

A line with no scorable word has no bonus. A word that is a MISS by expiry, skip or never reached denies the bonus (its accuracy is 0/1). The bonus is added to the score and shown separately in the line breakdown. The line bonus uses the same 80 % constant as the combo (decision D4).

Examples: line 1 of the running play: `sky` OK with 3/3 and `up` EARLY with 2/2: both at 100 %, no MISS: bonus 50. Line 0 of the same play: `bright` has 4/6 (66.7 %, below 80 %): no bonus. A line whose last word expires: that word is a MISS: no bonus.

## 11. Catch-up (expiry)

A scorable word without a result **expires** when `playhead - expected_ms > miss_window_ms` (strictly greater: at exactly 3500 ms after the expected time the word is still open; a commit at `delta = +3500` is tier OK). An expired word becomes a MISS with accuracy `(0, 1)` and 0 points, the combo becomes 0, the line bonus is decided if it was the last scorable word of its line, and the current word moves to the first scorable word that has not expired (6.6).

Expiries are applied **in word order, starting from the current word**: while the current word has expired, it is resolved as a MISS and the next scorable word is examined; the scan stops at the first word that has not expired. Because expected times never decrease along the song (section 6.2), the words after that one cannot have expired either.

The live engine applies the expiries as the playhead advances (`advanceTo`). The replay applies them **before every event, at the time of that event**, and once more at the end of the play (section 13). This makes the live result and the replayed result identical: a word that expired between two events is already a MISS when the next event is looked at.

**Precondition of that equality (decision D21).** The live result equals the replayed one only if the game keeps the playhead it gives the engine non-decreasing except through a seek, and records every event with the engine's current playhead: the time of a recorded event is never below the last value given to `advanceTo`. An interpolated playhead that would step back by a few milliseconds without a seek is clamped to the last value (the game never gives the engine a smaller playhead, and never records an event time smaller than the previous one). A seek is recorded before any `advanceTo` with the destination playhead, so the engine and the replay both apply the expiries of the seek at `max(from, t)` first. Without this condition the live engine could have expired a word at time T and then accept a commit recorded below T, which the replay at that time would reject.

Example (running play): after `hello` (resolved at 11800) the current word is `bright` (13960). At playhead 17460 (`17460 - 13960 = 3500`) it is still open. At 17461 (`3501`) it expires. A commit at `t = 19000`: `bright` expired (`19000 - 13960 = 5040`), `moon` expired (`19000 - 15400 = 3600 > 3500`), `sky` has not (it is before its own time by 3174): the current word is `sky` (global index 3). A commit with `word = 2` at that time is an inconsistent index.

Example across a line boundary (running timeline, play settings both on): events `[commit {word 3, "sky", t = 22174}, commit {word 5, "la", t = 28000}]`. Event 0: expiries at 22174 resolve in word order `hello` (`22174 - 11800 = 10374`), `bright` and `moon` as MISS (line 0 is complete with no bonus; combo 0); `sky` is not expired. The commit is accepted: `delta = 0`, PERFECT, 3/3, combo 0 (100), `N = 10 x 3 x 3 x 100 x 100 = 900000`, `D = 30000`: 30 points, combo 1. Event 1: expiries at 28000: `up` (`28000 - 23623 = 4377 > 3500`) expires as MISS, the combo becomes 0, and as the last scorable word of line 1 its resolution decides the bonus: `sky` is not a MISS but `up` is, so no bonus. `la` (word 5, `28000 - 25525 = 2475`) has not expired and is current: `delta = 2475`, tier OK (30), 2/2, `N = 10 x 2 x 2 x 30 x 100 = 120000`, `D = 20000`: 6 points, combo unchanged (0). End: words 6 and 7 are MISS. Score `30 + 6 = 36`.

## 12. Pause, resume and seek

**Pause and resume** events carry only the playhead time. They are recorded for the plausibility checks of a later spec (A10) and have **no effect** on the score, the combo, the current word or the result: times in the log are playhead times, which do not advance while the game is paused. Buffering is recorded as a pause followed by a resume. The replay does not require pauses and resumes to alternate: any sequence is accepted.

**Seek** event: `t` is the playhead **after** the seek (the destination) and `from` is the playhead **before** it. The game detects a seek (a jump of more than 1.5 s against wall-clock progress, 14.5) and records the event; that detection threshold is not a scoring constant. Processing a seek event:

1. apply the expiries (section 11) at time `from` and then at time `t`, which means at `max(from, t)`: words that expired while the playhead moved up to `from` are resolved first, and on a forward seek the words that the destination leaves more than 3500 ms behind are the *skipped words*: they become MISS, in word order, each with the effects of section 11 (combo 0, bonus decided);
2. the current word is the first scorable word without a result (the one the expiries stopped at); it is not changed otherwise;
3. words that already have a result **keep it** on any seek, backward included; they are never scored again (14.7);
4. the play result has `seeked = true` (9.7).

A backward seek therefore leaves the current word where it was; it is typeable again only when the new playhead has reached the lead-in of its line (section 5).

Example (running timeline): `hello` committed at 11800, then a seek from 12000 to 26000. Expiries at 26000: `bright` (`26000 - 13960 = 12040`), `moon` (`10600`), `sky` (`26000 - 22174 = 3826`) are MISS; `up` (`26000 - 23623 = 2377`) is not: the current word is `up` (index 4). A commit `{word 4, "up", t = 26100}`: `delta = 2477`, tier OK (30), points `N = 10 x 2 x 2 x 30 x 100 = 120000`, `D = 2 x 10000 = 20000`, 6 points; the combo was reset to 0 by the skipped words and stays 0 (OK is neutral). Line 1 has no bonus (`sky` is a MISS).

Backward seek (running timeline): events `[commit {word 0, "Hello", t = 11300}, seek {t = 5000, from = 12000}, commit {word 1, "bright", t = 5000}]`. Event 0: `hello` PERFECT, 50 points, combo 1. Event 1: expiries at `max(12000, 5000) = 12000`: `bright` (`12000 - 13960 = -1960`) has not expired; `hello` keeps its result; `seeked` is true; the current word is still `bright` (index 1). Event 2: the time check passes (`5000 >= 5000`), but `bright` is on line 0 (start 10000) and is locked until `10000 - 1500 = 8500`: rejected as `INCONSISTENT_WORD_INDEX` at index 2. With the commit at `t = 8499` the answer is the same; at `t = 8500` it is accepted: `delta = 8500 - 13960 = -5460 < -3500`, tier EARLY (10), accuracy 6/6, `N = 10 x 6 x 6 x 10 x 100 = 360000`, `D = 60000`: 6 points, combo unchanged (1).

## 13. Replay procedure

`score_play(timeline, settings, events, config)` returns either a play result or a rejection. The *play input* is the play settings (section 15.6) next to the event log (section 15.1), never inside it. Dart `replay` does the same, and the incremental engine of the game applies the same steps one event at a time, with the settings fixed when the play started.

0. **Validate the play settings** (section 15.6) before anything else, even before the log is looked at: a settings value that is not valid rejects the play as `MALFORMED_PLAY_SETTINGS` with `event_index` null. From here on, every comparison of a typed text uses these settings and nothing else (never the configuration).
1. **Validate the structure** of the whole event log (section 15.2). The first malformed event, in log order, rejects the log as `MALFORMED_EVENT_LOG` with its index.
2. State: current word = the first scorable word, combo 0, `max_combo` 0, no results, `seeked` false, previous time none.
3. For each event `e` at index `i`, in log order:
   1. **Time check** (15.3): for a `commit`, `pause` or `resume`, `e.t` must be `>=` the previous event's time; for a `seek`, `e.from` must be `>=` the previous event's time. Otherwise reject as `NON_MONOTONIC_TIME` at `i`. The "previous time" after an event is its `t` (for a seek, the destination).
   2. **Expiries**: apply section 11 at `e.t` (for a seek at `max(e.from, e.t)`).
   3. **Apply the event**:
      - `commit`: if there is no current word, or `e.word` is not the current word, or the current word is locked (`e.t < line start - lead_in_ms`): reject as `INCONSISTENT_WORD_INDEX` at `i`. Otherwise apply the commit (sections 8, 9, 10).
      - `pause`, `resume`: nothing.
      - `seek`: set `seeked` true (expiries were already applied in the previous step).
4. **End of the log**: every scorable word that still has no result becomes a MISS with accuracy `(0, 1)` and 0 points (8.3), in word order, with the combo and bonus effects of section 11 (they cannot change the score or `max_combo`: a bonus is denied and `max_combo` already holds its maximum). No time is needed.
5. Compute the result (section 14), which includes the play settings used.

The replay of a log is equal to the result of the live engine only under the precondition of section 11 (decision D21): the recorded times are the engine's playheads, non-decreasing except through a seek.

Equal timestamps are allowed (a time is `>=` the previous one, not `>`). Events with the same `t` are processed in log order, each one preceded by the expiries at that `t` (applying them again changes nothing). An expiry at time `t` always happens before any event at time `t`: a word exactly `3501` ms late at `t` is already a MISS when a commit at `t` is looked at, and the commit to it is rejected as inconsistent.

At most one rejection is reported: the first one found, with the order of precedence "the play settings" (step 0), then "all structural checks of every event" (step 1), then, event by event, time check before consistency check. A play with invalid settings and a malformed log is therefore rejected as `MALFORMED_PLAY_SETTINGS`, with no index.

Example (play settings both options on): events `[commit word 0 "hello" t 11800]`, `[pause t 14000]`, `[resume t 14000]`, `[commit word 3 "sky" t 19000]`. Event 0: expiries at 11800 (none), commit applied, 50 points. Events 1 and 2: expiries at 14000 (`14000 - 13960 = 40`, none); nothing else. Event 3: expiries at 19000 make `bright` and `moon` MISS, the current word is 3, and the commit `sky` at `delta = -3174` is tier OK: 9 points (`N = 10 x 3 x 3 x 30 x 100 = 270000`, `D = 30000`). End: the four remaining words (4, 5, 6 and 7) are MISS. Score 59, maximum combo 1 (after `hello`; `bright` and `moon` reset to 0, `sky` is neutral).

Example of an empty log (running timeline, both options on): events `[]` are valid. At the end every scorable word is MISS `(0, 1)` with 0 points (the eight words, indexes 0 to 7); every line has points 0 and bonus 0; `score = 0`, `max_combo = 0`, `hit_words = 0`, `scorable_words = 8`, `accuracy_bp = 0`, `hit_rate_bp = 0`, `max_base_score = 260`, `seeked = false`; rank: `0 >= 35 x 260 = 9100` is false, so rank D (and for a song with `n = 0` the rank is D by the special rule of section 14.4, not by the comparisons).

Example of a malformed log (running timeline): events `[{"type":"commit","t":11300,"word":0,"text":"Hello"},{"type":"pause","t":14000.5}]`. Event 1 has a `t` that is not an integer, so the log is malformed at index 1, before any replay: `{"reason": "MALFORMED_EVENT_LOG", "event_index": 1}`. The same log with a commit `{word 7, ...}` at index 0 that would be inconsistent still reports index 1.

Example of a commit to a word that is not scorable (D9): timeline with the line `Oh — yes` at start 40000, next line start 44000 (`W = 4000`), global word indexes 0 `Oh`, 1 `—`, 2 `yes` (times: `oh` through 2: `2 x 4000 x 90 / (5 x 100) = 1440`, `41440`; `yes` through 5: `5 x 4000 x 90 / 500 = 3600`, `43600`; `—` has `null`). Events `[commit {word 0, "oh", t = 41440}, commit {word 1, "x", t = 42000}]`: event 0 is accepted (PERFECT); event 1 is rejected as `INCONSISTENT_WORD_INDEX` at index 1, because the current word is 2 (word 1 is never current), although index 1 is inside the song and the log is not malformed.

## 14. Play result

### 14.1 Per word and per line

Every scorable word of the timeline ends with exactly one result: `tier` (PERFECT, GREAT, GOOD, OK, EARLY or MISS), `accuracy` `(num, den)` and `points`. Words never reached or never committed are MISS with `(0, 1)` (8.3). A commit that is a MISS, because of its accuracy or because it is too late (section 8 step 3), keeps its selected accuracy pair `(L - d, L)` (section 4) and 0 points.

Every line of the timeline has `points` (sum of its word points, bonus excluded) and `bonus` (0 or `line_bonus`). A line with no scorable word has points 0, bonus 0 and no words.

### 14.2 Totals

With `n` = the number of scorable words of the song:

- `score` = the sum of all word points plus all line bonuses (an integer).
- `max_combo` as in section 9.
- `hit_words` = the number of scorable words whose tier is not MISS. `scorable_words = n`.
- `max_base_score = base_points_per_char x (sum of Lexp over the scorable words)`, with `Lexp` under the song normalization (section 8), so the maximum base score and the rank scale never depend on the play settings (6.11): the score of a play where every word is PERFECT with accuracy 1, at combo multiplier 100 and no bonus (the formula of section 8 with `L - d = L = Lexp`, `tier_pct = combo_pct = 100` gives `base_points_per_char x Lexp` exactly).

### 14.3 Accuracy and hit rate (A9), in basis points

- `accuracy_bp` is the average accuracy over **all** scorable words: with the exact rational `S = sum over the scorable words of (num / den)`, `accuracy_bp = round_half_up(10000 x S / n)`. A word that is a MISS by expiry, skip or never reached counts 0; a MISS by low accuracy counts its computed accuracy. The sum is exact: `S = P / Q` is accumulated with arbitrary precision integers (`P = P x den + num x Q`, `Q = Q x den`, starting at `P = 0, Q = 1`; reducing the fraction is allowed and does not change the result), and then `accuracy_bp = round_half_up((10000 x P) / (Q x n)) = floor((20000 x P + Q x n) / (2 x Q x n))`.
- `hit_rate_bp = round_half_up(10000 x hit_words / n) = floor((20000 x hit_words + n) / (2 n))`.
- With `n = 0` both are 0.

### 14.4 Rank

If `n = 0` (no scorable word) the rank is D and the comparisons below are not evaluated (decision D20; without this, `0 x 100 >= 90 x 0` would give S). With `n >= 1`, `max_base_score >= 1` because `base_points_per_char >= 1` (section 2). Otherwise the rank compares the score with the maximum base score in integers, from the best to the worst, the first that applies wins; each comparison includes equality:

```
S  if score x 100 >= rank_s_pct x max_base_score
A  if score x 100 >= rank_a_pct x max_base_score
B  if score x 100 >= rank_b_pct x max_base_score
C  if score x 100 >= rank_c_pct x max_base_score
D  otherwise
```

The score includes combo and line bonus, so it can exceed 100 % of the base. A song with no scorable word (`n = 0`, `max_base_score = 0`) gives score 0, `accuracy_bp` 0, `hit_rate_bp` 0, `max_combo` 0, rank D, `scorable_words` 0, `hit_words` 0, and every line with empty word list; it is not an error (8.4). `seeked` and `settings` are still reported.

### 14.5 Result JSON

The play result is a JSON object with exactly these fields (all required, all integers unless stated):

| Field | Type | Meaning |
|---|---|---|
| `settings` | object `{"accent_insensitive": boolean, "case_insensitive": boolean}` | The play settings used to score the play, copied unchanged from the play input (8.1) |
| `score` | integer | Total score |
| `accuracy_bp` | integer 0..10000 | Average accuracy |
| `hit_rate_bp` | integer 0..10000 | Share of words that are not MISS |
| `max_combo` | integer | Highest combo |
| `rank` | string `"S"`, `"A"`, `"B"`, `"C"` or `"D"` | Rank letter |
| `seeked` | boolean | True when the log has a seek event |
| `scorable_words` | integer | `n` |
| `hit_words` | integer | Words that are not MISS |
| `max_base_score` | integer | Base of the rank |
| `lines` | array of line objects | One per timeline line, in order |

A line object: `line` (integer, 0-based line index), `points` (integer), `bonus` (integer), `words` (array of word objects, scorable words only, in order). A word object: `word` (global word index), `tier` (string), `accuracy` (object `{"num": integer, "den": integer}`, not reduced), `points` (integer).

### 14.6 Worked example of a whole play

Timeline of section 6.3 (8 words: indexes 0 to 7; `Lexp` = 5, 6, 4, 3, 2, 2, 2, 2), play settings `{"accent_insensitive": true, "case_insensitive": true}` (the defaults). Events:

| # | Event | Expiries before | Result |
|---|---|---|---|
| 0 | commit word 0 `Hello` at 11300 | none | `delta = 11300 - 11800 = -500`, PERFECT; accuracy 5/5; combo 0 (100); 50 points (section 8); combo 1 |
| 1 | commit word 1 `brigth` at 14660 | `14660 - 13960 = 700`, none | `delta = +700` GREAT; accuracy 4/6 (66.7 %); 32 points; combo unchanged (1) |
| 2 | commit word 2 `moon` at 18900 | `18900 - 15400 = 3500`, not expired | `delta = +3500`, OK; 4/4; 12 points; combo unchanged. Line 0 complete: `bright` is 4/6, so no bonus |
| 3 | commit word 3 `SKY!` at 19000 | none (`sky` is before its time) | open since `20000 - 1500 = 18500`; `delta = 19000 - 22174 = -3174`, OK; 3/3; 9 points |
| 4 | commit word 4 `up` at 20122 | none | `delta = 20122 - 23623 = -3501`, EARLY (10); 2/2; `N = 10 x 2 x 2 x 10 x 100 = 40000`, `D = 20000`, 2 points. Line 1 complete: 3/3 and 2/2, no MISS: bonus 50 |
| 5 | commit word 5 `la` at 25525 | none | `delta = 0`, PERFECT; 2/2; combo 1 (100); `N = 10 x 2 x 2 x 100 x 100 = 400000`, `D = 20000`, 20 points; combo 2 |
| end | words 6 and 7 | | MISS `(0, 1)`; line 2 has no bonus |

Totals: line 0 points `50 + 32 + 12 = 94`, bonus 0; line 1 points `9 + 2 = 11`, bonus 50; line 2 points 20, bonus 0. `score = 94 + 11 + 50 + 20 = 175`. `max_combo = 2`. `n = 8`, `hit_words = 6`. `max_base_score = 10 x (5 + 6 + 4 + 3 + 2 + 2 + 2 + 2) = 260`.

Accuracy: `S = 1 + 4/6 + 1 + 1 + 1 + 1 + 0 + 0 = 17/3`; `accuracy_bp = round_half_up(10000 x (17/3) / 8) = round_half_up(7083.33) = 7083` (with `P = 17`, `Q = 3`: `(20000 x 17 + 3 x 8) / (2 x 3 x 8) = 340024 / 48 = 7083.8`, floor 7083). Hit rate: `10000 x 6 / 8 = 7500`, exactly. Rank: `175 x 100 = 17500`; S needs `90 x 260 = 23400`, A needs `75 x 260 = 19500`, B needs `55 x 260 = 14300`: `17500 >= 14300`: rank **B**. (A score of exactly 234 would give `23400 >= 23400`: rank S.)

The result object (`seeked` is false):

```json
{
  "settings": {"accent_insensitive": true, "case_insensitive": true},
  "score": 175, "accuracy_bp": 7083, "hit_rate_bp": 7500, "max_combo": 2,
  "rank": "B", "seeked": false, "scorable_words": 8, "hit_words": 6, "max_base_score": 260,
  "lines": [
    {"line": 0, "points": 94, "bonus": 0, "words": [
      {"word": 0, "tier": "PERFECT", "accuracy": {"num": 5, "den": 5}, "points": 50},
      {"word": 1, "tier": "GREAT", "accuracy": {"num": 4, "den": 6}, "points": 32},
      {"word": 2, "tier": "OK", "accuracy": {"num": 4, "den": 4}, "points": 12}]},
    {"line": 1, "points": 11, "bonus": 50, "words": [
      {"word": 3, "tier": "OK", "accuracy": {"num": 3, "den": 3}, "points": 9},
      {"word": 4, "tier": "EARLY", "accuracy": {"num": 2, "den": 2}, "points": 2}]},
    {"line": 2, "points": 20, "bonus": 0, "words": [
      {"word": 5, "tier": "PERFECT", "accuracy": {"num": 2, "den": 2}, "points": 20},
      {"word": 6, "tier": "MISS", "accuracy": {"num": 0, "den": 1}, "points": 0},
      {"word": 7, "tier": "MISS", "accuracy": {"num": 0, "den": 1}, "points": 0}]}
  ]
}
```

## 15. Event log, play settings and rejections

A play is judged from its *play input*: the song timeline (section 16), the play settings (section 15.6) and the event log (section 15.1). The play settings sit next to the event log, not inside it, so the format of the event log is the same whatever the options are.

### 15.1 Format

An event log is a JSON array of event objects, in the order in which they happened. An empty array is a valid log (a play with no commits). Every event is an object with exactly these fields, no others:

| Type | Fields |
|---|---|
| commit | `type` = `"commit"`, `t` (integer ms, playhead of the commit), `word` (integer, global word index), `text` (string, the typed text) |
| pause | `type` = `"pause"`, `t` |
| resume | `type` = `"resume"`, `t` |
| seek | `type` = `"seek"`, `t` (playhead after the seek), `from` (integer ms, playhead before the seek) |

`t` and `from` are playhead times of the song in integer milliseconds (never wall-clock times).

Example: `[{"type":"commit","t":11300,"word":0,"text":"Hello"},{"type":"pause","t":14000},{"type":"resume","t":14000},{"type":"seek","t":26000,"from":26500}]`.

### 15.2 Malformed event log (`MALFORMED_EVENT_LOG`, 9.6)

An event is malformed when any of these holds: it is not an object; `type` is missing, not a string, or not one of the four names (unknown type); a required field is missing; a field not listed for its type is present; `t` or `from` or `word` is not an integer in the range of section 1.5 (a string, a float, a boolean, `null`, a negative number are all malformed); `word` is not below the number of words of the timeline (outside the song; the index of a word that is not scorable is inside the song); `text` is not a string, is empty, is longer than `max_typed_chars` code points, or contains an unpaired surrogate. The whole log is malformed, with `event_index = null`, when it is not a JSON array.

All events are checked before any replay, so the reported index is the first malformed event of the log, even if an earlier event would be inconsistent. The play settings are checked before the log (section 15.6), so a play with invalid settings never reaches this check.

### 15.3 Non-monotonic time (`NON_MONOTONIC_TIME`, 9.5)

Times may stay equal but never go backwards, except through a seek. The *previous time* is the `t` of the preceding event (for a seek, its destination `t`). Event `i` is rejected at index `i` when:

- it is a commit, pause or resume and `t` is less than the previous time; or
- it is a seek and `from` is less than the previous time (the playhead before the seek cannot be earlier than the last known playhead). A seek's own `t` may be less than, equal to or greater than `from` and the previous time.

The first event has no previous time. Example: `commit t 12000` then `pause t 11999` without a seek: reject at index 1. `commit t 12000` then `seek from 12000 t 5000` then `commit t 5000` passes the time check (whether that commit is consistent is the separate check of section 15.4; on the running timeline it is not, because the word is locked, see the example of section 12).

### 15.4 Inconsistent word index (`INCONSISTENT_WORD_INDEX`, 9.4, A20)

A commit at index `i` is rejected when, after the expiries at its time, there is no scorable word without a result, or `word` is not the current word, or the current word is locked (`t < line start - lead_in_ms`). Examples: `word = 1` when the current word is 0; `word = 2` after the expiries of section 11 moved the current word to 3; `word = 0` at `t = 8499` with line start 10000 (locked; at 8500 it is accepted).

### 15.5 Rejection object

A rejection carries no score:

```json
{"reason": "NON_MONOTONIC_TIME", "event_index": 1}
```

`reason` is one of the four strings (`MALFORMED_PLAY_SETTINGS`, `MALFORMED_EVENT_LOG`, `NON_MONOTONIC_TIME`, `INCONSISTENT_WORD_INDEX`); `event_index` is the 0-based index of the offending event in the log, or `null` when the reason is `MALFORMED_PLAY_SETTINGS` (no event has been looked at) and when the log is not an array. Invalid input other than the play settings and the event log (a timeline that violates its preconditions, an invalid configuration) is a programming error of the caller and is not a rejection reason.

### 15.6 Play settings and `MALFORMED_PLAY_SETTINGS` (9.11, 9.12, A32)

The play settings are a JSON object with exactly these two fields, both required and both JSON booleans:

| Field | Type | Meaning |
|---|---|---|
| `accent_insensitive` | boolean | `true`: diacritics are ignored when comparing (step 2 of section 3.2 runs); `false`: `cancion` and `canción` differ |
| `case_insensitive` | boolean | `true`: letter case is ignored when comparing (step 3 of section 3.2 runs); `false`: the step is skipped and the exact case is required |

Example: `{"accent_insensitive": true, "case_insensitive": false}`. Every one of the four combinations is valid. The player chooses the values before the play starts and they are fixed for the whole play (Requirement 18); the scoring takes them only from this object, never from the configuration.

The settings are malformed, and the play is rejected as `MALFORMED_PLAY_SETTINGS`, when any of these holds: the value is missing or is not an object (`null`, an array, a string, a number, a boolean); a field is missing; a field is not a JSON boolean (`0`, `1`, `"true"` and `null` are all malformed); a field other than the two listed is present. The rejection has `event_index = null` and is decided before the event log is looked at, so it takes precedence over every log problem (decision D13). Examples: `{"accent_insensitive": true}` (missing field), `{"accent_insensitive": true, "case_insensitive": 1}` (not a boolean), `{"accent_insensitive": true, "case_insensitive": true, "locale": "es"}` (extra field), `null`: all give `{"reason": "MALFORMED_PLAY_SETTINGS", "event_index": null}`.

## 16. Song timeline format

The timeline given to the scoring is a JSON object:

```json
{"lines": [
  {"start_ms": 10000, "end_ms": 16000, "text": "Hello, bright moon",
   "words": [{"text": "Hello,", "expected_ms": 11800},
             {"text": "bright", "expected_ms": 13960},
             {"text": "moon", "expected_ms": 15400}]}
]}
```

- `lines`: array (may be empty), in order. Each line has `start_ms` and `end_ms` (integers, `end_ms >= start_ms`), `text` (string, informative: the scoring reads only `words`) and `words` (array, empty for an empty line).
- Each word has `text` (non-empty string without whitespace) and `expected_ms`: an integer for a scorable word and `null` for a word that normalizes to empty.
- Preconditions (violations are caller errors): line starts do not decrease; the `expected_ms` of scorable words do not decrease in global word order; every expected word has at most 10000 code points after normalization with the accent option off (the longest form, section 1.6). For a fixture the `words` are the words of `text` (section 3.1) and the times and line ends are the output of the rule of section 6 under the song normalization, which a test checks (11.9). A timeline does not depend on the play settings.
- The line end is not used by the scoring; it is part of the format because the game shows it and the fixtures carry it.

## 17. Golden vectors and the canonical configuration

`testdata/scoring/config.json` is the canonical configuration: the flat object of section 2. `testdata/scoring/vector.schema.json` is the JSON Schema of a vector. Each vector is one file `testdata/scoring/vectors/<name>.json`, a JSON object with exactly these fields, all required:

| Field | Type | Meaning |
|---|---|---|
| `name` | string | Unique name, equal to the file name without `.json`; lowercase letters, digits and `-` |
| `description` | string | What the vector tests and, for boundary cases, the arithmetic |
| `config` | object | The **full** configuration (every key of section 2, no other) |
| `overrides` | object | The keys of `config` whose value differs from `config.json`, with their values; `{}` when none. It may not list a key whose value equals the canonical one, and it may not list `default_accent_insensitive` or `default_case_insensitive` (the scoring never reads them, so they could not change a result) |
| `timeline` | object | The timeline of section 16 (may carry any word times that the case needs; only fixtures must match the rule of section 6) |
| `settings` | object | The play settings of section 15.6, required in every vector. A vector that tests an option off sets it here and never through `overrides`. For a vector that tests malformed settings the field may hold any JSON value (as `events` may), so it is not constrained by the schema beyond being present; for a vector with a `result`, it must be a valid settings object equal to `expected.result.settings` |
| `events` | array | The event log of section 15.1. For a vector that tests a malformed log, the array may hold any JSON values, so `events` is not constrained by the schema beyond being an array |
| `expected` | object | Exactly one of `{"result": <play result of 14.5>}` or `{"rejection": <rejection of 15.5>}` |

Rules for the runners (both languages): `config` must equal the canonical configuration with `overrides` applied, key by key, otherwise the test fails (10.6); the scoring is run with `config` and `settings`; the whole result (every field, every word, every line) or the whole rejection (`reason` and `event_index`) is compared with `expected`; a file that does not match the schema, has an unknown or missing field, or has a `name` different from its file name fails; the number of vectors executed must equal the number of files. The lyric text of vectors is synthetic, written for the project. The vectors cover each combination of the two options (at least accent off, case off and both off, with a song of accented words whose points and maximum base score stay those of the song normalization) and a `MALFORMED_PLAY_SETTINGS` rejection (10.5). Two rejection paths cannot be written as golden vectors, because the vector format requires `events` to be an array and `settings` to be present: an event log that is not an array (`event_index` null) and a missing settings value; each language covers them with unit tests of its own scoring entry point, not with vectors (every other malformed settings value, such as `null`, an object with a missing, extra or non-boolean field, is expressible and has vectors). They also cover the lower-of rule (section 4) with a **pair of vectors** on the same timeline and event log with `áéíb` expected and `áéíc` typed: one with both options on and one with the accent option off, whose expected results are identical in accuracy (3/4) and points (30). Besides the vectors, **both runners check a property** over every vector with a `result` whose options are not both on: the same timeline and event log are also scored with both options on (that result is computed, not stored), and no word of the vector's own result may have more accuracy (the ratio, compared by cross-multiplication, not the numerator or the pair) or more points, and the play may not have a larger score, than in the both-on result.

Both suites feed the same vector: the Python one with `score_play`, the Dart one both event by event through the engine and through `replay`.

## 18. Decisions taken in this document

Where the requirements leave room, this document takes the most defensible reading below; none changes a stated acceptance criterion.

- **D1 - Case handling (5.1, 6.1, 6.10, A5, A32).** When the case option of the play is on, case is ignored by lowercase with the simple lowercase mapping, code point by code point, instead of case folding, because Dart cannot reproduce full case folding. Consequence: `ß` does not equal `ss`, dotless `ı` does not equal `i`, `ς` does not equal `σ` (section 3.2). When the case option is off, the lowercase step is skipped and nothing replaces it (exact case everywhere, including the first letter of each lyric line, Round 2 question 3), so D1 does not apply at all.
- **D2 - NFD when the accent option is off (6.1, 6.2, A5).** NFD is applied in both modes and marks are removed only when the accent option is on, so with it off `canción` has 8 code points and differs from `cancion` by one edit, as 6.2 requires. The alternative (NFC with the option off) was rejected because it needs a composition table in Dart.
- **D3 - Pinned Unicode data and Dart tables (5.1, 9.3, non-functional Determinism).** Unicode 16.0.0 is the reference and the Dart side uses generated tables (section 3.3); the Python suite asserts its `unicodedata` version. This forces a rule-book change when Python moves to a newer Unicode.
- **D4 - Line bonus threshold (7.5, 7.9, 5.2).** 5.2 lists one "combo accuracy threshold 0.8"; 7.9 uses 0.8 for the bonus too, so one key `combo_accuracy_pct` serves both.
- **D5 - Constants beyond 5.2 (5.2, A11, A12, 5.7).** Keys added so that no number is hidden in the rules: `combo_base_pct`, `expected_time_pct`, `max_line_window_ms`, `last_line_window_ms`, `max_typed_chars`, and `tier_ok_limit_ms` kept apart from `miss_window_ms`.
- **D6 - Line end cap (A11, 5.7).** "Capped at 6 seconds of instrumental gap" is read as: the line window never exceeds 6000 ms, `end = min(next start, start + 6000)`.
- **D7 - Accuracy of MISS words and totals (A9, 8.3).** A MISS by expiry, skip or never reached has accuracy `0/1` and counts 0 in the average; a MISS by low accuracy (or a too-late commit) keeps its selected accuracy pair (the lower of the play pair and the song pair, section 4) in the word result and in the average (A9 names only the expiry case).
- **D8 - Exact average with arbitrary precision (A9, 5.4).** The average accuracy is an exact rational rounded once to basis points; the sum of fractions with different denominators needs arbitrary precision integers (Python `int`, Dart `BigInt`, no package). A cheaper alternative, rounding each word to basis points first, would change values by a few bp and was not chosen because A9 says "average".
- **D9 - Global word index counts non-scorable words (9.1, 9.6).** The `word` of a commit is the position in the timeline words, including words that are not scorable; a commit to one of those is `INCONSISTENT_WORD_INDEX`, not malformed.
- **D10 - Seek semantics (9.7, 14.5, 14.7).** Expiries are applied at `max(from, t)`; "skipped words" are the words expired by the catch-up rule at the destination; `from` must not be before the previous event time (`NON_MONOTONIC_TIME` otherwise). A seek to a nearby position (`t` near `from`) is still a seek and sets `seeked`.
- **D11 - Pause and resume are not validated (A10).** Double pauses, a resume without pause, and commits between a pause and a resume are accepted; checking them is a plausibility check of spec 002.
- **D12 - Strictness of the log format (9.6).** Extra fields are malformed; an empty `text` is malformed (the game never records one, 6.9); `text` longer than 64 code points is malformed (A12); integers outside 0 to 2^53 - 1 are malformed (portability to Dart on the web).
- **D13 - Order of the checks (9.4, 9.5, 9.6, 9.8, 9.12).** The play settings first (`MALFORMED_PLAY_SETTINGS`, no event index); then the structure of the whole log; then, event by event, time before consistency; the first failure is reported.
- **D14 - End of the log (8.3, 6.6).** Instead of expiring at an end time that the log does not contain, every word without a result at the end of the log is a MISS.
- **D15 - Result fields beyond 8.1 (8.1, 8.2).** `scorable_words`, `hit_words` and `max_base_score` are added to the result so that rates and rank are checkable; per-line `points` excludes the bonus. The play settings used are a field of the result, `settings` (8.1, Amendment 1).
- **D16 - Typed text with only ignorable characters (6.9).** It is a real commit with accuracy `0/L`, not an empty commit.
- **D17 - Two normalizations (6.10, 6.11, 7.4, 8.2, A5, Round 2 question 1).** The comparison normalization follows the play settings and is used for `e`, `t`, `d` and the accuracy length `L`. The song normalization (accents removed and lowercase, always) is used for scorability, expected times, `Lexp` and the maximum base score, so one timeline serves every play and no option changes the base points of a song. The accuracy is the lower of the ratio under the play settings and the ratio under the song normalization, compared exactly by cross-multiplication; equal ratios report the song pair (owner decision of 2026-11-19, option (a), follow-up of 6.11 and A5). The points formula is `round_half_up(10 x Lexp x (L - d) x tier_pct x combo_pct / (L x 100 x 100))` with `L - d` and `L` of the selected pair, still one integer expression with one half-up rounding. Without the lower-of rule, turning the accent option off could raise the accuracy of a word whose typed text shares every mark with the expected word and differs elsewhere (`áéíb`/`áéíc`: 6/7 against 3/4, section 8), because `L` grows with the kept marks; the rule removes that. Property: for the same timeline and event log, no option can raise a word's accuracy or points or the score of the play above the both-on play (sections 4 and 8).
- **D18 - Play settings are a separate input (9.11, 9.12, A32).** The settings object `{"accent_insensitive", "case_insensitive"}` travels next to the event log, not inside it, so the event log format is unchanged; it is copied into the result and into every vector; invalid settings are the new rejection `MALFORMED_PLAY_SETTINGS` with a null index, decided first.
- **D20 - Rank with no scorable word, and configuration bounds (8.2, 8.4).** The special case is part of the rank rule: if `n = 0` the rank is D and the comparisons are not evaluated. `base_points_per_char >= 1` is required so that `max_base_score >= 1` whenever `n >= 1`, and section 2 gives upper bounds for the configuration values so that the magnitude statement of section 1.6 holds for every valid configuration, not only the canonical one.
- **D21 - Precondition of live/replay equality (9.3, 8.5).** The game keeps the playhead given to the engine non-decreasing except through a seek and records every event time as the engine's current playhead, never below the last `advanceTo` value; a seek is recorded before any `advanceTo` with its destination (section 11).
- **D22 - Validity on decoded values (9.6, 9.11).** Integer validity is defined on the decoded value (Python `type(x) is int`, bool excluded; Dart VM `x is int`); `-0` decodes to 0 and is accepted, vectors never contain it; `NaN`, `Infinity` and duplicate keys are invalid JSON (a test-file error in vectors; on the server, spec 002, `MALFORMED_EVENT_LOG` at the decoding layer); the canonical Python decoder settings are in section 1.5. The rejection paths "log is not an array" and "settings missing" are covered by unit tests in each language, not by vectors (section 17).
- **D19 - Default flags (5.2).** The former configuration key `accent_insensitive` is replaced by `default_accent_insensitive` and `default_case_insensitive` (both true): they are the initial state of the game screen toggles and are never read by the scoring, so a vector cannot override them.

## 19. Traceability: criterion to section

| Criterion | Rule in | Example in |
|---|---|---|
| 5.1 (contents of the document, incl. play settings format and their rejection) | sections 3 to 17 | whole document |
| 5.2 (constants table, default flags of the two options) | 2 | 2 |
| 5.3 (boundaries) | 1.3, 5.4, 7, 8 step 2, 9, 11, 14.4 | 4, 5, 7, 9, 11, 14.6 |
| 5.4 (order of operations, rounding) | 1.2, 6.2, 8, 14.3 | 6.3, 8, 14.6 |
| 5.5 (worked example per rule) | every section | every section |
| 5.6 (one pull request for a change) | header and 1 | n/a |
| 5.7 (expected time) | 6 | 6.3 |
| 6.1, 6.2 (comparison normalization, play settings, accent option) | 3.2, 4, 15.6 | 3.4, 4 |
| A5 (accuracy: longer length; lower of the play pair and the song pair) | 4, 8, D17 | 4, 8 |
| 6.3 (accuracy) | 4 | 4 |
| 6.4 (MISS below 0.6) | 8 step 2 | 4, 8 |
| 6.5 (commits apply to the current word) | 5.1, 5.2, 15.4 | 15.4 |
| 6.6 (catch-up) | 11 | 11, 13 |
| 6.7 (lead-in) | 5.4 | 5 |
| 6.8 (non-scorable words) | 1.9, 5.3, 6.2 | 3.4, 6.3 |
| 6.9 (empty commit) | 5.2, 15.2 | 5 |
| 6.10 (case option off skips the lowercase step) | 3.2 step 3, D1 | 3.4, 4, 8 |
| 6.11 (song normalization for scorability, times, lengths, max base score; accuracy is the lower of the play ratio and the song ratio; no option raises accuracy, points or score) | 3.2, 4, 6.2, 8, 14.2 | 4, 6.3, 8, D17 |
| 7.1 (tiers) | 7 | 7 |
| 7.2 (EARLY) | 7 | 7, 14.6 |
| 7.3 (late MISS) | 7, 8 step 3 | 7 |
| 7.4 (points, `Lexp` under the song normalization) | 8 | 8 |
| 7.5 (combo increase) | 9 | 9 |
| 7.6 (combo reset) | 9 | 9, 12 |
| 7.7 (combo neutral) | 9 | 9 |
| 7.8 (combo multiplier) | 9 | 9 |
| 7.9 (line bonus) | 10 | 10, 14.6 |
| 7.10 (no points for watching) | 5.6, 12 | 13 |
| 8.1 (result fields, incl. `settings`) | 14.1 to 14.5 | 14.6 |
| 8.2 (rank) | 14.4 | 14.6 |
| 8.3 (unreached words are MISS) | 13 step 4, 14.1 | 14.6 |
| 8.4 (no scorable word, rank D by the special rule) | 14.4 | 14.4 (outcome), 13 (empty log) |
| 8.5 (determinism, settings are part of the input) | 1.8, 11 (D21) | 14.6 (one input, one result) |
| 9.1 (event log) | 15.1 | 15.1 |
| 9.2 (complete result from timeline, play settings, log, configuration) | 13, 14 | 14.6 |
| 9.3 (parity) | 3.3, 11 (D21), 17 | n/a (proved by the golden vectors of 17) |
| 9.4 (inconsistent index) | 15.4 | 15.4 |
| 9.5 (non-monotonic time) | 15.3 | 15.3 |
| 9.6 (malformed log) | 1.5, 15.2 | 13 (malformed log) |
| 9.7 (seek) | 12 | 12 (forward and backward) |
| 9.8 (rejection with index, no score) | 15.5 | 15.5 |
| 9.9 (no handler, network, AWS) | implementation rule, outside the rules | n/a |
| 9.10 (word-time rule in Python only) | 6 | 6.3 |
| 9.11 (play settings next to the log, only source of the options) | 13 step 0, 15, 15.6 | 15.6, 8 |
| 9.12 (`MALFORMED_PLAY_SETTINGS`, null index, checked first) | 13 step 0, 15.5, 15.6, D13 | 15.6 |
| 10.1 (vector fields incl. `settings`) | 17 | 17 |
| 10.2, 10.3 (both suites run every vector and compare every field) | 17 (runner rules) | n/a (test rule) |
| 10.4 (parity failure or different vector counts fail the CI) | 17 (runner rules) | n/a (CI rule) |
| 10.6 (configuration equals the vectors' values) | 17 (`config`, `overrides`) | n/a (test rule) |
| 10.7 (synthetic lyrics) | 17 | n/a (every example is synthetic) |
| 10.5 (vectors for each option combination and the settings rejection) | 17 | 17 |
| 18.3 (options fixed at the start and recorded as play settings) | 13 step 0, 15.6 | 15.6 |
| 18.4 (scoring, replay and export use the fixed settings) | 13, 14.5, 15.6 | 13, 14.6 |
| 18.5 (results carry the options used) | 14.5 | 14.6 |

Criteria 18.1, 18.2 and 18.6 (the toggles, when they can be changed, nothing stored) belong to the game screen and are not scoring rules; the toggle defaults are the constants of section 2.

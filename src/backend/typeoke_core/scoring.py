"""Text handling, word accuracy, tiers, points, combo and line bonus of ``docs/scoring.md``.

Sections 3, 4 and 7 to 14. The replay of section 13 is a step function over events.

Pure functions on integers and strings: no clock, no randomness, no locale, no I/O. Unicode
properties are those of Unicode 16.0.0 (section 1.7), which the test suite asserts.
"""

import math
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field

from typeoke_core.config import DEFAULT_CONFIG, ScoringConfig
from typeoke_core.models import (
    Accuracy,
    Commit,
    Event,
    LineResult,
    PlayResult,
    PlaySettings,
    Rank,
    Rejection,
    RejectionReason,
    Seek,
    Tier,
    Timeline,
    WordResult,
    parse_event_log,
    parse_play_settings,
)

# Section 3.1: not the whitespace of the standard library.
_WHITESPACE_CODES = (
    *range(0x09, 0x0E),
    0x20,
    0x85,
    0xA0,
    0x1680,
    *range(0x2000, 0x200B),
    0x2028,
    0x2029,
    0x202F,
    0x205F,
    0x3000,
)
_WHITESPACE_CHARS = frozenset(chr(code) for code in _WHITESPACE_CODES)

_SONG_SETTINGS = PlaySettings(accent_insensitive=True, case_insensitive=True)


def split_words(text: str) -> list[str]:
    """Cut a line text at every run of whitespace (section 3.1); no empty word is produced."""
    words: list[str] = []
    current: list[str] = []
    for char in text:
        if char in _WHITESPACE_CHARS:
            if current:
                words.append("".join(current))
                current = []
        else:
            current.append(char)
    if current:
        words.append("".join(current))
    return words


def _is_ignorable(category: str) -> bool:
    """Step 4 of section 3.2: P*, S*, Z*, Cc and Cf are removed."""
    return category[0] in "PSZ" or category in ("Cc", "Cf")


def normalize(text: str, settings: PlaySettings) -> str:
    """Comparison normalization of section 3.2, driven by the play settings.

    Order: NFD (always), marks Mn removed (accent option), simple lowercase one code point at
    a time (case option), then P*, S*, Z*, Cc and Cf removed (always).
    """
    kept: list[str] = []
    for char in unicodedata.normalize("NFD", text):
        if settings.accent_insensitive and unicodedata.category(char) == "Mn":
            continue
        if settings.case_insensitive:
            # A single code point never meets the final-sigma context rule. After NFD the only
            # code point whose lower() has two code points (U+0130) is no longer present.
            char = char.lower()
        if not _is_ignorable(unicodedata.category(char)):
            kept.append(char)
    return "".join(kept)


def song_normalize(text: str) -> str:
    """Song normalization: both options on, whatever the play settings are (section 3.2)."""
    return normalize(text, _SONG_SETTINGS)


def is_scorable(word: str) -> bool:
    """A word is scorable when its song-normalized text is not empty (section 1.9)."""
    return song_normalize(word) != ""


def levenshtein(left: str, right: str) -> int:
    """Edit distance over code points: insertion, deletion and substitution cost 1."""
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, start=1):
        current = [i]
        for j, b in enumerate(right, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (a != b)))
        previous = current
    return previous[-1]


def _candidate(expected: str, typed: str, settings: PlaySettings) -> Accuracy:
    """Candidate pair ``(L - d, L)`` under one normalization, not reduced (section 4)."""
    e = normalize(expected, settings)
    t = normalize(typed, settings)
    length = max(len(e), len(t))
    return Accuracy(length - levenshtein(e, t), length)


def word_accuracy(expected: str, typed: str, settings: PlaySettings) -> Accuracy:
    """Accuracy of a typed text: the lower of the play pair and the song pair (section 4).

    The ratios are compared by cross-multiplication. The play pair is selected only when it is
    strictly lower; in every other case the song pair is returned, so equal ratios with
    different denominators report the song pair. ``expected`` must be scorable.
    """
    play = _candidate(expected, typed, settings)
    song = _candidate(expected, typed, _SONG_SETTINGS)
    if play.num * song.den < song.num * play.den:
        return play
    return song


# ------------------------------------------------------------------------ rounding


def round_half_up(numerator: int, denominator: int) -> int:
    """``floor((2n + d) / (2d))`` for ``n >= 0`` and ``d > 0`` (section 1.2)."""
    return (2 * numerator + denominator) // (2 * denominator)


# --------------------------------------------------------------------------- tiers


def timing_tier(delta_ms: int, config: ScoringConfig = DEFAULT_CONFIG) -> Tier:
    """Tier of a commit by its delta, ``playhead - expected_ms`` (section 7).

    Every limit belongs to the better tier. Beyond the OK limit the sign decides: early is
    EARLY, late is MISS.
    """
    magnitude = abs(delta_ms)
    if magnitude <= config.tier_perfect_limit_ms:
        return Tier.PERFECT
    if magnitude <= config.tier_great_limit_ms:
        return Tier.GREAT
    if magnitude <= config.tier_good_limit_ms:
        return Tier.GOOD
    if magnitude <= config.tier_ok_limit_ms:
        return Tier.OK
    return Tier.EARLY if delta_ms < 0 else Tier.MISS


def tier_pct(tier: Tier, config: ScoringConfig = DEFAULT_CONFIG) -> int:
    """Timing multiplier of a tier as an integer percentage (MISS gives 0)."""
    return {
        Tier.PERFECT: config.tier_perfect_pct,
        Tier.GREAT: config.tier_great_pct,
        Tier.GOOD: config.tier_good_pct,
        Tier.OK: config.tier_ok_pct,
        Tier.EARLY: config.tier_early_pct,
        Tier.MISS: 0,
    }[tier]


def meets_accuracy_pct(accuracy: Accuracy, pct: int) -> bool:
    """Exact test ``num x 100 >= pct x den`` on the selected pair (section 4)."""
    return accuracy.num * 100 >= pct * accuracy.den


def commit_tier(delta_ms: int, accuracy: Accuracy, config: ScoringConfig = DEFAULT_CONFIG) -> Tier:
    """Tier of a commit (section 8, steps 2 and 3).

    An accuracy below ``min_accuracy_pct`` is a MISS whatever the timing is; otherwise the
    tier comes from the delta (and may still be MISS when the commit is too late).
    """
    if not meets_accuracy_pct(accuracy, config.min_accuracy_pct):
        return Tier.MISS
    return timing_tier(delta_ms, config)


# --------------------------------------------------------------------------- combo


def combo_multiplier_pct(combo: int, config: ScoringConfig = DEFAULT_CONFIG) -> int:
    """Combo multiplier for the combo count before the word (section 9, A7)."""
    steps = combo // config.combo_step_words
    return min(config.combo_cap_pct, config.combo_base_pct + steps * config.combo_step_pct)


def next_combo(
    combo: int, tier: Tier, accuracy: Accuracy, config: ScoringConfig = DEFAULT_CONFIG
) -> int:
    """Combo after a commit (section 9): MISS resets, a clean fast word adds one, else unchanged."""
    if tier is Tier.MISS:
        return 0
    if tier in (Tier.PERFECT, Tier.GREAT, Tier.GOOD) and meets_accuracy_pct(
        accuracy, config.combo_accuracy_pct
    ):
        return combo + 1
    return combo


# --------------------------------------------------------------------------- points


def word_points(
    expected_length: int,
    accuracy: Accuracy,
    tier: Tier,
    combo: int,
    config: ScoringConfig = DEFAULT_CONFIG,
) -> int:
    """Points of a scored word, one rounding half up (section 8).

    ``expected_length`` is ``Lexp``, the length of the expected word under the song
    normalization; ``accuracy`` is the selected pair ``(L - d, L)``; ``combo`` is the combo
    before the word. A MISS gives 0.
    """
    numerator = (
        config.base_points_per_char
        * expected_length
        * accuracy.num
        * tier_pct(tier, config)
        * combo_multiplier_pct(combo, config)
    )
    return round_half_up(numerator, accuracy.den * 100 * 100)


# ----------------------------------------------------------------------- line bonus


def line_bonus(results: Sequence[WordResult], config: ScoringConfig = DEFAULT_CONFIG) -> int:
    """Bonus of a line whose scorable words all have a result (section 10).

    Given when there is at least one word and every one is not a MISS and meets
    ``combo_accuracy_pct``; the bonus is never multiplied. Tier does not matter otherwise.
    """
    if results and all(
        result.tier is not Tier.MISS
        and meets_accuracy_pct(result.accuracy, config.combo_accuracy_pct)
        for result in results
    ):
        return config.line_bonus
    return 0


# ------------------------------------------------------------------------- replay


@dataclass(frozen=True, slots=True)
class _PlanWord:
    """A scorable word of the timeline with the values the replay needs."""

    index: int
    line: int
    text: str
    expected_ms: int
    line_start_ms: int
    base_length: int


@dataclass(slots=True)
class ReplayState:
    """State of a replay between two events (section 13, step 2).

    Scorable words are resolved strictly in order, so the current word is
    ``plan[len(results)]``. Created by ``start_replay``; changed only by ``advance_to`` and
    ``step``; read by ``finish``.
    """

    settings: PlaySettings
    config: ScoringConfig
    plan: tuple[_PlanWord, ...]
    line_ranges: tuple[range, ...]
    results: list[WordResult] = field(default_factory=list)
    bonuses: dict[int, int] = field(default_factory=dict)
    combo: int = 0
    max_combo: int = 0
    seeked: bool = False
    previous_time: int | None = None


def start_replay(
    timeline: Timeline, settings: PlaySettings, config: ScoringConfig = DEFAULT_CONFIG
) -> ReplayState:
    """Initial state of a replay. A scorable word without an expected time is a caller error."""
    plan: list[_PlanWord] = []
    line_ranges: list[range] = []
    index = 0
    for line_index, line in enumerate(timeline.lines):
        first = len(plan)
        for word in line.words:
            base_length = len(song_normalize(word.text))
            if base_length > 0:
                if word.expected_ms is None:
                    raise ValueError(f"scorable word {index} has no expected time")
                plan.append(
                    _PlanWord(
                        index, line_index, word.text, word.expected_ms, line.start_ms, base_length
                    )
                )
            index += 1
        line_ranges.append(range(first, len(plan)))
    return ReplayState(settings, config, tuple(plan), tuple(line_ranges))


def _resolve(state: ReplayState, result: WordResult, combo: int) -> None:
    """Record the result of the current word, set the combo and decide the line bonus."""
    position = len(state.results)
    line = state.plan[position].line
    state.results.append(result)
    state.combo = combo
    state.max_combo = max(state.max_combo, combo)
    line_range = state.line_ranges[line]
    if position == line_range[-1]:
        state.bonuses[line] = line_bonus(state.results[line_range.start :], state.config)


def _resolve_miss(state: ReplayState) -> None:
    """The current word becomes a MISS with accuracy (0, 1) and 0 points (sections 11, 14.1)."""
    word = state.plan[len(state.results)]
    _resolve(state, WordResult(word.index, Tier.MISS, Accuracy(0, 1), 0), 0)


def advance_to(state: ReplayState, time_ms: int) -> None:
    """Expire, in word order, every current word more than ``miss_window_ms`` late (section 11)."""
    plan = state.plan
    while (
        len(state.results) < len(plan)
        and time_ms - plan[len(state.results)].expected_ms > state.config.miss_window_ms
    ):
        _resolve_miss(state)


def _apply_commit(state: ReplayState, commit: Commit) -> RejectionReason | None:
    position = len(state.results)
    if position == len(state.plan):
        return RejectionReason.INCONSISTENT_WORD_INDEX
    word = state.plan[position]
    locked = commit.t < word.line_start_ms - state.config.lead_in_ms
    if commit.word != word.index or locked:
        return RejectionReason.INCONSISTENT_WORD_INDEX
    accuracy = word_accuracy(word.text, commit.text, state.settings)
    tier = commit_tier(commit.t - word.expected_ms, accuracy, state.config)
    points = word_points(word.base_length, accuracy, tier, state.combo, state.config)
    combo = next_combo(state.combo, tier, accuracy, state.config)
    _resolve(state, WordResult(word.index, tier, accuracy, points), combo)
    return None


def step(state: ReplayState, event: Event) -> RejectionReason | None:
    """Apply one event (section 13, step 3); a reason means the play is rejected at this event.

    Time check first (``NON_MONOTONIC_TIME``), then the expiries at the time of the event (at
    ``max(from, t)`` for a seek), then the event itself. After a rejection the state must not
    be used again.
    """
    origin = event.from_ms if isinstance(event, Seek) else event.t
    if state.previous_time is not None and origin < state.previous_time:
        return RejectionReason.NON_MONOTONIC_TIME
    state.previous_time = event.t
    advance_to(state, max(origin, event.t))
    if isinstance(event, Commit):
        return _apply_commit(state, event)
    if isinstance(event, Seek):
        state.seeked = True
    return None


def rank_for(
    score: int, max_base_score: int, scorable_words: int, config: ScoringConfig = DEFAULT_CONFIG
) -> Rank:
    """Rank by integer comparison with the maximum base score (section 14.4, D20)."""
    if scorable_words == 0:
        return Rank.D
    for rank, pct in (
        (Rank.S, config.rank_s_pct),
        (Rank.A, config.rank_a_pct),
        (Rank.B, config.rank_b_pct),
        (Rank.C, config.rank_c_pct),
    ):
        if score * 100 >= pct * max_base_score:
            return rank
    return Rank.D


def _accuracy_bp(results: Sequence[WordResult]) -> int:
    """Average accuracy in basis points from the exact sum of the ratios (section 14.3)."""
    if not results:
        return 0
    numerator, denominator = 0, 1
    for result in results:
        den = result.accuracy.den
        numerator = numerator * den + result.accuracy.num * denominator
        denominator *= den
        divisor = math.gcd(numerator, denominator)
        numerator //= divisor
        denominator //= divisor
    return round_half_up(10000 * numerator, denominator * len(results))


def _line_result(state: ReplayState, line: int, line_range: range) -> LineResult:
    words = tuple(state.results[line_range.start : line_range.stop])
    return LineResult(line, sum(w.points for w in words), state.bonuses.get(line, 0), words)


def finish(state: ReplayState) -> PlayResult:
    """End of the log: every unresolved scorable word is a MISS, then the result (section 14)."""
    while len(state.results) < len(state.plan):
        _resolve_miss(state)
    results = state.results
    count = len(results)
    max_base_score = state.config.base_points_per_char * sum(w.base_length for w in state.plan)
    lines = tuple(
        _line_result(state, line, line_range) for line, line_range in enumerate(state.line_ranges)
    )
    score = sum(line.points + line.bonus for line in lines)
    hit_words = sum(1 for result in results if result.tier is not Tier.MISS)
    return PlayResult(
        settings=state.settings,
        score=score,
        accuracy_bp=_accuracy_bp(results),
        hit_rate_bp=round_half_up(10000 * hit_words, count) if count else 0,
        max_combo=state.max_combo,
        rank=rank_for(score, max_base_score, count, state.config),
        seeked=state.seeked,
        scorable_words=count,
        hit_words=hit_words,
        max_base_score=max_base_score,
        lines=lines,
    )


def score_play(
    timeline: Timeline,
    settings: object,
    events: object,
    config: ScoringConfig = DEFAULT_CONFIG,
) -> PlayResult | Rejection:
    """Judge a play from its timeline, play settings and event log (section 13).

    ``settings`` and ``events`` are raw decoded JSON values (a ``dict`` and a ``list``); they
    are validated here: settings first, then the whole log, then event by event. ``timeline``
    and ``config`` are trusted caller values. Returns the result or the first rejection.
    """
    parsed_settings = parse_play_settings(settings)
    if isinstance(parsed_settings, Rejection):
        return parsed_settings
    parsed_events = parse_event_log(events, timeline.word_count, config)
    if isinstance(parsed_events, Rejection):
        return parsed_events
    state = start_replay(timeline, parsed_settings, config)
    for index, event in enumerate(parsed_events):
        reason = step(state, event)
        if reason is not None:
            return Rejection(reason, index)
    return finish(state)

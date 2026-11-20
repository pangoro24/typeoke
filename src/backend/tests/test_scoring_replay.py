"""Tests of the replay engine, play result and rejections (sections 11 to 15 of docs/scoring.md)."""

import random
import time
import unicodedata
from dataclasses import replace

import pytest

from typeoke_core.config import DEFAULT_CONFIG
from typeoke_core.models import (
    Accuracy,
    Commit,
    Line,
    PlayResult,
    PlaySettings,
    Rank,
    Rejection,
    RejectionReason,
    Tier,
    Timeline,
    Word,
    result_from_json,
)
from typeoke_core.scoring import (
    advance_to,
    finish,
    rank_for,
    score_play,
    start_replay,
    step,
)
from typeoke_core.timeline import SourceLine, build_timeline

BOTH_ON = {"accent_insensitive": True, "case_insensitive": True}
Json = dict[str, object]


def _running() -> Timeline:
    """The timeline of section 6.3: words 0-2 on line 0, 3-4 on line 1, 5-7 on line 2."""
    return build_timeline(
        [
            SourceLine(10000, "Hello, bright moon"),
            SourceLine(20000, "Sky up"),
            SourceLine(24025, "La la la"),
        ]
    )


def _commit(t: int, word: int, text: str) -> Json:
    return {"type": "commit", "t": t, "word": word, "text": text}


def _pause(t: int) -> Json:
    return {"type": "pause", "t": t}


def _resume(t: int) -> Json:
    return {"type": "resume", "t": t}


def _seek(t: int, origin: int) -> Json:
    return {"type": "seek", "t": t, "from": origin}


def _play(
    events: list[Json],
    timeline: Timeline | None = None,
    settings: object = BOTH_ON,
) -> PlayResult:
    result = score_play(timeline or _running(), settings, events)
    assert isinstance(result, PlayResult)
    return result


def _rejection(
    events: object, timeline: Timeline | None = None, settings: object = BOTH_ON
) -> Rejection:
    result = score_play(timeline or _running(), settings, events)
    assert isinstance(result, Rejection)
    return result


def _word(result: PlayResult, index: int) -> tuple[Tier, Accuracy, int]:
    for line in result.lines:
        for word in line.words:
            if word.word == index:
                return word.tier, word.accuracy, word.points
    raise AssertionError(f"word {index} has no result")


# ------------------------------------------------------------------ worked examples


def test_whole_play_of_section_14_6() -> None:
    events = [
        _commit(11300, 0, "Hello"),
        _commit(14660, 1, "brigth"),
        _commit(18900, 2, "moon"),
        _commit(19000, 3, "SKY!"),
        _commit(20122, 4, "up"),
        _commit(25525, 5, "la"),
    ]
    expected = result_from_json(
        {
            "settings": BOTH_ON,
            "score": 175,
            "accuracy_bp": 7083,
            "hit_rate_bp": 7500,
            "max_combo": 2,
            "rank": "B",
            "seeked": False,
            "scorable_words": 8,
            "hit_words": 6,
            "max_base_score": 260,
            "lines": [
                {
                    "line": 0,
                    "points": 94,
                    "bonus": 0,
                    "words": [
                        {
                            "word": 0,
                            "tier": "PERFECT",
                            "accuracy": {"num": 5, "den": 5},
                            "points": 50,
                        },
                        {
                            "word": 1,
                            "tier": "GREAT",
                            "accuracy": {"num": 4, "den": 6},
                            "points": 32,
                        },
                        {"word": 2, "tier": "OK", "accuracy": {"num": 4, "den": 4}, "points": 12},
                    ],
                },
                {
                    "line": 1,
                    "points": 11,
                    "bonus": 50,
                    "words": [
                        {"word": 3, "tier": "OK", "accuracy": {"num": 3, "den": 3}, "points": 9},
                        {"word": 4, "tier": "EARLY", "accuracy": {"num": 2, "den": 2}, "points": 2},
                    ],
                },
                {
                    "line": 2,
                    "points": 20,
                    "bonus": 0,
                    "words": [
                        {
                            "word": 5,
                            "tier": "PERFECT",
                            "accuracy": {"num": 2, "den": 2},
                            "points": 20,
                        },
                        {"word": 6, "tier": "MISS", "accuracy": {"num": 0, "den": 1}, "points": 0},
                        {"word": 7, "tier": "MISS", "accuracy": {"num": 0, "den": 1}, "points": 0},
                    ],
                },
            ],
        }
    )
    assert _play(events) == expected


def test_pause_resume_and_expiry_example_scores_59() -> None:
    events = [
        _commit(11800, 0, "hello"),
        _pause(14000),
        _resume(14000),
        _commit(19000, 3, "sky"),
    ]
    result = _play(events)
    assert result.score == 59
    assert result.max_combo == 1
    assert _word(result, 1)[0] is Tier.MISS
    assert _word(result, 2)[0] is Tier.MISS
    assert _word(result, 3) == (Tier.OK, Accuracy(3, 3), 9)
    assert [_word(result, i)[0] for i in (4, 5, 6, 7)] == [Tier.MISS] * 4


def test_pause_and_resume_have_no_effect() -> None:
    plain = _play([_commit(11800, 0, "hello"), _commit(19000, 3, "sky")])
    paused = _play(
        [
            _commit(11800, 0, "hello"),
            _pause(12000),
            _pause(12000),
            _resume(18000),
            _commit(19000, 3, "sky"),
        ]
    )
    assert paused == plain


def test_expiries_across_a_line_boundary_deny_the_bonus() -> None:
    result = _play([_commit(22174, 3, "sky"), _commit(28000, 5, "la")])
    assert _word(result, 3) == (Tier.PERFECT, Accuracy(3, 3), 30)
    assert _word(result, 4)[0] is Tier.MISS
    assert _word(result, 5) == (Tier.OK, Accuracy(2, 2), 6)
    assert [line.bonus for line in result.lines] == [0, 0, 0]
    assert result.score == 36
    assert result.max_combo == 1


def test_forward_seek_skips_words_as_miss() -> None:
    events = [_commit(11800, 0, "Hello"), _seek(26000, 12000), _commit(26100, 4, "up")]
    result = _play(events)
    assert [_word(result, i)[0] for i in (1, 2, 3)] == [Tier.MISS] * 3
    assert _word(result, 4) == (Tier.OK, Accuracy(2, 2), 6)
    assert result.lines[1].bonus == 0
    assert result.seeked is True
    assert result.score == 50 + 6
    assert result.max_combo == 1


def test_backward_seek_keeps_results_and_word_stays_locked() -> None:
    for t in (5000, 8499):
        rejection = _rejection(
            [_commit(11300, 0, "Hello"), _seek(5000, 12000), _commit(t, 1, "bright")]
        )
        assert rejection == Rejection(RejectionReason.INCONSISTENT_WORD_INDEX, 2)


def test_backward_seek_commit_at_lead_in_is_accepted_as_early() -> None:
    result = _play([_commit(11300, 0, "Hello"), _seek(5000, 12000), _commit(8500, 1, "bright")])
    assert _word(result, 0) == (Tier.PERFECT, Accuracy(5, 5), 50)
    assert _word(result, 1) == (Tier.EARLY, Accuracy(6, 6), 6)
    assert result.max_combo == 1
    assert result.seeked is True


def test_malformed_log_reports_the_first_malformed_index() -> None:
    bad = {"type": "pause", "t": 14000.5}
    assert _rejection([_commit(11300, 0, "Hello"), bad]) == Rejection(
        RejectionReason.MALFORMED_EVENT_LOG, 1
    )
    assert _rejection([_commit(11300, 7, "x"), bad]) == Rejection(
        RejectionReason.MALFORMED_EVENT_LOG, 1
    )


def test_word_outside_the_song_is_malformed_not_inconsistent() -> None:
    assert _rejection([_commit(11300, 8, "x")]) == Rejection(RejectionReason.MALFORMED_EVENT_LOG, 0)


def test_commit_to_a_word_that_is_not_scorable_is_inconsistent() -> None:
    timeline = build_timeline([SourceLine(40000, "Oh — yes"), SourceLine(44000, "Next")])
    assert [w.expected_ms for w in timeline.lines[0].words] == [41440, None, 43600]
    events = [_commit(41440, 0, "oh"), _commit(42000, 1, "x")]
    assert _rejection(events, timeline) == Rejection(RejectionReason.INCONSISTENT_WORD_INDEX, 1)
    ok = _play([_commit(41440, 0, "oh"), _commit(43600, 2, "yes")], timeline)
    assert ok.lines[0].bonus == 50
    assert [w.word for w in ok.lines[0].words] == [0, 2]


def test_empty_log_scores_zero_with_rank_d() -> None:
    result = _play([])
    assert (result.score, result.max_combo, result.hit_words, result.scorable_words) == (0, 0, 0, 8)
    assert (result.accuracy_bp, result.hit_rate_bp, result.max_base_score) == (0, 0, 260)
    assert result.rank is Rank.D
    assert result.seeked is False
    assert all(line.points == 0 and line.bonus == 0 for line in result.lines)
    assert all(
        word.tier is Tier.MISS and word.accuracy == Accuracy(0, 1)
        for line in result.lines
        for word in line.words
    )


def test_song_without_scorable_word_scores_zero_rank_d() -> None:
    timeline = build_timeline([SourceLine(1000, "—"), SourceLine(2000, "")])
    result = _play([_seek(500, 100)], timeline)
    assert result.scorable_words == 0
    assert (result.score, result.accuracy_bp, result.hit_rate_bp, result.max_base_score) == (
        0,
        0,
        0,
        0,
    )
    assert result.rank is Rank.D
    assert result.seeked is True
    assert [(line.points, line.bonus, line.words) for line in result.lines] == [(0, 0, ())] * 2
    assert result.settings == PlaySettings(True, True)
    assert _rejection([_commit(1000, 0, "x")], timeline) == Rejection(
        RejectionReason.INCONSISTENT_WORD_INDEX, 0
    )
    assert score_play(Timeline(()), BOTH_ON, []) == replace(result, seeked=False, lines=())


# ------------------------------------------------------------------- order of checks


@pytest.mark.parametrize(
    "settings",
    [
        None,
        [],
        "x",
        1,
        True,
        {},
        {"accent_insensitive": True},
        {"accent_insensitive": True, "case_insensitive": 1},
        {"accent_insensitive": True, "case_insensitive": True, "locale": "es"},
    ],
)
def test_malformed_settings_win_over_everything_and_have_no_index(settings: object) -> None:
    malformed_log = [{"type": "nope"}]
    assert _rejection(malformed_log, settings=settings) == Rejection(
        RejectionReason.MALFORMED_PLAY_SETTINGS, None
    )


@pytest.mark.parametrize("events", [None, {}, "x", 3])
def test_log_that_is_not_an_array_has_no_index(events: object) -> None:
    assert _rejection(events) == Rejection(RejectionReason.MALFORMED_EVENT_LOG, None)


def test_non_monotonic_commit_pause_resume_and_seek() -> None:
    first = _commit(12000, 0, "hello")
    expected = Rejection(RejectionReason.NON_MONOTONIC_TIME, 1)
    assert _rejection([first, _pause(11999)]) == expected
    assert _rejection([first, _resume(11999)]) == expected
    assert _rejection([first, _commit(11999, 1, "bright")]) == expected
    assert _rejection([first, _seek(5000, 11999)]) == expected


def test_time_check_comes_before_the_consistency_check() -> None:
    assert _rejection([_commit(12000, 0, "hello"), _commit(11000, 7, "x")]) == Rejection(
        RejectionReason.NON_MONOTONIC_TIME, 1
    )


def test_equal_times_and_seek_destination_below_are_accepted() -> None:
    result = _play(
        [
            _commit(12000, 0, "hello"),
            _pause(12000),
            _seek(5000, 12000),
            _seek(5000, 5000),
            _resume(5000),
        ]
    )
    assert result.seeked is True


def test_seek_without_a_following_commit_passes_the_time_check() -> None:
    rejection = _rejection([_commit(12000, 0, "hello"), _seek(5000, 12000), _commit(5000, 1, "x")])
    assert rejection == Rejection(RejectionReason.INCONSISTENT_WORD_INDEX, 2)


# ------------------------------------------------------------- commits and expiries


def test_commit_is_applied_to_the_current_word_only() -> None:
    assert _rejection([_commit(11800, 1, "bright")]) == Rejection(
        RejectionReason.INCONSISTENT_WORD_INDEX, 0
    )
    assert _rejection([_commit(11800, 0, "hello"), _commit(12000, 0, "hello")]) == Rejection(
        RejectionReason.INCONSISTENT_WORD_INDEX, 1
    )


def test_lead_in_limit_is_inclusive() -> None:
    assert _rejection([_commit(8499, 0, "hello")]) == Rejection(
        RejectionReason.INCONSISTENT_WORD_INDEX, 0
    )
    result = _play([_commit(8500, 0, "hello")])
    assert _word(result, 0)[0] is Tier.OK


def test_word_is_open_at_3500_late_and_expired_at_3501() -> None:
    prefix = _commit(11800, 0, "hello")
    result = _play([prefix, _commit(17460, 1, "bright")])
    assert _word(result, 1) == (Tier.OK, Accuracy(6, 6), 18)
    assert _rejection([prefix, _commit(17461, 1, "bright")]) == Rejection(
        RejectionReason.INCONSISTENT_WORD_INDEX, 1
    )


def test_commit_after_catch_up_must_name_the_new_current_word() -> None:
    prefix = _commit(11800, 0, "hello")
    assert _rejection([prefix, _commit(19000, 2, "moon")]) == Rejection(
        RejectionReason.INCONSISTENT_WORD_INDEX, 1
    )


def test_commit_after_the_last_word_is_inconsistent() -> None:
    timeline = build_timeline([SourceLine(10000, "Hello")])
    events = [_commit(14500, 0, "hello"), _commit(14500, 0, "hello")]
    assert _rejection(events, timeline) == Rejection(RejectionReason.INCONSISTENT_WORD_INDEX, 1)


def test_low_accuracy_commit_is_a_miss_that_keeps_its_accuracy_and_resets_the_combo() -> None:
    result = _play(
        [_commit(11800, 0, "hello"), _commit(13960, 1, "zzzzzz"), _commit(15400, 2, "!!")]
    )
    assert _word(result, 1) == (Tier.MISS, Accuracy(0, 6), 0)
    assert _word(result, 2) == (Tier.MISS, Accuracy(0, 4), 0)
    assert result.max_combo == 1
    low = _play([_commit(11800, 0, "hexxx")])
    assert _word(low, 0) == (Tier.MISS, Accuracy(2, 5), 0)
    exactly_sixty = _play([_commit(11800, 0, "helxx")])
    assert _word(exactly_sixty, 0) == (Tier.PERFECT, Accuracy(3, 5), 30)


def test_too_late_commit_is_a_miss_with_its_accuracy() -> None:
    config = replace(DEFAULT_CONFIG, miss_window_ms=5000)
    result = score_play(_running(), BOTH_ON, [_commit(15301, 0, "hello")], config)
    assert isinstance(result, PlayResult)
    assert _word(result, 0) == (Tier.MISS, Accuracy(5, 5), 0)
    assert result.max_combo == 0


def test_combo_multiplier_reaches_the_next_step_on_the_eleventh_word() -> None:
    timeline = build_timeline([SourceLine(10000, " ".join(["hello"] * 11))])
    events = [_commit(t, index, "hello") for index, t in enumerate(_times(timeline))]
    result = _play(events, timeline)
    points = [w.points for w in result.lines[0].words]
    assert points == [50] * 10 + [63]
    assert result.max_combo == 11
    assert result.lines[0].bonus == 50


def _times(timeline: Timeline) -> list[int]:
    return [
        w.expected_ms for line in timeline.lines for w in line.words if w.expected_ms is not None
    ]


def test_scorable_word_without_expected_time_is_a_caller_error() -> None:
    timeline = Timeline((Line(0, 1000, "abc", (Word("abc", None),)),))
    with pytest.raises(ValueError, match="no expected time"):
        start_replay(timeline, PlaySettings(True, True))


# ---------------------------------------------------------------------- rank and rates


@pytest.mark.parametrize(
    ("score", "rank"),
    [
        (234, Rank.S),
        (233, Rank.A),
        (195, Rank.A),
        (194, Rank.B),
        (143, Rank.B),
        (142, Rank.C),
        (91, Rank.C),
        (90, Rank.D),
        (0, Rank.D),
    ],
)
def test_rank_thresholds_include_equality(score: int, rank: Rank) -> None:
    assert rank_for(score, 260, 8) is rank


def test_rank_is_d_without_scorable_words() -> None:
    assert rank_for(0, 0, 0) is Rank.D


# ------------------------------------------------------------------- play settings


def _single(text: str) -> Timeline:
    return build_timeline([SourceLine(10000, text)])


@pytest.mark.parametrize(
    ("text", "typed", "accent", "case", "accuracy", "points"),
    [
        ("canción", "cancion", True, True, Accuracy(7, 7), 70),
        ("canción", "cancion", False, True, Accuracy(7, 8), 61),
        ("Hello", "hello", True, False, Accuracy(4, 5), 40),
        ("Hello", "hello", True, True, Accuracy(5, 5), 50),
        ("Canción", "cancion", True, False, Accuracy(6, 7), 60),
        ("Canción", "cancion", False, False, Accuracy(6, 8), 53),
        ("áéíb", "áéíc", False, True, Accuracy(3, 4), 30),
        ("áéíb", "áéíc", True, True, Accuracy(3, 4), 30),
    ],
)
def test_settings_change_only_the_accuracy(
    text: str, typed: str, accent: bool, case: bool, accuracy: Accuracy, points: int
) -> None:
    timeline = _single(text)
    settings = {"accent_insensitive": accent, "case_insensitive": case}
    result = _play(
        [_commit(timeline.lines[0].words[0].expected_ms or 0, 0, typed)], timeline, settings
    )
    assert _word(result, 0) == (Tier.PERFECT, accuracy, points)
    assert result.settings == PlaySettings(accent, case)


def test_max_base_score_and_scorable_words_do_not_depend_on_settings() -> None:
    timeline = build_timeline([SourceLine(10000, "Canción sí"), SourceLine(14000, "Ñandú")])
    results = [
        _play([], timeline, {"accent_insensitive": a, "case_insensitive": c})
        for a in (True, False)
        for c in (True, False)
    ]
    assert {(r.max_base_score, r.scorable_words) for r in results} == {(10 * (7 + 2 + 5), 3)}


# -------------------------------------------------------------- step API, determinism


def test_step_function_matches_score_play_event_by_event() -> None:
    events: list[Json] = [
        _commit(11300, 0, "Hello"),
        _pause(12000),
        _seek(26000, 12000),
        _commit(26100, 4, "up"),
    ]
    state = start_replay(_running(), PlaySettings(True, True))
    assert step(state, Commit(11300, 0, "Hello")) is None
    advance_to(state, 19000)
    assert [r.tier for r in state.results] == [Tier.PERFECT, Tier.MISS, Tier.MISS]
    stepped = finish(state)
    assert stepped.scorable_words == 8
    assert stepped.score == 50
    assert _play(events).score == 56


def test_scoring_the_same_input_twice_gives_equal_results() -> None:
    events = [_commit(11300, 0, "Hello"), _commit(14660, 1, "brigth"), _seek(5000, 14660)]
    assert _play(events) == _play(events)
    assert _play(events) is not _play(events)


# ------------------------------------------------------------------------ performance


def test_dense_300_second_play_is_scored_in_under_a_second() -> None:
    line_text = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
    timeline = build_timeline([SourceLine(index * 1000, line_text) for index in range(300)])
    times = _times(timeline)
    assert len(times) == 3000
    events = [_commit(t, index, "alpha") for index, t in enumerate(times)]
    started = time.perf_counter()
    result = _play(events, timeline)
    elapsed = time.perf_counter() - started
    assert result.scorable_words == 3000
    assert elapsed < 1.0


# ------------------------------------------------------------------ whole-play property

_POOL = [
    "Canción",
    "sí",
    "Ñandú",
    "Hello,",
    "bright",
    "moon",
    "áéíb",
    "Straße",
    "Don" + chr(0x2019) + "t",
    chr(0x2014),
]
_RANKS = [Rank.S, Rank.A, Rank.B, Rank.C, Rank.D]


def _mutate(rng: random.Random, word: str) -> str:
    stripped = "".join(
        c for c in unicodedata.normalize("NFD", word) if unicodedata.category(c) != "Mn"
    )
    options = [word, word.lower(), stripped, stripped.lower(), word[:-1] or word, word + "x"]
    options.append(word[:1] + "x" + word[2:])
    return rng.choice(options)


def _random_play(rng: random.Random) -> tuple[Timeline, list[Json]]:
    starts = []
    start = rng.randint(0, 3000)
    lines = []
    for _ in range(rng.randint(1, 6)):
        starts.append(start)
        lines.append(SourceLine(start, " ".join(rng.choices(_POOL, k=rng.randint(0, 5)))))
        start += rng.randint(500, 7000)
    timeline = build_timeline(lines)
    events: list[Json] = []
    previous = 0
    index = 0
    for line in timeline.lines:
        for word in line.words:
            if word.expected_ms is not None:
                t = max(previous, rng.randint(line.start_ms - 1500, word.expected_ms + 3400))
                events.append(_commit(t, index, _mutate(rng, word.text)))
                previous = t
                if rng.random() < 0.2:
                    events.append(_pause(t))
            index += 1
    return timeline, events


def test_options_never_raise_any_result_above_both_on() -> None:
    rng = random.Random(20261119)
    off_settings = [
        {"accent_insensitive": a, "case_insensitive": c}
        for a, c in ((False, True), (True, False), (False, False))
    ]
    for _ in range(150):
        timeline, events = _random_play(rng)
        base = _play(events, timeline, BOTH_ON)
        for settings in off_settings:
            other = _play(events, timeline, settings)
            assert other.max_base_score == base.max_base_score
            assert other.score <= base.score
            assert other.max_combo <= base.max_combo
            assert other.hit_words <= base.hit_words
            assert other.accuracy_bp <= base.accuracy_bp
            assert _RANKS.index(other.rank) >= _RANKS.index(base.rank)
            for line_off, line_on in zip(other.lines, base.lines, strict=True):
                assert line_off.bonus <= line_on.bonus
                for word_off, word_on in zip(line_off.words, line_on.words, strict=True):
                    assert word_off.points <= word_on.points
                    assert (
                        word_off.accuracy.num * word_on.accuracy.den
                        <= word_on.accuracy.num * word_off.accuracy.den
                    )

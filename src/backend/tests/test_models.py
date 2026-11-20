"""Tests of the models and their strict JSON parsing."""

import json
from copy import deepcopy

import pytest

from typeoke_core.config import DEFAULT_CONFIG, MAX_JSON_INT, ScoringConfig
from typeoke_core.models import (
    Accuracy,
    Commit,
    Event,
    Line,
    LineResult,
    Pause,
    PlayResult,
    PlaySettings,
    Rank,
    Rejection,
    RejectionReason,
    Resume,
    Seek,
    Tier,
    Timeline,
    Word,
    WordResult,
    decode_json,
    event_log_to_json,
    is_valid_int,
    parse_event_log,
    parse_play_settings,
    play_settings_to_json,
    rejection_from_json,
    rejection_to_json,
    result_from_json,
    result_to_json,
    timeline_from_json,
    timeline_to_json,
)

WORDS = 8
MALFORMED = RejectionReason.MALFORMED_EVENT_LOG
BAD_SETTINGS = Rejection(RejectionReason.MALFORMED_PLAY_SETTINGS, None)

SPEC_LOG = (
    '[{"type":"commit","t":11300,"word":0,"text":"Hello"},{"type":"pause","t":14000},'
    '{"type":"resume","t":14000},{"type":"seek","t":26000,"from":26500}]'
)


def _log(value: object) -> tuple[Event, ...] | Rejection:
    return parse_event_log(value, WORDS, DEFAULT_CONFIG)


def _commit(**changes: object) -> dict[str, object]:
    return {"type": "commit", "t": 100, "word": 0, "text": "a"} | changes


# ------------------------------------------------------------------- event log


def test_every_event_type_round_trips() -> None:
    events = (Commit(11300, 0, "Hello"), Pause(14000), Resume(14000), Seek(26000, 26500))
    as_json = event_log_to_json(events)
    assert as_json == json.loads(SPEC_LOG)
    assert _log(json.loads(json.dumps(as_json))) == events


def test_spec_example_log_parses() -> None:
    assert _log(decode_json(SPEC_LOG)) == (
        Commit(11300, 0, "Hello"),
        Pause(14000),
        Resume(14000),
        Seek(26000, 26500),
    )


def test_empty_log_is_valid() -> None:
    assert _log([]) == ()


@pytest.mark.parametrize("value", [None, {}, "[]", 5, True, {"type": "pause", "t": 1}])
def test_log_that_is_not_an_array_has_no_index(value: object) -> None:
    assert _log(value) == Rejection(MALFORMED, None)


@pytest.mark.parametrize(
    "event",
    [
        "pause",
        None,
        [],
        {},
        {"t": 1},
        {"type": "jump", "t": 1},
        {"type": 5, "t": 1},
        {"type": ["pause"], "t": 1},
        {"type": "pause"},
        {"type": "pause", "t": 1, "extra": 0},
        {"type": "resume", "t": 1, "from": 0},
        {"type": "seek", "t": 1},
        {"type": "seek", "from": 1},
        {"type": "commit", "t": 1, "word": 0},
        {"type": "commit", "t": 1, "text": "a"},
        {"type": "commit", "word": 0, "text": "a"},
        {"type": "pause", "t": "1"},
        {"type": "pause", "t": 1.5},
        {"type": "pause", "t": 1.0},
        {"type": "pause", "t": True},
        {"type": "pause", "t": None},
        {"type": "pause", "t": -1},
        {"type": "pause", "t": MAX_JSON_INT + 1},
        {"type": "seek", "t": 1, "from": -5},
        {"type": "seek", "t": 1, "from": False},
        {"type": "seek", "t": 1, "from": 2.5},
        _commit(word=True),
        _commit(word=-1),
        _commit(word=1.0),
        _commit(word=WORDS),
        _commit(word=99),
        _commit(text=""),
        _commit(text=5),
        _commit(text=None),
        _commit(text="x" * 65),
        _commit(text="a\ud800b"),
        _commit(text="\udfff"),
        _commit(t=-1),
    ],
)
def test_malformed_event_reports_its_index(event: object) -> None:
    assert _log([{"type": "pause", "t": 0}, event]) == Rejection(MALFORMED, 1)


def test_first_malformed_event_wins_over_later_ones() -> None:
    assert _log([_commit(), "x", {"type": "bad"}]) == Rejection(MALFORMED, 1)


def test_text_limits_are_in_code_points() -> None:
    assert _log([_commit(text="x" * 64)]) == (Commit(100, 0, "x" * 64),)
    assert _log([_commit(text="\U0001f600" * 64)]) == (Commit(100, 0, "\U0001f600" * 64),)
    assert _log([_commit(text="\U0001f600" * 65)]) == Rejection(MALFORMED, 0)


def test_text_limit_follows_the_configuration() -> None:
    config = ScoringConfig(max_typed_chars=3)
    assert parse_event_log([_commit(text="abc")], WORDS, config) == (Commit(100, 0, "abc"),)
    assert parse_event_log([_commit(text="abcd")], WORDS, config) == Rejection(MALFORMED, 0)


def test_largest_integer_is_accepted_and_minus_zero_is_zero() -> None:
    log = decode_json('[{"type":"pause","t":9007199254740991},{"type":"pause","t":-0}]')
    assert _log(log) == (Pause(MAX_JSON_INT), Pause(0))


def test_paired_surrogates_decode_to_a_valid_character() -> None:
    log = decode_json('[{"type":"commit","t":1,"word":0,"text":"\\ud83d\\ude00"}]')
    assert _log(log) == (Commit(1, 0, "\U0001f600"),)
    lone = decode_json('[{"type":"commit","t":1,"word":0,"text":"\\ud83d"}]')
    assert _log(lone) == Rejection(MALFORMED, 0)


def test_word_index_is_checked_against_the_timeline_size() -> None:
    assert parse_event_log([_commit(word=0)], 1, DEFAULT_CONFIG) == (Commit(100, 0, "a"),)
    assert parse_event_log([_commit(word=1)], 1, DEFAULT_CONFIG) == Rejection(MALFORMED, 0)
    assert parse_event_log([_commit(word=0)], 0, DEFAULT_CONFIG) == Rejection(MALFORMED, 0)


# --------------------------------------------------------------- play settings


@pytest.mark.parametrize("accent", [True, False])
@pytest.mark.parametrize("case", [True, False])
def test_play_settings_round_trip(accent: bool, case: bool) -> None:
    settings = PlaySettings(accent, case)
    as_json = play_settings_to_json(settings)
    assert as_json == {"accent_insensitive": accent, "case_insensitive": case}
    assert parse_play_settings(json.loads(json.dumps(as_json))) == settings


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        "true",
        0,
        True,
        {},
        {"accent_insensitive": True},
        {"case_insensitive": True},
        {"accent_insensitive": True, "case_insensitive": 1},
        {"accent_insensitive": 0, "case_insensitive": True},
        {"accent_insensitive": True, "case_insensitive": "true"},
        {"accent_insensitive": True, "case_insensitive": None},
        {"accent_insensitive": True, "case_insensitive": True, "locale": "es"},
    ],
)
def test_malformed_play_settings_have_no_index(value: object) -> None:
    assert parse_play_settings(value) == BAD_SETTINGS


# ------------------------------------------------------------------- rejection


@pytest.mark.parametrize("reason", list(RejectionReason))
@pytest.mark.parametrize("index", [None, 0, 7])
def test_rejection_round_trips(reason: RejectionReason, index: int | None) -> None:
    rejection = Rejection(reason, index)
    as_json = rejection_to_json(rejection)
    assert as_json == {"reason": reason.value, "event_index": index}
    assert rejection_from_json(json.loads(json.dumps(as_json))) == rejection


@pytest.mark.parametrize(
    "value",
    [
        None,
        {"reason": "NON_MONOTONIC_TIME"},
        {"reason": "OTHER", "event_index": 1},
        {"reason": 5, "event_index": 1},
        {"reason": "NON_MONOTONIC_TIME", "event_index": -1},
        {"reason": "NON_MONOTONIC_TIME", "event_index": "1"},
        {"reason": "NON_MONOTONIC_TIME", "event_index": 1, "extra": 0},
    ],
)
def test_rejection_with_another_shape_raises(value: object) -> None:
    with pytest.raises(ValueError):
        rejection_from_json(value)


# -------------------------------------------------------------------- timeline

TIMELINE_JSON: dict[str, object] = {
    "lines": [
        {
            "start_ms": 10000,
            "end_ms": 16000,
            "text": "Hello, bright moon",
            "words": [
                {"text": "Hello,", "expected_ms": 11800},
                {"text": "bright", "expected_ms": 13960},
                {"text": "moon", "expected_ms": 15400},
            ],
        },
        {"start_ms": 20000, "end_ms": 24000, "text": "", "words": []},
        {
            "start_ms": 40000,
            "end_ms": 44000,
            "text": "Oh — yes",
            "words": [
                {"text": "Oh", "expected_ms": 41440},
                {"text": "—", "expected_ms": None},
                {"text": "yes", "expected_ms": 43600},
            ],
        },
    ]
}


def test_timeline_round_trips() -> None:
    timeline = timeline_from_json(TIMELINE_JSON)
    assert timeline.word_count == 6
    assert timeline.lines[2].words[1] == Word("—", None)
    assert timeline_to_json(timeline) == TIMELINE_JSON
    assert timeline_from_json(timeline_to_json(timeline)) == timeline


def test_empty_timeline_is_valid() -> None:
    assert timeline_from_json({"lines": []}) == Timeline(())


def _timeline_with(path: list[object], value: object) -> dict[str, object]:
    changed = deepcopy(TIMELINE_JSON)
    target: object = changed
    for step in path[:-1]:
        target = target[step]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]
    return changed


@pytest.mark.parametrize(
    "bad",
    [
        None,
        {},
        {"lines": {}},
        {"lines": [], "extra": 1},
        _timeline_with(["lines", 0, "start_ms"], 1.5),
        _timeline_with(["lines", 0, "start_ms"], -1),
        _timeline_with(["lines", 0, "end_ms"], 9999),
        _timeline_with(["lines", 0, "text"], 5),
        _timeline_with(["lines", 0, "words"], "x"),
        _timeline_with(["lines", 0, "extra"], 1),
        _timeline_with(["lines", 1, "start_ms"], 5000),
        _timeline_with(["lines", 0, "words", 0, "text"], ""),
        _timeline_with(["lines", 0, "words", 0, "expected_ms"], "1"),
        _timeline_with(["lines", 0, "words", 1, "expected_ms"], 100),
        _timeline_with(["lines", 0, "words", 0], "word"),
    ],
)
def test_invalid_timeline_raises(bad: object) -> None:
    with pytest.raises(ValueError):
        timeline_from_json(bad)


def test_line_and_word_dataclasses_are_frozen() -> None:
    line = Line(1, 2, "a", (Word("a", 1),))
    with pytest.raises(AttributeError):
        line.start_ms = 5  # type: ignore[misc]


# ---------------------------------------------------------------- play result

RESULT = PlayResult(
    settings=PlaySettings(True, True),
    score=175,
    accuracy_bp=7083,
    hit_rate_bp=7500,
    max_combo=2,
    rank=Rank.B,
    seeked=False,
    scorable_words=8,
    hit_words=6,
    max_base_score=260,
    lines=(
        LineResult(0, 94, 0, (WordResult(0, Tier.PERFECT, Accuracy(5, 5), 50),)),
        LineResult(1, 0, 0, ()),
        LineResult(2, 0, 0, (WordResult(6, Tier.MISS, Accuracy(0, 1), 0),)),
    ),
)


def test_play_result_round_trips_with_every_field() -> None:
    as_json = result_to_json(RESULT)
    assert list(as_json) == [
        "settings",
        "score",
        "accuracy_bp",
        "hit_rate_bp",
        "max_combo",
        "rank",
        "seeked",
        "scorable_words",
        "hit_words",
        "max_base_score",
        "lines",
    ]
    assert as_json["settings"] == {"accent_insensitive": True, "case_insensitive": True}
    assert result_from_json(json.loads(json.dumps(as_json))) == RESULT


def _result_with(path: list[object], value: object) -> object:
    changed = json.loads(json.dumps(result_to_json(RESULT)))
    target = changed
    for step in path[:-1]:
        target = target[step]
    target[path[-1]] = value
    return changed


@pytest.mark.parametrize(
    "bad",
    [
        None,
        {},
        _result_with(["extra"], 1),
        _result_with(["settings"], {"accent_insensitive": True}),
        _result_with(["score"], 1.5),
        _result_with(["score"], True),
        _result_with(["score"], -1),
        _result_with(["rank"], "E"),
        _result_with(["rank"], 1),
        _result_with(["seeked"], 0),
        _result_with(["lines"], {}),
        _result_with(["lines", 0, "extra"], 1),
        _result_with(["lines", 0, "words"], None),
        _result_with(["lines", 0, "words", 0, "tier"], "BAD"),
        _result_with(["lines", 0, "words", 0, "tier"], None),
        _result_with(["lines", 0, "words", 0, "accuracy"], {"num": 1}),
        _result_with(["lines", 0, "words", 0, "accuracy", "den"], 1.0),
    ],
)
def test_invalid_play_result_raises(bad: object) -> None:
    with pytest.raises(ValueError):
        result_from_json(bad)


# --------------------------------------------------------------------- decoder


@pytest.mark.parametrize(
    "text",
    ['{"a": NaN}', "[Infinity]", "[-Infinity]", '{"a": 1, "a": 2}', '[{"b": 1, "b": 1}]', "[1,"],
)
def test_canonical_decoder_rejects_invalid_input(text: str) -> None:
    with pytest.raises(ValueError):
        decode_json(text)


def test_canonical_decoder_keeps_numbers_as_written() -> None:
    decoded = decode_json("[1, 1.0, 1e2, true]")
    assert isinstance(decoded, list)
    assert [type(item) for item in decoded] == [int, float, float, bool]


def test_is_valid_int_excludes_bool_float_and_range() -> None:
    assert is_valid_int(0)
    assert is_valid_int(MAX_JSON_INT)
    assert not is_valid_int(True)
    assert not is_valid_int(1.0)
    assert not is_valid_int(-1)
    assert not is_valid_int(MAX_JSON_INT + 1)
    assert not is_valid_int("1")

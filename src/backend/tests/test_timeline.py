"""Tests of the expected-time rule (sections 6 and 16 of docs/scoring.md)."""

import pytest

from typeoke_core.config import MAX_JSON_INT, ScoringConfig
from typeoke_core.models import Timeline, timeline_from_json, timeline_to_json
from typeoke_core.scoring import round_half_up
from typeoke_core.timeline import SourceLine, build_timeline, line_end_ms


def _times(timeline: Timeline, line: int) -> list[int | None]:
    return [w.expected_ms for w in timeline.lines[line].words]


def _running_example() -> Timeline:
    return build_timeline(
        [
            SourceLine(10000, "Hello, bright moon"),
            SourceLine(20000, "Sky up"),
            SourceLine(24025, "La la la"),
        ]
    )


def test_round_half_up_goes_to_the_larger_integer() -> None:
    assert round_half_up(5, 2) == 3
    assert round_half_up(125, 2) == 63
    assert round_half_up(7, 2) == 4
    assert round_half_up(9, 4) == 2
    assert round_half_up(0, 7) == 0


def test_worked_example_line_zero_with_gap_capped() -> None:
    timeline = _running_example()
    line = timeline.lines[0]
    assert (line.start_ms, line.end_ms) == (10000, 16000)
    assert [w.text for w in line.words] == ["Hello,", "bright", "moon"]
    assert _times(timeline, 0) == [11800, 13960, 15400]


def test_worked_example_half_up_cases_in_line_one() -> None:
    timeline = _running_example()
    assert timeline.lines[1].end_ms == 24025
    assert _times(timeline, 1) == [22174, 23623]


def test_worked_example_last_line_uses_the_last_window() -> None:
    timeline = _running_example()
    assert timeline.lines[2].end_ms == 29025
    assert _times(timeline, 2) == [25525, 27025, 28525]


def test_accented_line_uses_song_normalized_lengths() -> None:
    timeline = build_timeline([SourceLine(30000, "Canción sí"), SourceLine(34000, "x")])
    assert timeline.lines[0].end_ms == 34000
    assert _times(timeline, 0) == [32800, 33600]


def test_non_scorable_word_gets_null_and_is_not_counted() -> None:
    timeline = build_timeline([SourceLine(0, "Oh — yes")])
    assert _times(timeline, 0) == [1800, None, 4500]
    assert [w.text for w in timeline.lines[0].words] == ["Oh", "—", "yes"]


def test_punctuation_only_line_has_only_null_times() -> None:
    timeline = build_timeline([SourceLine(1000, "... !!!")])
    assert _times(timeline, 0) == [None, None]


def test_empty_line_has_a_window_and_no_words() -> None:
    timeline = build_timeline(
        [SourceLine(0, "a"), SourceLine(2000, "  \t "), SourceLine(3000, "b")]
    )
    empty = timeline.lines[1]
    assert (empty.start_ms, empty.end_ms, empty.words) == (2000, 3000, ())
    assert timeline.lines[0].end_ms == 2000


def test_gap_over_six_seconds_is_capped() -> None:
    timeline = build_timeline([SourceLine(0, "ab"), SourceLine(6001, "cd")])
    assert timeline.lines[0].end_ms == 6000
    assert _times(timeline, 0) == [5400]


def test_gap_of_exactly_six_seconds_is_not_capped_further() -> None:
    assert line_end_ms([0, 6000], 0) == 6000


def test_same_start_gives_a_zero_window() -> None:
    timeline = build_timeline([SourceLine(500, "ab"), SourceLine(500, "cd")])
    assert (timeline.lines[0].end_ms, _times(timeline, 0)) == (500, [500])


def test_no_lines_gives_an_empty_timeline() -> None:
    assert build_timeline([]) == Timeline(())


def test_configuration_changes_windows_and_percentage() -> None:
    config = ScoringConfig(max_line_window_ms=1000, last_line_window_ms=2000, expected_time_pct=50)
    timeline = build_timeline([SourceLine(0, "ab"), SourceLine(9000, "cd")], config)
    assert timeline.lines[0].end_ms == 1000
    assert _times(timeline, 0) == [500]
    assert timeline.lines[1].end_ms == 11000
    assert _times(timeline, 1) == [9000 + 1000]


def test_play_settings_never_change_the_times() -> None:
    # The accent-off count of "canción" is 8; the rule must still use 7.
    timeline = build_timeline([SourceLine(0, "canción cancion")])
    assert _times(timeline, 0) == [2250, 4500]


def test_supplied_times_take_precedence_and_others_keep_the_rule() -> None:
    line = SourceLine(0, "ab cd ef", word_times=(None, 3333, None))
    timeline = build_timeline([line, SourceLine(6000, "x")])
    # total_chars 6 and W 6000: ab through 2 -> 1800, ef through 6 -> 5400.
    assert _times(timeline, 0) == [1800, 3333, 5400]


def test_supplied_time_of_a_non_scorable_word_is_ignored() -> None:
    line = SourceLine(0, "ab — cd", word_times=(None, 777, None))
    assert _times(build_timeline([line]), 0) == [2250, None, 4500]


def test_timeline_round_trips_through_the_json_parser() -> None:
    timeline = _running_example()
    assert timeline_from_json(timeline_to_json(timeline)) == timeline


def test_start_must_be_an_integer_in_range() -> None:
    for bad in (-1, 1.5, True, MAX_JSON_INT + 1, "0"):
        with pytest.raises(ValueError, match="line start"):
            build_timeline([SourceLine(bad, "a")])  # type: ignore[arg-type]


def test_text_must_be_a_string() -> None:
    with pytest.raises(ValueError, match="line text"):
        build_timeline([SourceLine(0, None)])  # type: ignore[arg-type]


def test_starts_must_not_decrease() -> None:
    with pytest.raises(ValueError, match="must not decrease"):
        build_timeline([SourceLine(5, "a"), SourceLine(4, "b")])


def test_end_must_stay_in_the_json_integer_range() -> None:
    with pytest.raises(ValueError, match="line end"):
        build_timeline([SourceLine(MAX_JSON_INT, "a")])


def test_expected_word_longer_than_ten_thousand_code_points_is_invalid() -> None:
    build_timeline([SourceLine(0, "a" * 10000)])
    with pytest.raises(ValueError, match="10000"):
        build_timeline([SourceLine(0, "a" * 10001)])


def test_length_limit_counts_the_accent_off_form() -> None:
    # 5001 letters with one mark each: 5001 under the song form, 10002 with accents kept.
    with pytest.raises(ValueError, match="10000"):
        build_timeline([SourceLine(0, "á" * 5001)])


def test_supplied_times_must_match_the_word_count() -> None:
    with pytest.raises(ValueError, match="one entry per word"):
        build_timeline([SourceLine(0, "a b", word_times=(1,))])


def test_supplied_time_must_be_a_valid_integer() -> None:
    for bad in (-1, 1.5, True, MAX_JSON_INT + 1):
        with pytest.raises(ValueError, match="supplied word time"):
            build_timeline([SourceLine(0, "a", word_times=(bad,))])  # type: ignore[arg-type]


def test_supplied_times_that_decrease_are_invalid() -> None:
    with pytest.raises(ValueError, match="expected times"):
        build_timeline([SourceLine(0, "a b", word_times=(900, 100))])


def test_supplied_time_above_the_next_line_is_invalid() -> None:
    lines = [SourceLine(0, "a", word_times=(9000,)), SourceLine(1000, "b")]
    with pytest.raises(ValueError, match="expected times"):
        build_timeline(lines)

"""Tests of tiers, points, combo and line bonus (sections 7 to 10 of docs/scoring.md)."""

import random

import pytest

from typeoke_core.config import ScoringConfig
from typeoke_core.models import Accuracy, PlaySettings, Tier, WordResult
from typeoke_core.scoring import (
    combo_multiplier_pct,
    commit_tier,
    line_bonus,
    meets_accuracy_pct,
    next_combo,
    round_half_up,
    song_normalize,
    tier_pct,
    timing_tier,
    word_accuracy,
    word_points,
)

CONFIG = ScoringConfig()
BOTH_ON = PlaySettings(accent_insensitive=True, case_insensitive=True)


@pytest.mark.parametrize(
    ("delta", "tier"),
    [
        (0, Tier.PERFECT),
        (600, Tier.PERFECT),
        (-600, Tier.PERFECT),
        (601, Tier.GREAT),
        (1200, Tier.GREAT),
        (1201, Tier.GOOD),
        (2200, Tier.GOOD),
        (2201, Tier.OK),
        (3500, Tier.OK),
        (-3500, Tier.OK),
        (3501, Tier.MISS),
        (-3501, Tier.EARLY),
    ],
)
def test_timing_tier_boundaries_belong_to_the_better_tier(delta: int, tier: Tier) -> None:
    assert timing_tier(delta, CONFIG) is tier


def test_tier_percentages() -> None:
    assert [tier_pct(tier, CONFIG) for tier in Tier] == [100, 80, 55, 30, 10, 0]


def test_accuracy_threshold_is_inclusive_and_exact() -> None:
    assert meets_accuracy_pct(Accuracy(3, 5), 60)
    assert not meets_accuracy_pct(Accuracy(2, 5), 60)
    assert meets_accuracy_pct(Accuracy(4, 5), 80)
    assert not meets_accuracy_pct(Accuracy(4, 6), 80)
    assert not meets_accuracy_pct(Accuracy(79, 100), 80)


def test_commit_tier_below_min_accuracy_is_a_miss() -> None:
    assert commit_tier(0, Accuracy(3, 5), CONFIG) is Tier.PERFECT
    assert commit_tier(0, Accuracy(2, 5), CONFIG) is Tier.MISS
    assert commit_tier(0, Accuracy(59, 100), CONFIG) is Tier.MISS
    assert commit_tier(0, Accuracy(60, 100), CONFIG) is Tier.PERFECT


def test_commit_tier_follows_the_delta_otherwise() -> None:
    assert commit_tier(2000, Accuracy(5, 5), CONFIG) is Tier.GOOD
    assert commit_tier(3501, Accuracy(5, 5), CONFIG) is Tier.MISS
    assert commit_tier(-3501, Accuracy(5, 5), CONFIG) is Tier.EARLY


@pytest.mark.parametrize(
    ("combo", "pct"),
    [
        (0, 100),
        (9, 100),
        (10, 125),
        (19, 125),
        (20, 150),
        (30, 175),
        (39, 175),
        (40, 200),
        (41, 200),
        (50, 200),
        (1000, 200),
    ],
)
def test_combo_multiplier(combo: int, pct: int) -> None:
    assert combo_multiplier_pct(combo, CONFIG) == pct


def test_first_ten_words_at_100_and_the_eleventh_at_125() -> None:
    combo = 0
    pcts = []
    for _ in range(11):
        pcts.append(combo_multiplier_pct(combo, CONFIG))
        combo = next_combo(combo, Tier.PERFECT, Accuracy(5, 5), CONFIG)
    assert pcts == [100] * 10 + [125]
    assert combo == 11


@pytest.mark.parametrize(
    ("tier", "accuracy", "expected"),
    [
        (Tier.PERFECT, Accuracy(5, 5), 8),
        (Tier.GREAT, Accuracy(4, 5), 8),
        (Tier.GOOD, Accuracy(4, 5), 8),
        (Tier.PERFECT, Accuracy(4, 6), 7),
        (Tier.PERFECT, Accuracy(3, 5), 7),
        (Tier.OK, Accuracy(5, 5), 7),
        (Tier.EARLY, Accuracy(5, 5), 7),
        (Tier.MISS, Accuracy(5, 5), 0),
        (Tier.MISS, Accuracy(0, 1), 0),
    ],
)
def test_next_combo(tier: Tier, accuracy: Accuracy, expected: int) -> None:
    assert next_combo(7, tier, accuracy, CONFIG) == expected


def test_round_half_up_examples() -> None:
    assert round_half_up(125, 2) == 63
    assert round_half_up(5, 2) == 3
    assert round_half_up(4347, 2) == 2174  # 2173.5
    assert round_half_up(4200000, 80000) == 53  # 52.5
    assert round_half_up(2500000, 60000) == 42  # 41.67
    assert round_half_up(4900000, 80000) == 61  # 61.25
    assert round_half_up(0, 7) == 0


@pytest.mark.parametrize(
    ("lexp", "accuracy", "tier", "combo", "points"),
    [
        (5, Accuracy(5, 5), Tier.PERFECT, 0, 50),  # hello, PERFECT
        (6, Accuracy(4, 6), Tier.GREAT, 1, 32),  # bright / brigth
        (4, Accuracy(4, 4), Tier.OK, 1, 12),  # moon at +3500
        (5, Accuracy(5, 6), Tier.PERFECT, 0, 42),  # helloo
        (5, Accuracy(5, 5), Tier.PERFECT, 10, 63),  # 62.5 rounds up
        (5, Accuracy(3, 5), Tier.PERFECT, 0, 30),  # exactly 60 %
        (7, Accuracy(7, 7), Tier.PERFECT, 0, 70),  # canción, both on
        (7, Accuracy(7, 8), Tier.PERFECT, 0, 61),  # accent option off
        (5, Accuracy(4, 5), Tier.PERFECT, 0, 40),  # case option off
        (7, Accuracy(6, 7), Tier.PERFECT, 0, 60),  # case off, Canción
        (7, Accuracy(6, 8), Tier.PERFECT, 0, 53),  # both off, 52.5
        (4, Accuracy(3, 4), Tier.PERFECT, 0, 30),  # áéíb mixed
        (3, Accuracy(3, 3), Tier.OK, 0, 9),  # sky
        (2, Accuracy(2, 2), Tier.OK, 0, 6),
        (6, Accuracy(6, 6), Tier.EARLY, 1, 6),
        (5, Accuracy(5, 5), Tier.MISS, 0, 0),
    ],
)
def test_word_points_worked_examples(
    lexp: int, accuracy: Accuracy, tier: Tier, combo: int, points: int
) -> None:
    assert word_points(lexp, accuracy, tier, combo, CONFIG) == points


def test_word_points_use_the_combo_before_the_word_and_the_cap() -> None:
    assert word_points(5, Accuracy(5, 5), Tier.PERFECT, 9, CONFIG) == 50
    assert word_points(5, Accuracy(5, 5), Tier.PERFECT, 40, CONFIG) == 100
    assert word_points(5, Accuracy(5, 5), Tier.PERFECT, 500, CONFIG) == 100


def _points(expected: str, typed: str, settings: PlaySettings) -> int:
    accuracy = word_accuracy(expected, typed, settings)
    lexp = len(song_normalize(expected))
    return word_points(lexp, accuracy, commit_tier(0, accuracy, CONFIG), 0, CONFIG)


def test_mixed_marks_score_the_same_in_both_settings() -> None:
    accent_off = PlaySettings(accent_insensitive=False, case_insensitive=True)
    assert _points("áéíb", "áéíc", accent_off) == 30
    assert _points("áéíb", "áéíc", BOTH_ON) == 30


def test_play_settings_worked_examples_through_the_accuracy() -> None:
    accent_off = PlaySettings(accent_insensitive=False, case_insensitive=True)
    case_off = PlaySettings(accent_insensitive=True, case_insensitive=False)
    both_off = PlaySettings(accent_insensitive=False, case_insensitive=False)
    assert _points("canción", "cancion", BOTH_ON) == 70
    assert _points("canción", "cancion", accent_off) == 61
    assert _points("Hello", "hello", case_off) == 40
    assert _points("Canción", "cancion", case_off) == 60
    assert _points("Canción", "cancion", both_off) == 53


def test_points_with_an_option_off_never_exceed_both_on() -> None:
    rng = random.Random(20260101)
    alphabet = "aáeéiíbBcCñn"
    settings = [
        PlaySettings(accent_insensitive=a, case_insensitive=c)
        for a in (True, False)
        for c in (True, False)
    ]
    for _ in range(300):
        expected = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 8)))
        typed = "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 8)))
        best = _points(expected, typed, BOTH_ON)
        for option in settings:
            assert _points(expected, typed, option) <= best


def _result(tier: Tier, num: int, den: int) -> WordResult:
    return WordResult(word=0, tier=tier, accuracy=Accuracy(num, den), points=0)


def test_line_bonus_given_for_clean_words_whatever_the_tier() -> None:
    results = [_result(Tier.OK, 3, 3), _result(Tier.EARLY, 2, 2), _result(Tier.PERFECT, 4, 5)]
    assert line_bonus(results, CONFIG) == 50


def test_line_bonus_denied_by_a_word_under_80_percent() -> None:
    results = [_result(Tier.PERFECT, 5, 5), _result(Tier.PERFECT, 4, 6)]
    assert line_bonus(results, CONFIG) == 0


def test_line_bonus_denied_by_a_miss_even_with_kept_accuracy() -> None:
    assert line_bonus([_result(Tier.PERFECT, 5, 5), _result(Tier.MISS, 5, 5)], CONFIG) == 0
    assert line_bonus([_result(Tier.MISS, 0, 1)], CONFIG) == 0


def test_line_bonus_of_a_line_without_words_is_zero() -> None:
    assert line_bonus([], CONFIG) == 0

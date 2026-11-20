"""Tests of the text handling and word accuracy of docs/scoring.md (sections 3 and 4)."""

import random
import unicodedata

import pytest

from typeoke_core.models import Accuracy, PlaySettings
from typeoke_core.scoring import (
    is_scorable,
    levenshtein,
    normalize,
    song_normalize,
    split_words,
    word_accuracy,
)

ON_ON = PlaySettings(accent_insensitive=True, case_insensitive=True)
ACCENT_OFF = PlaySettings(accent_insensitive=False, case_insensitive=True)
CASE_OFF = PlaySettings(accent_insensitive=True, case_insensitive=False)
OFF_OFF = PlaySettings(accent_insensitive=False, case_insensitive=False)
ALL_SETTINGS = (ON_ON, ACCENT_OFF, CASE_OFF, OFF_OFF)

ACUTE = "́"
TILDE = "̃"
DOT = "̇"


def test_unicode_version_is_pinned() -> None:
    assert unicodedata.unidata_version == "16.0.0"


# ---------------------------------------------------------------- section 3.4 table


@pytest.mark.parametrize(
    ("text", "settings", "expected"),
    [
        ("Canción,", ON_ON, "cancion"),
        ("Canción,", ACCENT_OFF, "cancio" + ACUTE + "n"),
        ("Canción,", CASE_OFF, "Cancion"),
        ("Canción,", OFF_OFF, "Cancio" + ACUTE + "n"),
        ("Ñandú!", ON_ON, "nandu"),
        ("Don’t", ON_ON, "dont"),  # noqa: RUF001
        ("İstanbul", ON_ON, "istanbul"),
        ("İstanbul", ACCENT_OFF, "i" + DOT + "stanbul"),
        ("STRAẞE", ON_ON, "straße"),
        ("—", ON_ON, ""),
        ("—", OFF_OFF, ""),
        ("Hello,", ON_ON, "hello"),
        ("Hello,", CASE_OFF, "Hello"),
    ],
)
def test_normalize_table(text: str, settings: PlaySettings, expected: str) -> None:
    assert normalize(text, settings) == expected


def test_table_lengths() -> None:
    assert len(normalize("Canción,", ON_ON)) == 7
    assert len(normalize("Canción,", ACCENT_OFF)) == 8
    assert len(normalize("İstanbul", ACCENT_OFF)) == 9
    assert len(normalize("Ñandú!", ON_ON)) == 5


def test_song_normalize_ignores_play_settings() -> None:
    assert song_normalize("Canción,") == "cancion"
    assert song_normalize("Canción,") == normalize("Canción,", ON_ON)


def test_nfc_and_nfd_inputs_are_equal() -> None:
    assert normalize("cañon", ACCENT_OFF) == normalize("can" + TILDE + "on", ACCENT_OFF)


def test_ignorable_categories_are_removed() -> None:
    # P*, S*, Z*, Cc, Cf and the Cc/Cf control characters inside a word.
    assert normalize("a-b_c(d)e«f»g!h$i+j^k©l m​n\x00o", ON_ON) == ("abcdefghijklmno")


def test_kept_categories() -> None:
    # Numbers and letters are kept; Mc is not removed by the accent option.
    assert normalize("a1ำ", ON_ON) == "a1ำ"


def test_sigma_is_lowercased_per_code_point() -> None:
    assert normalize("ΟΔΟΣ", ON_ON) == "οδοσ"
    assert normalize("ς", ON_ON) != normalize("σ", ON_ON)  # noqa: RUF001


def test_turkish_and_german_limits() -> None:
    assert normalize("ı", ON_ON) == "ı"  # noqa: RUF001
    assert normalize("I", ON_ON) == "i"
    assert normalize("ß", ON_ON) == "ß"
    assert word_accuracy("Straße", "STRASSE", ON_ON) == Accuracy(5, 7)
    assert word_accuracy("Straße", "STRAẞE", ON_ON) == Accuracy(6, 6)


# ---------------------------------------------------------------------- words


def test_split_words_uses_the_section_3_set() -> None:
    assert split_words("  one\u00a0two\u3000three\n\n four  ") == ["one", "two", "three", "four"]
    assert split_words("a\u200bb") == ["a\u200bb"]
    assert split_words(" \t\u2028 ") == []
    assert split_words("") == []


def test_scorable() -> None:
    assert is_scorable("Canción,")
    assert not is_scorable("—")
    assert not is_scorable("!!!")
    assert not is_scorable("\U0001f600")
    assert is_scorable("a")


# ------------------------------------------------------------------ levenshtein


def test_levenshtein() -> None:
    assert levenshtein("", "") == 0
    assert levenshtein("abc", "") == 3
    assert levenshtein("", "abc") == 3
    assert levenshtein("kitten", "sitting") == 3
    assert levenshtein("sitting", "kitten") == 3
    assert levenshtein("ab", "ba") == 2


# ---------------------------------------------------------------------- accuracy


@pytest.mark.parametrize(
    ("expected", "typed", "settings", "accuracy"),
    [
        ("canción", "cancion", ON_ON, Accuracy(7, 7)),
        ("canción", "cansion", ON_ON, Accuracy(6, 7)),
        ("canción", "cancion", ACCENT_OFF, Accuracy(7, 8)),
        ("Hello", "hello", CASE_OFF, Accuracy(4, 5)),
        ("Hello", "hello", ON_ON, Accuracy(5, 5)),
        ("Canción", "cancion", CASE_OFF, Accuracy(6, 7)),
        ("Canción", "cancion", OFF_OFF, Accuracy(6, 8)),
        ("Canción", "cancion", ACCENT_OFF, Accuracy(7, 8)),
        ("áéíb", "áéíc", ON_ON, Accuracy(3, 4)),
        ("áéíb", "áéíc", ACCENT_OFF, Accuracy(3, 4)),
        ("hello", "helxx", ON_ON, Accuracy(3, 5)),
        ("hello", "hexxx", ON_ON, Accuracy(2, 5)),
        ("hello", "hellx", ON_ON, Accuracy(4, 5)),
        ("melody", "melxxy", ON_ON, Accuracy(4, 6)),
        ("bright", "brigth", ON_ON, Accuracy(4, 6)),
        ("no", "nonsense", ON_ON, Accuracy(2, 8)),
        ("hello", "helloo", ON_ON, Accuracy(5, 6)),
        ("hello", "!!!", ON_ON, Accuracy(0, 5)),
        ("hello", "!!!", OFF_OFF, Accuracy(0, 5)),
        ("Hello,", "Hello", CASE_OFF, Accuracy(5, 5)),
        ("ñ", "n", ON_ON, Accuracy(1, 1)),
        ("ñ", "n", ACCENT_OFF, Accuracy(1, 2)),
    ],
)
def test_word_accuracy_examples(
    expected: str, typed: str, settings: PlaySettings, accuracy: Accuracy
) -> None:
    assert word_accuracy(expected, typed, settings) == accuracy


def test_tie_reports_the_song_pair() -> None:
    # Play pair 6/8 (both options off) and song pair 3/4: equal ratios, the song pair wins.
    assert word_accuracy("áéíb", "áéíc", OFF_OFF) == Accuracy(3, 4)
    # Typed exactly: every pair is L/L, the song pair (shorter) is reported.
    assert word_accuracy("canción", "canción", ACCENT_OFF) == Accuracy(7, 7)


def test_empty_typed_text_after_normalization_is_zero() -> None:
    assert word_accuracy("hello", "—", ON_ON) == Accuracy(0, 5)


def test_accuracy_is_within_zero_and_one() -> None:
    for settings in ALL_SETTINGS:
        result = word_accuracy("no", "n" * 64, settings)
        assert 0 <= result.num <= result.den
        assert result.den >= 1


def test_option_off_never_exceeds_both_on() -> None:
    rng = random.Random(20261119)
    alphabet = ["a", "e", "i", "b", "A", "E", "B", "á", "é", "í", "Á", "ñ", "Ñ", "ß", "Σ", "ς"]
    alphabet += [ACUTE, TILDE, DOT, "İ", "!", "-"]
    for _ in range(1500):
        expected = "".join(rng.choices(alphabet, k=rng.randint(1, 8)))
        typed = "".join(rng.choices(alphabet, k=rng.randint(0, 10)))
        if not is_scorable(expected):
            continue
        best = word_accuracy(expected, typed, ON_ON)
        for settings in ALL_SETTINGS:
            got = word_accuracy(expected, typed, settings)
            assert 0 <= got.num <= got.den
            assert got.num * best.den <= best.num * got.den

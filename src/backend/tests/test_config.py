"""Tests of the scoring configuration and its canonical file."""

import json
from dataclasses import fields, replace
from pathlib import Path
from typing import Any

import pytest

from typeoke_core.config import (
    DEFAULT_CONFIG,
    ScoringConfig,
    config_from_dict,
    config_to_dict,
)
from typeoke_core.models import decode_json

CONFIG_JSON = Path(__file__).resolve().parents[3] / "testdata" / "scoring" / "config.json"


def _canonical() -> dict[str, object]:
    decoded = decode_json(CONFIG_JSON.read_text(encoding="utf-8"))
    assert isinstance(decoded, dict)
    return decoded


def test_default_config_equals_config_json_field_by_field() -> None:
    canonical = _canonical()
    assert list(canonical) == [field.name for field in fields(ScoringConfig)]
    for field in fields(ScoringConfig):
        value = getattr(DEFAULT_CONFIG, field.name)
        assert canonical[field.name] == value
        assert type(canonical[field.name]) is type(value), field.name


def test_config_json_has_the_documented_default_flags() -> None:
    canonical = _canonical()
    assert canonical["default_accent_insensitive"] is True
    assert canonical["default_case_insensitive"] is True


def test_config_json_is_lf_without_bom() -> None:
    raw = CONFIG_JSON.read_bytes()
    assert b"\r" not in raw
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.endswith(b"}\n")


def test_dict_round_trip_keeps_key_order() -> None:
    as_dict = config_to_dict(DEFAULT_CONFIG)
    assert list(as_dict) == list(_canonical())
    assert config_from_dict(json.loads(json.dumps(as_dict))) == DEFAULT_CONFIG


def test_config_from_dict_rejects_missing_and_extra_keys() -> None:
    canonical = _canonical()
    missing = {key: value for key, value in canonical.items() if key != "line_bonus"}
    with pytest.raises(ValueError, match="line_bonus"):
        config_from_dict(missing)
    with pytest.raises(ValueError, match="surprise"):
        config_from_dict({**canonical, "surprise": 1})


@pytest.mark.parametrize(
    "change",
    [
        {"tier_great_limit_ms": 600},
        {"tier_ok_limit_ms": 2200},
        {"tier_perfect_pct": 101},
        {"tier_early_pct": -1},
        {"min_accuracy_pct": 1001},
        {"base_points_per_char": 0},
        {"base_points_per_char": 101},
        {"combo_step_words": 0},
        {"combo_step_words": 1_000_001},
        {"combo_cap_pct": 1001},
        {"rank_a_pct": 90},
        {"rank_c_pct": 55},
        {"lead_in_ms": 3_600_001},
        {"max_line_window_ms": -1},
        {"max_typed_chars": 0},
        {"max_typed_chars": 65},
        {"line_bonus": -1},
        {"lead_in_ms": 1.5},
        {"lead_in_ms": True},
        {"default_case_insensitive": 1},
    ],
)
def test_invalid_configuration_raises(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        replace(DEFAULT_CONFIG, **change)


@pytest.mark.parametrize(
    "change",
    [
        {"base_points_per_char": 1},
        {"base_points_per_char": 100},
        {"combo_step_words": 1_000_000},
        {"max_typed_chars": 1},
        {"lead_in_ms": 3_600_000},
        {"tier_early_pct": 0},
        {"default_accent_insensitive": False},
    ],
)
def test_boundary_values_are_valid(change: dict[str, Any]) -> None:
    assert replace(DEFAULT_CONFIG, **change) is not None

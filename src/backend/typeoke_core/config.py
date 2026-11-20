"""Scoring configuration: the constants of section 2 of ``docs/scoring.md``.

An invalid configuration is a programming error and raises ``ValueError``; it is never a
rejection of a play (decision D20).
"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields

MAX_JSON_INT = 9007199254740991

_MAX_MS = 3_600_000
_MAX_PCT = 1000
_MAX_BASE_POINTS_PER_CHAR = 100
_MAX_COMBO_STEP_WORDS = 1_000_000
_MAX_TYPED_CHARS_LIMIT = 64

_MS_KEYS = (
    "lead_in_ms",
    "miss_window_ms",
    "tier_perfect_limit_ms",
    "tier_great_limit_ms",
    "tier_good_limit_ms",
    "tier_ok_limit_ms",
    "max_line_window_ms",
    "last_line_window_ms",
)
_TIER_PCT_KEYS = (
    "tier_perfect_pct",
    "tier_great_pct",
    "tier_good_pct",
    "tier_ok_pct",
    "tier_early_pct",
)
_OTHER_PCT_KEYS = (
    "min_accuracy_pct",
    "base_points_per_char",
    "combo_base_pct",
    "combo_step_pct",
    "combo_cap_pct",
    "combo_accuracy_pct",
    "rank_s_pct",
    "rank_a_pct",
    "rank_b_pct",
    "rank_c_pct",
    "expected_time_pct",
)
_BOOL_KEYS = ("default_accent_insensitive", "default_case_insensitive")


@dataclass(frozen=True, slots=True)
class ScoringConfig:
    """Every constant of the scoring rules, in the order of the table of section 2."""

    lead_in_ms: int = 1500
    miss_window_ms: int = 3500
    min_accuracy_pct: int = 60
    tier_perfect_limit_ms: int = 600
    tier_great_limit_ms: int = 1200
    tier_good_limit_ms: int = 2200
    tier_ok_limit_ms: int = 3500
    tier_perfect_pct: int = 100
    tier_great_pct: int = 80
    tier_good_pct: int = 55
    tier_ok_pct: int = 30
    tier_early_pct: int = 10
    base_points_per_char: int = 10
    combo_base_pct: int = 100
    combo_step_words: int = 10
    combo_step_pct: int = 25
    combo_cap_pct: int = 200
    combo_accuracy_pct: int = 80
    line_bonus: int = 50
    default_accent_insensitive: bool = True
    default_case_insensitive: bool = True
    rank_s_pct: int = 90
    rank_a_pct: int = 75
    rank_b_pct: int = 55
    rank_c_pct: int = 35
    expected_time_pct: int = 90
    max_line_window_ms: int = 6000
    last_line_window_ms: int = 5000
    max_typed_chars: int = 64

    def __post_init__(self) -> None:
        values = asdict(self)
        for key in _BOOL_KEYS:
            if type(values[key]) is not bool:
                raise ValueError(f"{key} must be a boolean")
        for key, value in values.items():
            if key not in _BOOL_KEYS and not _is_int(value):
                raise ValueError(f"{key} must be an integer")
        _check_ranges(self)


def _is_int(value: object) -> bool:
    return type(value) is int


def _check_ranges(config: ScoringConfig) -> None:
    values = asdict(config)
    for key in _MS_KEYS:
        _require(0 <= values[key] <= _MAX_MS, f"{key} must be between 0 and {_MAX_MS}")
    for key in _TIER_PCT_KEYS:
        _require(0 <= values[key] <= 100, f"{key} must be between 0 and 100")
    for key in _OTHER_PCT_KEYS:
        _require(0 <= values[key] <= _MAX_PCT, f"{key} must be between 0 and {_MAX_PCT}")
    _require(
        config.tier_perfect_limit_ms
        < config.tier_great_limit_ms
        < config.tier_good_limit_ms
        < config.tier_ok_limit_ms,
        "the tier limits must be strictly increasing",
    )
    _require(
        config.rank_s_pct > config.rank_a_pct > config.rank_b_pct > config.rank_c_pct,
        "the rank percentages must strictly decrease from S to C",
    )
    _require(
        1 <= config.base_points_per_char <= _MAX_BASE_POINTS_PER_CHAR,
        f"base_points_per_char must be between 1 and {_MAX_BASE_POINTS_PER_CHAR}",
    )
    _require(
        1 <= config.combo_step_words <= _MAX_COMBO_STEP_WORDS,
        f"combo_step_words must be between 1 and {_MAX_COMBO_STEP_WORDS}",
    )
    _require(
        1 <= config.max_typed_chars <= _MAX_TYPED_CHARS_LIMIT,
        f"max_typed_chars must be between 1 and {_MAX_TYPED_CHARS_LIMIT}",
    )
    _require(
        0 <= config.line_bonus <= MAX_JSON_INT,
        f"line_bonus must be between 0 and {MAX_JSON_INT}",
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


DEFAULT_CONFIG = ScoringConfig()


def config_to_dict(config: ScoringConfig) -> dict[str, int | bool]:
    """Flat JSON object of a configuration, keys in the order of section 2."""
    return asdict(config)


def config_from_dict(data: Mapping[str, object]) -> ScoringConfig:
    """Build a configuration from a flat object with exactly the keys of section 2."""
    expected = [field.name for field in fields(ScoringConfig)]
    if set(data) != set(expected):
        missing = sorted(set(expected) - set(data))
        extra = sorted(set(data) - set(expected))
        raise ValueError(f"configuration keys differ: missing {missing}, unexpected {extra}")
    return ScoringConfig(**data)  # type: ignore[arg-type]

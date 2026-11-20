"""Data shapes of the scoring rules and their strict JSON parsing.

The shapes are those of sections 14 to 16 of ``docs/scoring.md``. A malformed event log or
play settings value is a rejection (returned as a value, never raised); a timeline, a result
or a rejection that does not have the documented shape is a caller error and raises
``ValueError``. Nothing here reads a file.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import NoReturn, TypeGuard

from typeoke_core.config import MAX_JSON_INT, ScoringConfig

_SURROGATES = range(0xD800, 0xE000)


class RejectionReason(StrEnum):
    """The four reasons a play is rejected (section 15.5)."""

    MALFORMED_PLAY_SETTINGS = "MALFORMED_PLAY_SETTINGS"
    MALFORMED_EVENT_LOG = "MALFORMED_EVENT_LOG"
    NON_MONOTONIC_TIME = "NON_MONOTONIC_TIME"
    INCONSISTENT_WORD_INDEX = "INCONSISTENT_WORD_INDEX"


class Tier(StrEnum):
    """Timing tier of a word result (section 7)."""

    PERFECT = "PERFECT"
    GREAT = "GREAT"
    GOOD = "GOOD"
    OK = "OK"
    EARLY = "EARLY"
    MISS = "MISS"


class Rank(StrEnum):
    """Rank letter of a play (section 14.4)."""

    S = "S"
    A = "A"
    B = "B"
    C = "C"
    D = "D"


@dataclass(frozen=True, slots=True)
class Rejection:
    """A rejected play: no score, the reason and the 0-based index of the offending event."""

    reason: RejectionReason
    event_index: int | None


@dataclass(frozen=True, slots=True)
class PlaySettings:
    """Comparison options chosen by the player before a play (section 15.6)."""

    accent_insensitive: bool
    case_insensitive: bool


@dataclass(frozen=True, slots=True)
class Commit:
    """A typed word committed at playhead ``t`` for the word with global index ``word``."""

    t: int
    word: int
    text: str


@dataclass(frozen=True, slots=True)
class Pause:
    """The game paused at playhead ``t``."""

    t: int


@dataclass(frozen=True, slots=True)
class Resume:
    """The game resumed at playhead ``t``."""

    t: int


@dataclass(frozen=True, slots=True)
class Seek:
    """A jump: ``t`` is the playhead after it and ``from_ms`` the playhead before it."""

    t: int
    from_ms: int


Event = Commit | Pause | Resume | Seek


@dataclass(frozen=True, slots=True)
class Word:
    """A timeline word; ``expected_ms`` is ``None`` when it normalizes to empty."""

    text: str
    expected_ms: int | None


@dataclass(frozen=True, slots=True)
class Line:
    """A timeline line with its window and words (empty for an empty line)."""

    start_ms: int
    end_ms: int
    text: str
    words: tuple[Word, ...]


@dataclass(frozen=True, slots=True)
class Timeline:
    """The song timeline given to the scoring (section 16)."""

    lines: tuple[Line, ...]

    @property
    def word_count(self) -> int:
        """Number of words of the timeline, scorable or not."""
        return sum(len(line.words) for line in self.lines)


@dataclass(frozen=True, slots=True)
class Accuracy:
    """Accuracy of a word as an unreduced fraction ``num / den`` (section 4)."""

    num: int
    den: int


@dataclass(frozen=True, slots=True)
class WordResult:
    """Result of one scorable word."""

    word: int
    tier: Tier
    accuracy: Accuracy
    points: int


@dataclass(frozen=True, slots=True)
class LineResult:
    """Points and bonus of one line, with the results of its scorable words."""

    line: int
    points: int
    bonus: int
    words: tuple[WordResult, ...]


@dataclass(frozen=True, slots=True)
class PlayResult:
    """The result of a replayed play (section 14.5)."""

    settings: PlaySettings
    score: int
    accuracy_bp: int
    hit_rate_bp: int
    max_combo: int
    rank: Rank
    seeked: bool
    scorable_words: int
    hit_words: int
    max_base_score: int
    lines: tuple[LineResult, ...]


def is_valid_int(value: object) -> TypeGuard[int]:
    """Integer validity of section 1.5, on a decoded value: ``int`` (not bool), 0 to 2^53 - 1."""
    return type(value) is int and 0 <= value <= MAX_JSON_INT


def _reject_constant(name: str) -> NoReturn:
    raise ValueError(f"JSON constant {name} is not allowed")


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def decode_json(text: str) -> object:
    """Canonical decoder of section 1.5: no NaN or Infinity, no duplicate keys.

    Raises ``ValueError`` (``json.JSONDecodeError`` is one) on invalid input.
    """
    return json.loads(text, parse_constant=_reject_constant, object_pairs_hook=_reject_duplicates)


# ---------------------------------------------------------------- play settings

_SETTINGS_KEYS = frozenset({"accent_insensitive", "case_insensitive"})


def parse_play_settings(value: object) -> PlaySettings | Rejection:
    """Strict parse of section 15.6; malformed gives ``MALFORMED_PLAY_SETTINGS``, no index."""
    if not isinstance(value, dict) or set(value) != _SETTINGS_KEYS:
        return _malformed_settings()
    accent = value["accent_insensitive"]
    case = value["case_insensitive"]
    if type(accent) is not bool or type(case) is not bool:
        return _malformed_settings()
    return PlaySettings(accent_insensitive=accent, case_insensitive=case)


def _malformed_settings() -> Rejection:
    return Rejection(RejectionReason.MALFORMED_PLAY_SETTINGS, None)


def play_settings_to_json(settings: PlaySettings) -> dict[str, bool]:
    """JSON object of the play settings."""
    return {
        "accent_insensitive": settings.accent_insensitive,
        "case_insensitive": settings.case_insensitive,
    }


# -------------------------------------------------------------------- event log

_EVENT_KEYS: dict[str, frozenset[str]] = {
    "commit": frozenset({"type", "t", "word", "text"}),
    "pause": frozenset({"type", "t"}),
    "resume": frozenset({"type", "t"}),
    "seek": frozenset({"type", "t", "from"}),
}


def parse_event_log(
    value: object, word_count: int, config: ScoringConfig
) -> tuple[Event, ...] | Rejection:
    """Strict parse of an event log (sections 15.1 and 15.2).

    Every event is checked before any replay; the first malformed one gives
    ``MALFORMED_EVENT_LOG`` with its index, and a value that is not an array gives it with no
    index. ``word_count`` is the number of words of the timeline.
    """
    if not isinstance(value, list):
        return Rejection(RejectionReason.MALFORMED_EVENT_LOG, None)
    events: list[Event] = []
    for index, raw in enumerate(value):
        event = _parse_event(raw, word_count, config.max_typed_chars)
        if event is None:
            return Rejection(RejectionReason.MALFORMED_EVENT_LOG, index)
        events.append(event)
    return tuple(events)


def _parse_event(raw: object, word_count: int, max_typed_chars: int) -> Event | None:
    if not isinstance(raw, dict):
        return None
    kind = raw.get("type")
    if not isinstance(kind, str) or kind not in _EVENT_KEYS or set(raw) != _EVENT_KEYS[kind]:
        return None
    t = raw["t"]
    if not is_valid_int(t):
        return None
    if kind == "pause":
        return Pause(t)
    if kind == "resume":
        return Resume(t)
    if kind == "seek":
        origin = raw["from"]
        return Seek(t, origin) if is_valid_int(origin) else None
    word = raw["word"]
    text = raw["text"]
    if not is_valid_int(word) or word >= word_count:
        return None
    if not _is_valid_typed_text(text, max_typed_chars):
        return None
    return Commit(t, word, text)


def _is_valid_typed_text(text: object, max_typed_chars: int) -> bool:
    if not isinstance(text, str) or not 1 <= len(text) <= max_typed_chars:
        return False
    return not any(ord(char) in _SURROGATES for char in text)


def event_to_json(event: Event) -> dict[str, object]:
    """JSON object of one event."""
    match event:
        case Commit(t=t, word=word, text=text):
            return {"type": "commit", "t": t, "word": word, "text": text}
        case Pause(t=t):
            return {"type": "pause", "t": t}
        case Resume(t=t):
            return {"type": "resume", "t": t}
        case Seek(t=t, from_ms=origin):
            return {"type": "seek", "t": t, "from": origin}


def event_log_to_json(events: tuple[Event, ...]) -> list[dict[str, object]]:
    """JSON array of an event log."""
    return [event_to_json(event) for event in events]


# -------------------------------------------------------------------- rejection


def rejection_to_json(rejection: Rejection) -> dict[str, object]:
    """JSON object of a rejection (section 15.5)."""
    return {"reason": rejection.reason.value, "event_index": rejection.event_index}


def rejection_from_json(value: object) -> Rejection:
    """Parse the JSON object of a rejection; raises ``ValueError`` on any other shape."""
    data = _exact_object(value, {"reason", "event_index"}, "rejection")
    reason = data["reason"]
    index = data["event_index"]
    if not isinstance(reason, str) or reason not in RejectionReason:
        raise ValueError("rejection reason is not one of the four reasons")
    if index is not None and not is_valid_int(index):
        raise ValueError("rejection event_index must be an integer or null")
    return Rejection(RejectionReason(reason), index if isinstance(index, int) else None)


# --------------------------------------------------------------------- timeline


def timeline_from_json(value: object) -> Timeline:
    """Parse a timeline (section 16); raises ``ValueError`` when it breaks its preconditions.

    Checked here: the shape, integer times, ``end_ms >= start_ms``, non-decreasing line starts
    and non-decreasing expected times of the scorable words. The length limit of expected
    words needs the normalization and belongs to the scoring.
    """
    data = _exact_object(value, {"lines"}, "timeline")
    raw_lines = data["lines"]
    if not isinstance(raw_lines, list):
        raise ValueError("timeline lines must be an array")
    lines = tuple(_line_from_json(raw) for raw in raw_lines)
    starts = [line.start_ms for line in lines]
    if starts != sorted(starts):
        raise ValueError("line starts must not decrease")
    times = [w.expected_ms for line in lines for w in line.words if w.expected_ms is not None]
    if times != sorted(times):
        raise ValueError("expected times must not decrease in word order")
    return Timeline(lines)


def _line_from_json(value: object) -> Line:
    data = _exact_object(value, {"start_ms", "end_ms", "text", "words"}, "line")
    start = _int(data["start_ms"], "start_ms")
    end = _int(data["end_ms"], "end_ms")
    text = data["text"]
    raw_words = data["words"]
    if end < start:
        raise ValueError("end_ms must not be below start_ms")
    if not isinstance(text, str):
        raise ValueError("line text must be a string")
    if not isinstance(raw_words, list):
        raise ValueError("line words must be an array")
    return Line(start, end, text, tuple(_word_from_json(raw) for raw in raw_words))


def _word_from_json(value: object) -> Word:
    data = _exact_object(value, {"text", "expected_ms"}, "word")
    text = data["text"]
    expected = data["expected_ms"]
    if not isinstance(text, str) or not text:
        raise ValueError("word text must be a non-empty string")
    if expected is not None:
        expected = _int(expected, "expected_ms")
    return Word(text, expected if isinstance(expected, int) else None)


def timeline_to_json(timeline: Timeline) -> dict[str, object]:
    """JSON object of a timeline."""
    return {
        "lines": [
            {
                "start_ms": line.start_ms,
                "end_ms": line.end_ms,
                "text": line.text,
                "words": [{"text": w.text, "expected_ms": w.expected_ms} for w in line.words],
            }
            for line in timeline.lines
        ]
    }


# ------------------------------------------------------------------ play result

_RESULT_KEYS = {
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
}


def result_to_json(result: PlayResult) -> dict[str, object]:
    """JSON object of a play result (section 14.5)."""
    return {
        "settings": play_settings_to_json(result.settings),
        "score": result.score,
        "accuracy_bp": result.accuracy_bp,
        "hit_rate_bp": result.hit_rate_bp,
        "max_combo": result.max_combo,
        "rank": result.rank.value,
        "seeked": result.seeked,
        "scorable_words": result.scorable_words,
        "hit_words": result.hit_words,
        "max_base_score": result.max_base_score,
        "lines": [_line_result_to_json(line) for line in result.lines],
    }


def _line_result_to_json(line: LineResult) -> dict[str, object]:
    return {
        "line": line.line,
        "points": line.points,
        "bonus": line.bonus,
        "words": [
            {
                "word": w.word,
                "tier": w.tier.value,
                "accuracy": {"num": w.accuracy.num, "den": w.accuracy.den},
                "points": w.points,
            }
            for w in line.words
        ],
    }


def result_from_json(value: object) -> PlayResult:
    """Parse a play result; raises ``ValueError`` on any other shape."""
    data = _exact_object(value, _RESULT_KEYS, "result")
    settings = parse_play_settings(data["settings"])
    if isinstance(settings, Rejection):
        raise ValueError("result settings are malformed")
    rank = data["rank"]
    seeked = data["seeked"]
    raw_lines = data["lines"]
    if not isinstance(rank, str) or rank not in Rank:
        raise ValueError("result rank must be S, A, B, C or D")
    if type(seeked) is not bool:
        raise ValueError("result seeked must be a boolean")
    if not isinstance(raw_lines, list):
        raise ValueError("result lines must be an array")
    return PlayResult(
        settings=settings,
        score=_int(data["score"], "score"),
        accuracy_bp=_int(data["accuracy_bp"], "accuracy_bp"),
        hit_rate_bp=_int(data["hit_rate_bp"], "hit_rate_bp"),
        max_combo=_int(data["max_combo"], "max_combo"),
        rank=Rank(rank),
        seeked=seeked,
        scorable_words=_int(data["scorable_words"], "scorable_words"),
        hit_words=_int(data["hit_words"], "hit_words"),
        max_base_score=_int(data["max_base_score"], "max_base_score"),
        lines=tuple(_line_result_from_json(raw) for raw in raw_lines),
    )


def _line_result_from_json(value: object) -> LineResult:
    data = _exact_object(value, {"line", "points", "bonus", "words"}, "line result")
    raw_words = data["words"]
    if not isinstance(raw_words, list):
        raise ValueError("line result words must be an array")
    return LineResult(
        line=_int(data["line"], "line"),
        points=_int(data["points"], "points"),
        bonus=_int(data["bonus"], "bonus"),
        words=tuple(_word_result_from_json(raw) for raw in raw_words),
    )


def _word_result_from_json(value: object) -> WordResult:
    data = _exact_object(value, {"word", "tier", "accuracy", "points"}, "word result")
    tier = data["tier"]
    if not isinstance(tier, str) or tier not in Tier:
        raise ValueError("word tier is not a known tier")
    accuracy = _exact_object(data["accuracy"], {"num", "den"}, "accuracy")
    return WordResult(
        word=_int(data["word"], "word"),
        tier=Tier(tier),
        accuracy=Accuracy(_int(accuracy["num"], "num"), _int(accuracy["den"], "den")),
        points=_int(data["points"], "points"),
    )


# ---------------------------------------------------------------------- helpers


def _exact_object(value: object, keys: set[str], what: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{what} must be an object with exactly the keys {sorted(keys)}")
    return value


def _int(value: object, what: str) -> int:
    if not is_valid_int(value):
        raise ValueError(f"{what} must be an integer from 0 to {MAX_JSON_INT}")
    return value

"""Golden vector runner (section 17 of docs/scoring.md), Python side.

Every file of ``testdata/scoring/vectors/`` is decoded with the canonical decoder, validated
against ``testdata/scoring/vector.schema.json``, checked against ``config.json`` (the vector
configuration must equal the canonical one with the declared overrides applied), scored with
``score_play`` and compared field by field with the expected result or rejection. For a vector
whose play settings are not both on, the *twin* is the same timeline, event log and
configuration scored with both options on (computed, never stored): no word of the vector may
have more accuracy or points, and the play may not have a larger score, than the twin (6.11).

The outcome of every vector is written to ``build/vector-report-python.json`` at the
repository root, for the parity check of task 4.4. Reading files is allowed in tests; the
``typeoke_core`` package itself never does it.
"""

import functools
import json
import os
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import jsonschema  # type: ignore[import-untyped]
import pytest

from typeoke_core.config import config_from_dict
from typeoke_core.models import (
    PlayResult,
    PlaySettings,
    Rejection,
    decode_json,
    rejection_to_json,
    result_from_json,
    result_to_json,
    timeline_from_json,
)
from typeoke_core.scoring import score_play

ROOT = Path(__file__).resolve().parents[3]
SCORING_DIR = ROOT / "testdata" / "scoring"
VECTOR_DIR = SCORING_DIR / "vectors"
REPORT_PATH = ROOT / "build" / "vector-report-python.json"
BOTH_ON = PlaySettings(accent_insensitive=True, case_insensitive=True)
BOTH_ON_JSON = {"accent_insensitive": True, "case_insensitive": True}

Problems = list[str]


def _read_json(path: Path) -> Any:
    return decode_json(path.read_text(encoding="utf-8"))


CANONICAL: dict[str, Any] = _read_json(SCORING_DIR / "config.json")
SCHEMA: dict[str, Any] = _read_json(SCORING_DIR / "vector.schema.json")
VECTOR_PATHS = sorted(VECTOR_DIR.glob("*.json"))


# ------------------------------------------------------------------------------ decoding


def _find_float(value: object, where: str = "$") -> str | None:
    """Path of the first float in a decoded value: vectors hold integers only (D22)."""
    if isinstance(value, float):
        return where
    if isinstance(value, dict):
        children = [(f"{where}.{key}", item) for key, item in value.items()]
    elif isinstance(value, list):
        children = [(f"{where}[{index}]", item) for index, item in enumerate(value)]
    else:
        return None
    for child_where, child in children:
        found = _find_float(child, child_where)
        if found is not None:
            return found
    return None


def decode_vector_text(text: str) -> dict[str, Any]:
    """Canonical decoding of a vector file; raises ``ValueError`` on anything but strict JSON."""
    value = decode_json(text)
    if not isinstance(value, dict):
        raise ValueError("a vector must be a JSON object")
    where = _find_float(value)
    if where is not None:
        raise ValueError(f"a vector never contains a fraction or an exponent: {where}")
    return value


# ------------------------------------------------------------------------------- checking


def schema_problems(doc: object) -> Problems:
    """Every violation of the vector schema, as readable lines."""
    validator = jsonschema.Draft202012Validator(SCHEMA)
    return [
        f"schema: {_location(error.absolute_path)}: {error.message[:160]}"
        for error in validator.iter_errors(doc)
    ]


def _location(path: Iterable[str | int]) -> str:
    return "/".join(str(part) for part in path) or "$"


def _differences(expected: object, actual: object, where: str = "$") -> Problems:
    """Paths where two JSON values differ; a bool never equals an int."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        found: Problems = []
        for key in sorted(set(expected) | set(actual)):
            if key not in expected or key not in actual:
                found.append(f"{where}.{key}: present on one side only")
            else:
                found += _differences(expected[key], actual[key], f"{where}.{key}")
        return found
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return [f"{where}: {len(expected)} items expected, {len(actual)} found"]
        found = []
        for index, (left, right) in enumerate(zip(expected, actual, strict=True)):
            found += _differences(left, right, f"{where}[{index}]")
        return found
    if type(expected) is not type(actual) or expected != actual:
        return [f"{where}: expected {expected!r}, found {actual!r}"]
    return []


def config_problems(doc: dict[str, Any]) -> Problems:
    """The vector configuration must equal the canonical one with the overrides applied."""
    config, overrides = doc["config"], doc["overrides"]
    problems = [
        f"overrides.{key} repeats the canonical value {value!r}"
        for key, value in overrides.items()
        if CANONICAL.get(key) == value and type(CANONICAL.get(key)) is type(value)
    ]
    problems += [
        f"overrides.{key} is not a configuration key" for key in overrides if key not in CANONICAL
    ]
    expected_config = {**CANONICAL, **overrides}
    return problems + _differences(expected_config, config, "config")


def _twin_problems(doc: dict[str, Any], own: PlayResult) -> Problems:
    """Property of section 17: no option raises accuracy, points or score above both-on."""
    if own.settings == BOTH_ON:
        return []
    timeline = timeline_from_json(doc["timeline"])
    twin = score_play(timeline, BOTH_ON_JSON, doc["events"], config_from_dict(doc["config"]))
    if isinstance(twin, Rejection):
        return [f"twin with both options on is rejected: {twin.reason}"]
    problems: Problems = []
    if (own.max_base_score, own.scorable_words) != (twin.max_base_score, twin.scorable_words):
        problems.append("twin: max_base_score or scorable_words depends on the play settings")
    if own.score > twin.score:
        problems.append(f"twin: score {own.score} is above the both-on score {twin.score}")
    own_words = [word for line in own.lines for word in line.words]
    twin_words = [word for line in twin.lines for word in line.words]
    for mine, theirs in zip(own_words, twin_words, strict=True):
        if mine.accuracy.num * theirs.accuracy.den > theirs.accuracy.num * mine.accuracy.den:
            problems.append(f"twin: word {mine.word} has more accuracy than with both options on")
        if mine.points > theirs.points:
            problems.append(f"twin: word {mine.word} has more points than with both options on")
    return problems


def scoring_problems(doc: dict[str, Any]) -> Problems:
    """Score the vector and compare every field of the result or of the rejection."""
    try:
        timeline = timeline_from_json(doc["timeline"])
        config = config_from_dict(doc["config"])
    except ValueError as error:
        return [f"timeline or configuration is not valid: {error}"]
    outcome = score_play(timeline, doc["settings"], doc["events"], config)
    expected = doc["expected"]
    if isinstance(outcome, Rejection):
        if "rejection" not in expected:
            return [f"rejected as {outcome.reason} at {outcome.event_index}, a result was expected"]
        return _differences(expected["rejection"], rejection_to_json(outcome), "rejection")
    if "result" not in expected:
        return ["scored, a rejection was expected"]
    problems = _differences(expected["result"], result_to_json(outcome), "result")
    return problems or _twin_problems(doc, result_from_json(expected["result"]))


def document_problems(name: str, doc: dict[str, Any]) -> Problems:
    """All checks of one decoded vector; stops after the schema when the shape is wrong."""
    problems = schema_problems(doc)
    if problems:
        return problems
    if doc["name"] != name:
        problems.append(f"name {doc['name']!r} differs from the file name {name!r}")
    return problems + config_problems(doc) + scoring_problems(doc)


def vector_problems(path: Path) -> Problems:
    """All checks of one vector file."""
    try:
        doc = decode_vector_text(path.read_text(encoding="utf-8"))
    except ValueError as error:
        return [f"file is not a valid vector: {error}"]
    return document_problems(path.stem, doc)


@functools.cache
def run_all() -> dict[str, Problems]:
    """Run every vector once and write the report for task 4.4 (also when some fail)."""
    outcomes = {path.stem: vector_problems(path) for path in VECTOR_PATHS}
    report = {
        "runner": "python",
        "vectors": [{"name": name, "passed": not found} for name, found in outcomes.items()],
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(report, indent=2) + "\n")
    return outcomes


# ------------------------------------------------------------------------------ the tests


@pytest.mark.parametrize("name", [path.stem for path in VECTOR_PATHS])
def test_vector(name: str) -> None:
    assert run_all()[name] == []


def test_every_vector_file_is_executed_once() -> None:
    run_all()
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    names = [entry["name"] for entry in report["vectors"]]
    on_disk = sorted(
        name[: -len(".json")] for name in os.listdir(VECTOR_DIR) if name.endswith(".json")
    )
    assert names == on_disk
    assert len(names) > 0
    assert len(names) == len(set(names))
    assert all(entry["passed"] for entry in report["vectors"])


def test_schema_is_a_valid_draft_2020_12_schema() -> None:
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


def test_the_two_aeib_vectors_have_the_same_scores() -> None:
    off = _read_json(VECTOR_DIR / "lower-of-aeib-accent-off.json")
    default = _read_json(VECTOR_DIR / "lower-of-aeib-default.json")
    assert off["timeline"] == default["timeline"]
    assert off["events"] == default["events"]
    assert off["settings"]["accent_insensitive"] is False
    assert off["expected"]["result"]["lines"] == default["expected"]["result"]["lines"]
    word = off["expected"]["result"]["lines"][0]["words"][0]
    assert (word["accuracy"], word["points"]) == ({"num": 3, "den": 4}, 30)


# ----------------------------------------------------- the checks themselves catch mistakes


def _vector(name: str) -> dict[str, Any]:
    return decode_vector_text((VECTOR_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _sample() -> dict[str, Any]:
    doc = _vector("worked-play-section-14-6")
    assert document_problems("worked-play-section-14-6", doc) == []
    return doc


def _sample_rejection() -> dict[str, Any]:
    return _vector("reject-non-monotonic-time")


def _set(path: list[str | int], value: object) -> Callable[[dict[str, Any]], None]:
    def mutate(doc: dict[str, Any]) -> None:
        target: Any = doc
        for part in path[:-1]:
            target = target[part]
        target[path[-1]] = value

    return mutate


def _delete(path: list[str | int]) -> Callable[[dict[str, Any]], None]:
    def mutate(doc: dict[str, Any]) -> None:
        target: Any = doc
        for part in path[:-1]:
            target = target[part]
        del target[path[-1]]

    return mutate


SCHEMA_MUTATIONS: dict[str, Callable[[dict[str, Any]], None]] = {
    "unknown top-level field": _set(["extra"], 1),
    "missing field": _delete(["description"]),
    "unknown field in the result": _set(["expected", "result", "extra"], 1),
    "unknown field in a word": _set(["expected", "result", "lines", 0, "words", 0, "extra"], 1),
    "unknown config key": _set(["config", "locale"], 1),
    "missing config key": _delete(["config", "line_bonus"]),
    "default flag in overrides": _set(["overrides", "default_accent_insensitive"], False),
    "string where an integer is expected": _set(["expected", "result", "score"], "175"),
    "float where an integer is expected": _set(["expected", "result", "score"], 175.5),
    "boolean where an integer is expected": _set(["expected", "result", "max_combo"], True),
    "integer where a boolean is expected": _set(["expected", "result", "seeked"], 0),
    "boolean config value as an integer": _set(["config", "line_bonus"], False),
    "negative time in the timeline": _set(["timeline", "lines", 0, "start_ms"], -1),
    "unknown rank": _set(["expected", "result", "rank"], "E"),
    "unknown tier": _set(["expected", "result", "lines", 0, "words", 0, "tier"], "GREATEST"),
    "events not an array": _set(["events"], {}),
    "name with capital letters": _set(["name"], "Worked-Play"),
    "both result and rejection expected": _set(
        ["expected", "rejection"], {"reason": "NON_MONOTONIC_TIME", "event_index": 0}
    ),
    "malformed settings next to a result": _set(["settings"], {"accent_insensitive": True}),
    "missing settings": _delete(["settings"]),
    "word text with a space": _set(["timeline", "lines", 0, "words", 0, "text"], "two words"),
    "word text with a no-break space": _set(
        ["timeline", "lines", 0, "words", 0, "text"], "a\u00a0b"
    ),
    "empty word text": _set(["timeline", "lines", 0, "words", 0, "text"], ""),
}


@pytest.mark.parametrize("mutation", sorted(SCHEMA_MUTATIONS))
def test_schema_rejects_mutated_vector(mutation: str) -> None:
    doc = _sample()
    SCHEMA_MUTATIONS[mutation](doc)
    assert schema_problems(doc) != []


def test_schema_accepts_any_json_value_for_malformed_settings_and_events() -> None:
    doc = _sample_rejection()
    doc["settings"] = {"accent_insensitive": 1}
    doc["events"] = [5, "x", None, {"type": 1}]
    assert schema_problems(doc) == []


@pytest.mark.parametrize(
    ("reason", "index", "valid"),
    [
        ("MALFORMED_PLAY_SETTINGS", None, True),
        ("MALFORMED_PLAY_SETTINGS", 0, False),
        ("MALFORMED_EVENT_LOG", 3, True),
        ("MALFORMED_EVENT_LOG", None, False),
        ("NON_MONOTONIC_TIME", None, False),
        ("INCONSISTENT_WORD_INDEX", 0, True),
    ],
)
def test_schema_ties_the_null_index_to_the_settings_reason(
    reason: str, index: int | None, valid: bool
) -> None:
    doc = _sample_rejection()
    doc["expected"]["rejection"] = {"reason": reason, "event_index": index}
    assert (schema_problems(doc) == []) is valid


def test_schema_rejects_a_rejection_with_an_extra_field() -> None:
    doc = _sample_rejection()
    doc["expected"]["rejection"]["extra"] = 1
    assert schema_problems(doc) != []


@pytest.mark.parametrize(
    "text",
    [
        '{"a": NaN}',
        '{"a": Infinity}',
        '{"a": -Infinity}',
        '{"a": 1, "a": 2}',
        '{"a": 1.5}',
        '{"a": [1.0]}',
        '{"a": 1e2}',
        "[1]",
        "{",
    ],
)
def test_decoder_rejects_what_a_vector_may_not_contain(text: str) -> None:
    with pytest.raises(ValueError, match=r".+"):
        decode_vector_text(text)


def test_changing_an_expected_value_fails_the_vector() -> None:
    doc = _sample()
    doc["expected"]["result"]["lines"][1]["words"][1]["points"] += 1
    problems = document_problems("worked-play-section-14-6", doc)
    assert problems == ["result.lines[1].words[1].points: expected 3, found 2"]


def test_changing_an_expected_rejection_fails_the_vector() -> None:
    doc = _sample_rejection()
    doc["expected"]["rejection"]["event_index"] = 0
    assert document_problems("reject-non-monotonic-time", doc) != []


def test_a_result_where_a_rejection_is_expected_fails() -> None:
    doc = _sample()
    doc["expected"] = {"rejection": {"reason": "NON_MONOTONIC_TIME", "event_index": 0}}
    assert document_problems("worked-play-section-14-6", doc) == [
        "scored, a rejection was expected"
    ]


def test_a_rejection_where_a_result_is_expected_fails() -> None:
    doc = _sample_rejection()
    doc["expected"] = {"result": _sample()["expected"]["result"]}
    problems = document_problems("reject-non-monotonic-time", doc)
    assert problems == ["rejected as NON_MONOTONIC_TIME at 1, a result was expected"]


def test_a_name_different_from_the_file_name_fails() -> None:
    assert document_problems("other-name", _sample()) == [
        "name 'worked-play-section-14-6' differs from the file name 'other-name'"
    ]


def test_configuration_must_equal_the_canonical_one_with_overrides() -> None:
    doc = _sample()
    doc["config"]["line_bonus"] = 60
    assert config_problems(doc) == ["config.line_bonus: expected 50, found 60"]
    doc["overrides"] = {"line_bonus": 60}
    assert config_problems(doc) == []


def test_an_override_that_repeats_the_canonical_value_fails() -> None:
    doc = _sample()
    doc["overrides"] = {"line_bonus": 50}
    assert config_problems(doc) == ["overrides.line_bonus repeats the canonical value 50"]


def test_an_override_of_an_unknown_key_fails() -> None:
    doc = _sample()
    doc["overrides"] = {"locale": 1}
    assert "overrides.locale is not a configuration key" in config_problems(doc)


def test_an_invalid_timeline_is_reported_not_raised() -> None:
    doc = _sample()
    doc["timeline"]["lines"][0]["end_ms"] = 1
    problems = scoring_problems(doc)
    assert len(problems) == 1 and problems[0].startswith("timeline or configuration is not valid")


def test_the_twin_property_flags_more_points_or_accuracy_than_both_on() -> None:
    doc = _vector("lower-of-aeib-accent-off")
    own = result_from_json(doc["expected"]["result"])
    assert _twin_problems(doc, own) == []
    word = own.lines[0].words[0]
    better = result_from_json(
        {
            **doc["expected"]["result"],
            "score": 31,
            "lines": [
                {
                    "line": 0,
                    "points": 31,
                    "bonus": 0,
                    "words": [
                        {
                            "word": 0,
                            "tier": "PERFECT",
                            "accuracy": {"num": 6, "den": 7},
                            "points": word.points + 1,
                        }
                    ],
                }
            ],
        }
    )
    assert _twin_problems(doc, better) == [
        "twin: score 31 is above the both-on score 30",
        "twin: word 0 has more accuracy than with both options on",
        "twin: word 0 has more points than with both options on",
    ]


def test_the_twin_property_flags_a_rejected_twin() -> None:
    doc = _vector("lower-of-aeib-accent-off")
    own = result_from_json(doc["expected"]["result"])
    doc["events"] = [{"type": "commit", "t": 10000, "word": 5, "text": "x"}]
    assert _twin_problems(doc, own) == [
        "twin with both options on is rejected: MALFORMED_EVENT_LOG"
    ]

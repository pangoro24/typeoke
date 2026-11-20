"""Expected time per word and line ends of ``docs/scoring.md`` (sections 6 and 16).

Pure functions on integers and strings: no clock, no randomness, no locale, no I/O. Only the
song normalization is used (never the play settings), so one timeline serves every play.
Input that breaks a precondition of section 16 is a caller error and raises ``ValueError``.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from typeoke_core.config import DEFAULT_CONFIG, MAX_JSON_INT, ScoringConfig
from typeoke_core.models import Line, PlaySettings, Timeline, Word, is_valid_int
from typeoke_core.scoring import normalize, round_half_up, song_normalize, split_words

MAX_EXPECTED_WORD_CHARS = 10000

# Longest form of a normalized word (section 1.6): accent option off, case option on.
_LONGEST_FORM = PlaySettings(accent_insensitive=False, case_insensitive=True)


@dataclass(frozen=True, slots=True)
class SourceLine:
    """A lyric line as a source gives it: its start and text, and optional word times.

    ``word_times`` holds one entry per word of the text (section 3.1). An integer is used as
    is for that word; ``None`` leaves the word to the rule of section 6.2. A time given for a
    word that is not scorable is ignored.
    """

    start_ms: int
    text: str
    word_times: Sequence[int | None] | None = None


def line_end_ms(starts: Sequence[int], index: int, config: ScoringConfig = DEFAULT_CONFIG) -> int:
    """End of line ``index`` (section 6.1): next start capped by the window, or the last window."""
    start = starts[index]
    if index < len(starts) - 1:
        return min(starts[index + 1], start + config.max_line_window_ms)
    return start + config.last_line_window_ms


def build_timeline(lines: Sequence[SourceLine], config: ScoringConfig = DEFAULT_CONFIG) -> Timeline:
    """Build the timeline of a song: line ends and the expected time of every scorable word.

    Raises ``ValueError`` when the input breaks a precondition of section 16: an invalid start
    or supplied time, starts that decrease, a word count that differs from the number of
    supplied times, an expected word of more than 10000 code points, or expected times that
    decrease in word order.
    """
    starts = [_checked_start(line) for line in lines]
    if starts != sorted(starts):
        raise ValueError("line starts must not decrease")
    built = tuple(
        _build_line(line, line_end_ms(starts, index, config), config)
        for index, line in enumerate(lines)
    )
    times = [w.expected_ms for line in built for w in line.words if w.expected_ms is not None]
    if times != sorted(times):
        raise ValueError("expected times must not decrease in word order")
    return Timeline(built)


def _checked_start(line: SourceLine) -> int:
    if not is_valid_int(line.start_ms):
        raise ValueError("line start must be an integer from 0 to 2^53 - 1")
    if not isinstance(line.text, str):
        raise ValueError("line text must be a string")
    return line.start_ms


def _build_line(line: SourceLine, end: int, config: ScoringConfig) -> Line:
    if end > MAX_JSON_INT:
        raise ValueError("line end must not exceed 2^53 - 1")
    texts = split_words(line.text)
    supplied = _supplied_times(line, len(texts))
    lengths = [len(song_normalize(text)) for text in texts]
    for text in texts:
        if len(normalize(text, _LONGEST_FORM)) > MAX_EXPECTED_WORD_CHARS:
            raise ValueError("an expected word has more than 10000 code points")
    total = sum(lengths)
    window = end - line.start_ms
    words: list[Word] = []
    through = 0
    for text, length, given in zip(texts, lengths, supplied, strict=True):
        through += length
        if length == 0:
            words.append(Word(text, None))
        elif given is not None:
            words.append(Word(text, given))
        else:
            offset = round_half_up(through * window * config.expected_time_pct, total * 100)
            words.append(Word(text, line.start_ms + offset))
    return Line(line.start_ms, end, line.text, tuple(words))


def _supplied_times(line: SourceLine, word_count: int) -> Sequence[int | None]:
    if line.word_times is None:
        return [None] * word_count
    if len(line.word_times) != word_count:
        raise ValueError("word_times must have one entry per word of the line")
    if not all(time is None or is_valid_int(time) for time in line.word_times):
        raise ValueError("a supplied word time must be an integer from 0 to 2^53 - 1 or None")
    return line.word_times

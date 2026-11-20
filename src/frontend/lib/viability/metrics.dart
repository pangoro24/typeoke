/// Pure measurement functions of the viability check (no browser, no Flutter).
library;

import 'dart:math' as math;

/// Key-to-paint latency: median limit in milliseconds (criterion 1.3).
const double keyLatencyMedianLimitMs = 33;

/// Key-to-paint latency: 95th percentile limit in milliseconds (criterion 1.3).
const double keyLatencyP95LimitMs = 50;

/// Minimum number of keystrokes for a reliable latency figure (criterion 1.3).
const int minLatencyKeystrokes = 500;

/// Burst typing speed in characters per second (criterion 1.4).
const int burstCharsPerSecond = 15;

/// Burst duration in seconds (criterion 1.4).
const int burstSeconds = 10;

/// Frame duration above which a frame counts as slow (criterion 1.5).
const double slowFrameMs = 50;

/// Minimum average frames per second (criterion 1.5).
const double minAverageFps = 50;

/// The share of slow frames must stay below this value (criterion 1.5).
const double maxSlowFrameShare = 0.01;

/// Minimum number of frames for a reliable frame figure (criterion 1.5).
const int minFrameSamples = 100;

/// Playhead drift: 95th percentile limit in milliseconds (criterion 1.6).
const double driftP95LimitMs = 50;

/// Playhead drift: maximum limit in milliseconds (criterion 1.6).
const double driftMaxLimitMs = 150;

/// Minimum number of drift samples for a reliable figure (criterion 1.6).
const int minDriftSamples = 100;

/// Pause, buffering and resume reaction limit in milliseconds (criterion 1.7).
const double stateReactionLimitMs = 250;

/// Seek detection limit in milliseconds (criterion 1.8).
const double seekReactionLimitMs = 500;

/// Smallest jump of the playhead that counts as a seek, in milliseconds.
const double seekMinJumpMs = 1500;

/// Hidden-tab pause limit in milliseconds (criterion 1.9).
const double hiddenTabLimitMs = 500;

/// Minimum player width in CSS pixels (criterion 1.10).
const double minPlayerWidthCss = 480;

/// Minimum player height in CSS pixels (criterion 1.10).
const double minPlayerHeightCss = 270;

/// Criteria that decide the verdict, in order.
const List<String> criterionIds = [
  '1.3',
  '1.4',
  '1.5',
  '1.6',
  '1.7',
  '1.8',
  '1.9',
  '1.10',
  '1.11',
  '1.12',
];

/// Browsers that must be measured (Assumption A1).
const List<String> requiredBrowsers = ['Chrome', 'Firefox'];

/// Median of [values], or null for an empty sample.
double? median(List<double> values) {
  if (values.isEmpty) return null;
  final sorted = [...values]..sort();
  final middle = sorted.length ~/ 2;
  if (sorted.length.isOdd) return sorted[middle];
  return (sorted[middle - 1] + sorted[middle]) / 2;
}

/// Nearest-rank percentile ([percent] in 0..100) of [values], or null if empty.
double? percentile(List<double> values, double percent) {
  if (values.isEmpty) return null;
  final sorted = [...values]..sort();
  final rank = math.max(1, (percent / 100 * sorted.length).ceil());
  return sorted[math.min(rank, sorted.length) - 1];
}

/// Share (0..1) of frames longer than [limitMs], or null for no frames.
double? slowFrameShare(List<double> frameMs, {double limitMs = slowFrameMs}) {
  if (frameMs.isEmpty) return null;
  final slow = frameMs.where((d) => d > limitMs).length;
  return slow / frameMs.length;
}

/// Average frames per second of consecutive frames, or null if there is no time.
double? averageFps(List<double> frameMs) {
  final total = frameMs.fold<double>(0, (sum, d) => sum + d);
  if (frameMs.isEmpty || total <= 0) return null;
  return 1000 * frameMs.length / total;
}

/// Drift statistics between two time series.
class DriftStats {
  /// Creates drift statistics.
  const DriftStats({required this.p95Ms, required this.maxMs});

  /// 95th percentile of the absolute differences.
  final double p95Ms;

  /// Largest absolute difference.
  final double maxMs;
}

/// Absolute differences between [game] and [reference] sampled at the same
/// instants; null for an empty sample. Throws if the lengths differ.
DriftStats? driftStats(List<double> game, List<double> reference) {
  if (game.length != reference.length) {
    throw ArgumentError('Series must have the same length');
  }
  if (game.isEmpty) return null;
  final diffs = [
    for (var i = 0; i < game.length; i++) (game[i] - reference[i]).abs(),
  ];
  return DriftStats(
    p95Ms: percentile(diffs, 95)!,
    maxMs: diffs.reduce(math.max),
  );
}

/// One reading taken on a fixed cadence.
typedef Sample = ({double timeMs, bool observed});

/// Reaction time: time of the first observed sample at or after the event
/// minus the event time; null when the reaction is never observed.
double? reactionTimeMs(double eventMs, List<Sample> samples) {
  for (final s in samples) {
    if (s.timeMs >= eventMs && s.observed) return s.timeMs - eventMs;
  }
  return null;
}

/// Comparison of the keystrokes sent with the keystrokes registered.
class KeystrokeIntegrity {
  /// Creates an integrity result.
  const KeystrokeIntegrity({
    required this.lost,
    required this.duplicated,
    required this.outOfOrder,
    required this.unexpected,
  });

  /// Sent keystrokes never registered.
  final int lost;

  /// Extra registrations of an already registered keystroke.
  final int duplicated;

  /// Registered keystrokes that arrived after a later one.
  final int outOfOrder;

  /// Registered ids that were never sent.
  final int unexpected;

  /// True when every keystroke was registered once, in order.
  bool get isClean =>
      lost == 0 && duplicated == 0 && outOfOrder == 0 && unexpected == 0;
}

/// Compares [sent] with [registered] (ids of the keystrokes, unique in [sent]).
KeystrokeIntegrity keystrokeIntegrity(List<int> sent, List<int> registered) {
  final position = {for (var i = 0; i < sent.length; i++) sent[i]: i};
  final seen = <int>{};
  var duplicated = 0;
  var unexpected = 0;
  var outOfOrder = 0;
  var highest = -1;
  for (final id in registered) {
    final index = position[id];
    if (index == null) {
      unexpected++;
    } else if (!seen.add(id)) {
      duplicated++;
    } else if (index < highest) {
      outOfOrder++;
    } else {
      highest = index;
    }
  }
  return KeystrokeIntegrity(
    lost: sent.length - seen.length,
    duplicated: duplicated,
    outOfOrder: outOfOrder,
    unexpected: unexpected,
  );
}

/// Outcome of one criterion on one browser.
enum Outcome {
  /// Measured reliably and within the limit.
  pass,

  /// Measured reliably and outside the limit.
  fail,

  /// Measured, but not reliably (for example too few samples).
  unreliable,

  /// Not measured.
  missing,
}

/// Overall verdict.
enum Verdict {
  /// Every criterion passed on every required browser.
  pass,

  /// At least one criterion failed.
  fail,

  /// No failure, but something is unreliable or missing.
  notPass,
}

/// Result of one criterion on one browser.
class CriterionResult {
  /// Creates a result.
  const CriterionResult({
    required this.id,
    required this.outcome,
    this.values = const {},
    this.threshold = '',
  });

  /// Criterion number, for example `1.3`.
  final String id;

  /// Outcome of the criterion.
  final Outcome outcome;

  /// Measured values by name.
  final Map<String, double> values;

  /// Human-readable threshold.
  final String threshold;

  /// Reads the JSON form written by [toJson].
  factory CriterionResult.fromJson(Map<String, dynamic> json) {
    return CriterionResult(
      id: json['id'] as String,
      outcome: Outcome.values.byName(json['outcome'] as String),
      values: {
        for (final e in (json['values'] as Map).entries)
          e.key as String: (e.value as num).toDouble(),
      },
      threshold: json['threshold'] as String,
    );
  }

  /// JSON form used to copy the values into the ADR.
  Map<String, Object> toJson() => {
    'id': id,
    'outcome': outcome.name,
    'values': values,
    'threshold': threshold,
  };
}

CriterionResult _unmeasured(String id, String threshold) =>
    CriterionResult(id: id, outcome: Outcome.missing, threshold: threshold);

/// Criterion 1.3: key-to-paint latency of [latenciesMs].
CriterionResult evaluateKeyLatency(List<double> latenciesMs) {
  const threshold = 'median <= 33 ms, p95 <= 50 ms, >= 500 keystrokes';
  final med = median(latenciesMs);
  if (med == null) return _unmeasured('1.3', threshold);
  final p95 = percentile(latenciesMs, 95)!;
  final Outcome outcome;
  if (latenciesMs.length < minLatencyKeystrokes) {
    outcome = Outcome.unreliable;
  } else if (med <= keyLatencyMedianLimitMs && p95 <= keyLatencyP95LimitMs) {
    outcome = Outcome.pass;
  } else {
    outcome = Outcome.fail;
  }
  return CriterionResult(
    id: '1.3',
    outcome: outcome,
    values: {
      'medianMs': med,
      'p95Ms': p95,
      'keystrokes': latenciesMs.length.toDouble(),
    },
    threshold: threshold,
  );
}

/// Criterion 1.4: burst of [burstCharsPerSecond] characters per second for
/// [burstSeconds] seconds; [sentCount] keystrokes were dispatched over
/// [durationMs].
CriterionResult evaluateBurst(
  KeystrokeIntegrity integrity, {
  required int sentCount,
  required double durationMs,
}) {
  const threshold = '15 chars/s for 10 s, none lost, duplicated or reordered';
  final reliable =
      sentCount >= burstCharsPerSecond * burstSeconds &&
      durationMs >= burstSeconds * 1000;
  final Outcome outcome;
  if (!reliable) {
    outcome = Outcome.unreliable;
  } else if (integrity.isClean) {
    outcome = Outcome.pass;
  } else {
    outcome = Outcome.fail;
  }
  return CriterionResult(
    id: '1.4',
    outcome: outcome,
    values: {
      'sent': sentCount.toDouble(),
      'durationMs': durationMs,
      'lost': integrity.lost.toDouble(),
      'duplicated': integrity.duplicated.toDouble(),
      'outOfOrder': integrity.outOfOrder.toDouble(),
      'unexpected': integrity.unexpected.toDouble(),
    },
    threshold: threshold,
  );
}

/// Criterion 1.5: frame durations in milliseconds while lines scroll.
CriterionResult evaluateFrames(List<double> frameMs) {
  const threshold = 'average >= 50 fps, < 1 % of frames over 50 ms';
  final fps = averageFps(frameMs);
  final share = slowFrameShare(frameMs);
  if (fps == null || share == null) return _unmeasured('1.5', threshold);
  final Outcome outcome;
  if (frameMs.length < minFrameSamples) {
    outcome = Outcome.unreliable;
  } else if (fps >= minAverageFps && share < maxSlowFrameShare) {
    outcome = Outcome.pass;
  } else {
    outcome = Outcome.fail;
  }
  return CriterionResult(
    id: '1.5',
    outcome: outcome,
    values: {'averageFps': fps, 'slowShare': share},
    threshold: threshold,
  );
}

/// Criterion 1.6: drift between the game playhead and the reported time.
CriterionResult evaluateDrift(List<double> game, List<double> reference) {
  const threshold = 'p95 <= 50 ms, max <= 150 ms';
  final stats = driftStats(game, reference);
  if (stats == null) return _unmeasured('1.6', threshold);
  final Outcome outcome;
  if (game.length < minDriftSamples) {
    outcome = Outcome.unreliable;
  } else if (stats.p95Ms <= driftP95LimitMs && stats.maxMs <= driftMaxLimitMs) {
    outcome = Outcome.pass;
  } else {
    outcome = Outcome.fail;
  }
  return CriterionResult(
    id: '1.6',
    outcome: outcome,
    values: {'p95Ms': stats.p95Ms, 'maxMs': stats.maxMs},
    threshold: threshold,
  );
}

/// A reaction time against [limitMs]; null [reactionMs] means the reaction was
/// never observed. [key] names the value (for example `pauseMs`).
CriterionResult evaluateReaction({
  required String id,
  required String key,
  required double? reactionMs,
  required double limitMs,
}) {
  final threshold = '<= ${limitMs.round()} ms';
  if (reactionMs == null) return _unmeasured(id, threshold);
  return CriterionResult(
    id: id,
    outcome: reactionMs <= limitMs ? Outcome.pass : Outcome.fail,
    values: {key: reactionMs},
    threshold: threshold,
  );
}

/// Merges several measurements of one criterion (for example pause, buffering
/// and resume for 1.7): fail if any fails, pass only if all pass.
CriterionResult mergeResults(String id, List<CriterionResult> parts) {
  if (parts.isEmpty) return _unmeasured(id, '');
  final outcomes = parts.map((p) => p.outcome);
  final Outcome outcome;
  if (outcomes.contains(Outcome.fail)) {
    outcome = Outcome.fail;
  } else if (outcomes.contains(Outcome.unreliable)) {
    outcome = Outcome.unreliable;
  } else if (outcomes.contains(Outcome.missing)) {
    outcome = Outcome.missing;
  } else {
    outcome = Outcome.pass;
  }
  return CriterionResult(
    id: id,
    outcome: outcome,
    values: {for (final p in parts) ...p.values},
    threshold: parts.first.threshold,
  );
}

/// Criterion 1.10: the player is at least 480 x 270 CSS px and not covered.
/// Null arguments mean the value was not measured.
CriterionResult evaluatePlayerVisibility({
  required double? widthCss,
  required double? heightCss,
  required bool? covered,
}) {
  const threshold = '>= 480 x 270 CSS px, not covered';
  if (widthCss == null || heightCss == null || covered == null) {
    return _unmeasured('1.10', threshold);
  }
  final ok =
      widthCss >= minPlayerWidthCss &&
      heightCss >= minPlayerHeightCss &&
      !covered;
  return CriterionResult(
    id: '1.10',
    outcome: ok ? Outcome.pass : Outcome.fail,
    values: {'widthCss': widthCss, 'heightCss': heightCss},
    threshold: threshold,
  );
}

/// Criterion 1.11 or 1.12 observed as a yes/no check; null means not measured.
CriterionResult evaluateFlag({
  required String id,
  required bool? ok,
  required String threshold,
}) {
  if (ok == null) return _unmeasured(id, threshold);
  return CriterionResult(
    id: id,
    outcome: ok ? Outcome.pass : Outcome.fail,
    threshold: threshold,
  );
}

/// All results of one browser.
class BrowserReport {
  /// Creates a report.
  const BrowserReport({required this.browser, required this.results});

  /// Browser name, for example `Chrome`.
  final String browser;

  /// Results by criterion.
  final List<CriterionResult> results;

  /// Verdict of this browser alone.
  Verdict get verdict {
    final byId = {for (final r in results) r.id: r.outcome};
    if (byId.values.contains(Outcome.fail)) return Verdict.fail;
    final allPass = criterionIds.every((id) => byId[id] == Outcome.pass);
    return allPass ? Verdict.pass : Verdict.notPass;
  }

  /// Reads the JSON form written by [toJson].
  factory BrowserReport.fromJson(Map<String, dynamic> json) {
    return BrowserReport(
      browser: json['browser'] as String,
      results: [
        for (final r in json['results'] as List)
          CriterionResult.fromJson(r as Map<String, dynamic>),
      ],
    );
  }

  /// JSON form used to copy the values into the ADR.
  Map<String, Object> toJson() => {
    'browser': browser,
    'verdict': verdict.name,
    'results': [for (final r in results) r.toJson()],
  };
}

/// Overall verdict: PASS only if every required browser passes every
/// criterion; any failure is FAIL; anything unreliable or missing is not PASS.
Verdict overallVerdict(
  List<BrowserReport> reports, {
  List<String> required = requiredBrowsers,
}) {
  if (reports.any((r) => r.verdict == Verdict.fail)) return Verdict.fail;
  final measured = {for (final r in reports) r.browser: r.verdict};
  final allPass =
      required.every((b) => measured[b] == Verdict.pass) &&
      reports.every((r) => r.verdict == Verdict.pass);
  return allPass ? Verdict.pass : Verdict.notPass;
}

/// Player states of the IFrame Player API (`YT.PlayerState`).
abstract final class PlayerState {
  /// Video ended.
  static const int ended = 0;

  /// Video playing.
  static const int playing = 1;

  /// Video paused.
  static const int paused = 2;

  /// Video buffering.
  static const int buffering = 3;
}

/// Reactions older than this are not paired with an event.
const double _pairingWindowMs = 2000;

/// Collects the samples and builds the report. No widgets, no DOM: every time
/// value is passed in.
class ViabilityCollector {
  /// Latencies of generated keystrokes (criterion 1.3).
  final List<double> generatedLatencies = [];

  /// Latencies of hand-typed keystrokes (confirmation, informational).
  final List<double> handLatencies = [];

  /// Intervals between frames during the run (criterion 1.5).
  final List<double> frames = [];

  /// Game playhead at each change of the reported time (criterion 1.6).
  final List<double> driftGame = [];

  /// Reported player time at the same instants.
  final List<double> driftReference = [];

  /// Reactions to pause, buffering, resume and seek, worst case first needed.
  final List<double> pauseMs = [];

  /// Reactions to buffering.
  final List<double> bufferingMs = [];

  /// Reactions to resume.
  final List<double> resumeMs = [];

  /// Seek detection delays.
  final List<double> seekMs = [];

  /// Delay between the tab becoming hidden and the player being paused.
  double? hiddenMs;

  /// Result of the click-in-player then click-typing-area check.
  bool? focusOk;

  /// Content Security Policy violations seen by the page.
  int cspViolations = 0;

  /// Integrity of the burst run, once finished.
  KeystrokeIntegrity? burst;

  /// Keystrokes sent in the burst run.
  int burstSent = 0;

  /// Duration of the burst run in milliseconds.
  double burstDurationMs = 0;

  /// True from the start of the 3 minute run until [stopRun].
  bool collecting = false;

  /// True once the run was stopped at its full length.
  bool runComplete = false;

  /// True while the tab is hidden; nothing is sampled then.
  bool tabHidden = false;

  bool _skipNextFrame = false;
  double? _lastFrame;
  int? _probeState;
  double? _probeReported;
  double? _pendingSeekAt;
  final Map<int, double> _probeSeen = {};
  final Map<int, double> _apiCall = {};
  double? _hiddenAt;
  int? _gameState;
  bool _anchored = false;
  bool _running = false;
  double _anchorPlayer = 0;
  double _anchorNow = 0;
  double? _lastReported;

  /// Starts the run: clears the frame and drift samples.
  void startRun() {
    collecting = true;
    runComplete = false;
    frames.clear();
    driftGame.clear();
    driftReference.clear();
    _lastFrame = null;
  }

  /// Ends the run: no further frame or drift sample is collected.
  void stopRun() {
    collecting = false;
    runComplete = true;
  }

  /// Visibility of the tab. Samples taken while hidden, and the first frame
  /// interval after the tab is shown again, are left out.
  void onVisibility(bool hidden) {
    tabHidden = hidden;
    if (!hidden) _skipNextFrame = true;
  }

  /// Records a latency of a generated keystroke unless the tab is hidden.
  void addGeneratedLatency(double ms) {
    if (!tabHidden) generatedLatencies.add(ms);
  }

  /// Records a latency of a hand-typed keystroke unless the tab is hidden.
  void addHandLatency(double ms) {
    if (!tabHidden) handLatencies.add(ms);
  }

  /// Per-frame probe: frame interval, and ground truth of state changes and
  /// jumps of the player time. [reportedMs] and [state] are null without player.
  void onFrame(double now, {double? reportedMs, int? state}) {
    final last = _lastFrame;
    final usable = !tabHidden && !_skipNextFrame;
    if (collecting && last != null && usable) frames.add(now - last);
    if (!tabHidden) _skipNextFrame = false;
    if (reportedMs != null && state != null) {
      _probe(now, last == null ? 0 : now - last, reportedMs, state);
    }
    _lastFrame = now;
  }

  void _probe(double now, double dt, double reportedMs, int state) {
    if (state != _probeState) _probeSeen[state] = now;
    final previous = _probeReported;
    if (previous != null) {
      final expected = previous + (_probeState == PlayerState.playing ? dt : 0);
      if ((reportedMs - expected).abs() >= seekMinJumpMs) {
        _pendingSeekAt ??= now;
      }
    }
    _probeState = state;
    _probeReported = reportedMs;
  }

  /// Game reading of the player on the fixed cadence: interpolates the playhead
  /// between readings, takes drift samples and detects seeks.
  void onPoll(double now, double reportedMs, int state) {
    final running = state == PlayerState.playing;
    if (!_anchored) {
      _anchor(reportedMs, now, running);
      _anchored = true;
      return;
    }
    final pending = _pendingSeekAt;
    if (pending != null && now - pending > _pairingWindowMs) {
      seekMs.add(now - pending);
      _pendingSeekAt = null;
    }
    if (reportedMs != _lastReported) {
      final predicted = _predict(now);
      if ((reportedMs - predicted).abs() >= seekMinJumpMs) {
        _resolveSeek(now);
      } else if (collecting && _running && !tabHidden) {
        driftGame.add(predicted);
        driftReference.add(reportedMs);
      }
      _anchor(reportedMs, now, running);
    } else if (running != _running) {
      _anchor(reportedMs, now, running);
    }
  }

  /// The game noticed a jump of the player time: one value per seek, from the
  /// first frame that showed the jump (at most one frame after it happened)
  /// to this detection.
  void _resolveSeek(double now) {
    final at = _pendingSeekAt;
    if (at != null) seekMs.add(math.max(0, now - at));
    _pendingSeekAt = null;
  }

  void _anchor(double reportedMs, double now, bool running) {
    _anchorPlayer = reportedMs;
    _anchorNow = now;
    _running = running;
    _lastReported = reportedMs;
  }

  double _predict(double now) =>
      _running ? _anchorPlayer + (now - _anchorNow) : _anchorPlayer;

  /// The game's playhead at [now], in milliseconds.
  double playheadMs(double now) => _predict(now);

  /// Records that the page asked the player, through the API, to reach [state].
  void onApiCall(int state, double now) => _apiCall[state] = now;

  /// Records that the tab became hidden at [now].
  void onHidden(double now) => _hiddenAt = now;

  /// State change event of the player: updates the playhead at once and records
  /// the reaction against the API call or the first frame that saw the change.
  void onPlayerState(double now, int state, double reportedMs) {
    final previous = _gameState;
    _gameState = state;
    if (_anchored && (reportedMs - _predict(now)).abs() >= seekMinJumpMs) {
      _resolveSeek(now);
    }
    _anchor(reportedMs, now, state == PlayerState.playing);
    final hiddenAt = _hiddenAt;
    if (hiddenAt != null && state == PlayerState.paused) {
      hiddenMs = now - hiddenAt;
      _hiddenAt = null;
      return;
    }
    final target = switch (state) {
      PlayerState.paused => pauseMs,
      PlayerState.buffering => bufferingMs,
      PlayerState.playing when _isPaused(previous) => resumeMs,
      _ => null,
    };
    if (target == null) return;
    var start = _apiCall.remove(state) ?? _probeSeen[state] ?? now;
    if (now - start > _pairingWindowMs) start = now;
    target.add(math.max(0, now - start));
  }

  bool _isPaused(int? state) =>
      state == PlayerState.paused || state == PlayerState.buffering;

  double? _worst(List<double> values) =>
      values.isEmpty ? null : values.reduce(math.max);

  CriterionResult _reaction(String key, List<double> values) =>
      evaluateReaction(
        id: '1.7',
        key: key,
        reactionMs: _worst(values),
        limitMs: stateReactionLimitMs,
      );

  /// The report of this browser at [now].
  BrowserReport report(
    String browser, {
    required double now,
    required ({double width, double height, bool covered})? visibility,
    required bool cspMeta,
  }) {
    final integrity = burst;
    return BrowserReport(
      browser: browser,
      results: [
        evaluateKeyLatency(generatedLatencies),
        integrity == null
            ? const CriterionResult(id: '1.4', outcome: Outcome.missing)
            : evaluateBurst(
                integrity,
                sentCount: burstSent,
                durationMs: burstDurationMs,
              ),
        evaluateFrames(frames),
        evaluateDrift(driftGame, driftReference),
        mergeResults('1.7', [
          _reaction('pauseMs', pauseMs),
          _reaction('bufferingMs', bufferingMs),
          _reaction('resumeMs', resumeMs),
        ]),
        evaluateReaction(
          id: '1.8',
          key: 'seekMs',
          reactionMs: _worst(seekMs),
          limitMs: seekReactionLimitMs,
        ),
        evaluateReaction(
          id: '1.9',
          key: 'hiddenMs',
          reactionMs: hiddenMs,
          limitMs: hiddenTabLimitMs,
        ),
        evaluatePlayerVisibility(
          widthCss: visibility?.width,
          heightCss: visibility?.height,
          covered: visibility?.covered,
        ),
        evaluateFlag(
          id: '1.11',
          ok: focusOk,
          threshold: 'one click on the typing area restores typing',
        ),
        evaluateFlag(
          id: '1.12',
          ok: cspMeta ? cspViolations == 0 : false,
          threshold: 'CSP meta tag present, no violation',
        ),
      ],
    );
  }
}

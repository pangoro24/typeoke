import 'package:flutter_test/flutter_test.dart';
import 'package:typeoke_frontend/viability/metrics.dart';

List<double> _repeat(double value, int count) => List.filled(count, value);

CriterionResult _result(String id, Outcome outcome) =>
    CriterionResult(id: id, outcome: outcome);

BrowserReport _report(
  String browser, {
  Map<String, Outcome> override = const {},
}) {
  return BrowserReport(
    browser: browser,
    results: [
      for (final id in criterionIds) _result(id, override[id] ?? Outcome.pass),
    ],
  );
}

void main() {
  collectorTests();
  group('statistics', () {
    test('median of odd, even and empty samples', () {
      expect(median([3, 1, 2]), 2);
      expect(median([4, 1, 2, 3]), 2.5);
      expect(median([]), isNull);
    });

    test('percentile uses nearest rank', () {
      final values = [for (var i = 1; i <= 100; i++) i.toDouble()];
      expect(percentile(values, 95), 95);
      expect(percentile(values, 100), 100);
      expect(percentile(values, 0), 1);
      expect(percentile([], 95), isNull);
    });

    test('slow frame share and average fps', () {
      expect(slowFrameShare([16, 50, 51, 20]), 0.25);
      expect(slowFrameShare([]), isNull);
      expect(averageFps([20, 20, 20, 20, 20]), 50);
      expect(averageFps([]), isNull);
      expect(averageFps([0, 0]), isNull);
    });

    test('drift statistics', () {
      final stats = driftStats([100, 200, 300], [110, 190, 450])!;
      expect(stats.maxMs, 150);
      expect(stats.p95Ms, 150);
      expect(driftStats([], []), isNull);
      expect(() => driftStats([1], []), throwsArgumentError);
    });

    test('reaction time is the first observed sample after the event', () {
      final samples = <Sample>[
        (timeMs: 90, observed: true),
        (timeMs: 100, observed: false),
        (timeMs: 200, observed: true),
        (timeMs: 300, observed: true),
      ];
      expect(reactionTimeMs(100, samples), 100);
      expect(reactionTimeMs(250, [(timeMs: 200, observed: true)]), isNull);
      expect(reactionTimeMs(0, []), isNull);
    });
  });

  group('keystroke integrity', () {
    test('clean sequence', () {
      expect(keystrokeIntegrity([1, 2, 3], [1, 2, 3]).isClean, isTrue);
    });

    test('lost keystroke', () {
      final r = keystrokeIntegrity([1, 2, 3], [1, 3]);
      expect(r.lost, 1);
      expect(r.isClean, isFalse);
    });

    test('duplicated keystroke', () {
      final r = keystrokeIntegrity([1, 2, 3], [1, 2, 2, 3]);
      expect(r.duplicated, 1);
      expect(r.lost, 0);
    });

    test('out of order keystroke and unexpected id', () {
      final r = keystrokeIntegrity([1, 2, 3], [1, 3, 2, 99]);
      expect(r.outOfOrder, 1);
      expect(r.unexpected, 1);
      expect(r.lost, 0);
    });
  });

  group('1.3 key latency', () {
    test('passes on the limits with enough keystrokes', () {
      final samples = [..._repeat(33, 475), ..._repeat(50, 25)];
      expect(evaluateKeyLatency(samples).outcome, Outcome.pass);
    });

    test('median just above the limit fails', () {
      expect(evaluateKeyLatency(_repeat(33.1, 500)).outcome, Outcome.fail);
    });

    test('p95 just above the limit fails', () {
      final samples = [..._repeat(10, 474), ..._repeat(50.1, 26)];
      expect(evaluateKeyLatency(samples).outcome, Outcome.fail);
    });

    test('fewer than 500 keystrokes is unreliable', () {
      expect(evaluateKeyLatency(_repeat(5, 499)).outcome, Outcome.unreliable);
    });

    test('empty sample is missing', () {
      expect(evaluateKeyLatency([]).outcome, Outcome.missing);
    });
  });

  group('1.4 burst', () {
    const clean = KeystrokeIntegrity(
      lost: 0,
      duplicated: 0,
      outOfOrder: 0,
      unexpected: 0,
    );

    test('clean full burst passes', () {
      final r = evaluateBurst(clean, sentCount: 150, durationMs: 10000);
      expect(r.outcome, Outcome.pass);
    });

    test('a lost keystroke fails', () {
      final lost = keystrokeIntegrity([1, 2, 3], [1, 3]);
      expect(
        evaluateBurst(lost, sentCount: 150, durationMs: 10000).outcome,
        Outcome.fail,
      );
    });

    test('a duplicated keystroke fails', () {
      final dup = keystrokeIntegrity([1, 2], [1, 1, 2]);
      expect(
        evaluateBurst(dup, sentCount: 150, durationMs: 10000).outcome,
        Outcome.fail,
      );
    });

    test('a short burst is unreliable', () {
      expect(
        evaluateBurst(clean, sentCount: 149, durationMs: 10000).outcome,
        Outcome.unreliable,
      );
      expect(
        evaluateBurst(clean, sentCount: 150, durationMs: 9999).outcome,
        Outcome.unreliable,
      );
    });
  });

  group('1.5 frames', () {
    test('exactly 50 fps with no slow frames passes', () {
      expect(evaluateFrames(_repeat(20, 200)).outcome, Outcome.pass);
    });

    test('just under 50 fps fails', () {
      expect(evaluateFrames(_repeat(20.1, 200)).outcome, Outcome.fail);
    });

    test('1 % slow frames fails, below 1 % passes', () {
      final onePercent = [..._repeat(10, 99), 51.0];
      expect(evaluateFrames(onePercent).outcome, Outcome.fail);
      final below = [..._repeat(10, 199), 51.0];
      expect(evaluateFrames(below).outcome, Outcome.pass);
    });

    test('too few frames is unreliable and empty is missing', () {
      expect(evaluateFrames(_repeat(10, 99)).outcome, Outcome.unreliable);
      expect(evaluateFrames([]).outcome, Outcome.missing);
    });
  });

  group('1.6 drift', () {
    final game = [for (var i = 0; i < 200; i++) i * 100.0];

    test('p95 and maximum on the limits pass', () {
      final reference = [
        for (var i = 0; i < 200; i++)
          game[i] - (i == 0 ? 150 : (i < 11 ? 50 : 0)),
      ];
      expect(evaluateDrift(game, reference).outcome, Outcome.pass);
    });

    test('maximum above 150 ms fails', () {
      final reference = [for (final g in game) g]..[0] = game[0] - 151;
      expect(evaluateDrift(game, reference).outcome, Outcome.fail);
    });

    test('p95 above 50 ms fails', () {
      final reference = [
        for (var i = 0; i < 200; i++) game[i] - (i < 11 ? 51 : 0),
      ];
      expect(evaluateDrift(game, reference).outcome, Outcome.fail);
    });

    test('few samples are unreliable, none are missing', () {
      expect(evaluateDrift([1], [1]).outcome, Outcome.unreliable);
      expect(evaluateDrift([], []).outcome, Outcome.missing);
    });
  });

  group('reaction criteria 1.7 to 1.9', () {
    CriterionResult at(double? ms, double limit) =>
        evaluateReaction(id: '1.7', key: 'ms', reactionMs: ms, limitMs: limit);

    test('250 ms passes, 251 ms fails', () {
      expect(at(250, stateReactionLimitMs).outcome, Outcome.pass);
      expect(at(251, stateReactionLimitMs).outcome, Outcome.fail);
    });

    test('500 ms passes, 501 ms fails', () {
      expect(at(500, seekReactionLimitMs).outcome, Outcome.pass);
      expect(at(501, hiddenTabLimitMs).outcome, Outcome.fail);
    });

    test('never observed is missing', () {
      expect(at(null, seekReactionLimitMs).outcome, Outcome.missing);
    });

    test('merge fails on any failure and passes only if all pass', () {
      final pass = at(100, 250);
      final fail = at(300, 250);
      final missing = at(null, 250);
      expect(mergeResults('1.7', [pass, pass]).outcome, Outcome.pass);
      expect(mergeResults('1.7', [pass, fail, missing]).outcome, Outcome.fail);
      expect(mergeResults('1.7', [pass, missing]).outcome, Outcome.missing);
      expect(
        mergeResults('1.7', [pass, _result('1.7', Outcome.unreliable)]).outcome,
        Outcome.unreliable,
      );
      expect(mergeResults('1.7', []).outcome, Outcome.missing);
    });
  });

  group('1.10 to 1.12', () {
    test('player size on both sides of the limit', () {
      CriterionResult size(double w, double h, bool covered) =>
          evaluatePlayerVisibility(widthCss: w, heightCss: h, covered: covered);
      expect(size(480, 270, false).outcome, Outcome.pass);
      expect(size(479, 270, false).outcome, Outcome.fail);
      expect(size(480, 269, false).outcome, Outcome.fail);
      expect(size(480, 270, true).outcome, Outcome.fail);
      expect(
        evaluatePlayerVisibility(
          widthCss: null,
          heightCss: 270,
          covered: false,
        ).outcome,
        Outcome.missing,
      );
    });

    test('flags are pass, fail or missing', () {
      CriterionResult flag(bool? ok) =>
          evaluateFlag(id: '1.11', ok: ok, threshold: 'one click');
      expect(flag(true).outcome, Outcome.pass);
      expect(flag(false).outcome, Outcome.fail);
      expect(flag(null).outcome, Outcome.missing);
    });
  });

  group('verdict', () {
    test('all criteria pass on both browsers is PASS', () {
      final reports = [_report('Chrome'), _report('Firefox')];
      expect(overallVerdict(reports), Verdict.pass);
    });

    test('one failure on one browser is FAIL', () {
      final reports = [
        _report('Chrome'),
        _report('Firefox', override: {'1.6': Outcome.fail}),
      ];
      expect(overallVerdict(reports), Verdict.fail);
    });

    test('one unreliable value is not PASS', () {
      final reports = [
        _report('Chrome', override: {'1.3': Outcome.unreliable}),
        _report('Firefox'),
      ];
      expect(overallVerdict(reports), Verdict.notPass);
      expect(reports.first.verdict, Verdict.notPass);
    });

    test('a missing browser or an empty list is not PASS', () {
      expect(overallVerdict([_report('Chrome')]), Verdict.notPass);
      expect(overallVerdict([]), Verdict.notPass);
    });

    test('a missing criterion is not PASS', () {
      const partial = BrowserReport(browser: 'Chrome', results: []);
      expect(partial.verdict, Verdict.notPass);
    });

    test('a failure wins over unreliable values', () {
      final reports = [
        _report('Chrome', override: {'1.3': Outcome.unreliable}),
        _report('Firefox', override: {'1.4': Outcome.fail}),
      ];
      expect(overallVerdict(reports), Verdict.fail);
    });

    test('report serializes to JSON', () {
      final json = _report('Chrome').toJson();
      expect(json['browser'], 'Chrome');
      expect(json['verdict'], 'pass');
      expect((json['results'] as List).length, criterionIds.length);
      final back = BrowserReport.fromJson(json.cast<String, dynamic>());
      expect(back.browser, 'Chrome');
      expect(back.verdict, Verdict.pass);
    });
  });
}

void _playFrames(ViabilityCollector c, double from, int count, double step) {
  for (var i = 0; i < count; i++) {
    c.onFrame(from + i * step);
  }
}

void collectorTests() {
  group('collector run and visibility', () {
    test('frames stop accumulating after stopRun', () {
      final c = ViabilityCollector()..startRun();
      _playFrames(c, 0, 10, 16);
      c.stopRun();
      _playFrames(c, 1000, 10, 16);
      expect(c.frames.length, 9);
      expect(c.runComplete, isTrue);
      expect(c.collecting, isFalse);
    });

    test('hidden frames and the first one after showing are excluded', () {
      final c = ViabilityCollector()..startRun();
      _playFrames(c, 0, 3, 16);
      c.onVisibility(true);
      _playFrames(c, 1000, 3, 16);
      c.onVisibility(false);
      _playFrames(c, 5000, 3, 16);
      expect(c.frames, [16, 16, 16, 16]);
    });

    test('latencies are ignored while the tab is hidden', () {
      final c = ViabilityCollector()..onVisibility(true);
      c.addGeneratedLatency(5);
      c.addHandLatency(5);
      c.onVisibility(false);
      c.addGeneratedLatency(6);
      c.addHandLatency(7);
      expect(c.generatedLatencies, [6]);
      expect(c.handLatencies, [7]);
    });
  });

  group('collector seek', () {
    ViabilityCollector playing() {
      final c = ViabilityCollector();
      c.onPoll(0, 10000, PlayerState.playing);
      return c;
    }

    test('one value per seek, from the first frame that saw the jump', () {
      final c = playing();
      c.onFrame(100, reportedMs: 10100, state: PlayerState.playing);
      c.onFrame(116, reportedMs: 20000, state: PlayerState.playing);
      c.onPoll(200, 20000, PlayerState.playing);
      expect(c.seekMs, [84]);
      c.onPoll(300, 20100, PlayerState.playing);
      c.onPoll(5000, 24800, PlayerState.playing);
      expect(c.seekMs.length, 1);
    });

    test('a state event that carries the jump resolves it too', () {
      final c = playing();
      c.onFrame(100, reportedMs: 10100, state: PlayerState.playing);
      c.onFrame(116, reportedMs: 30000, state: PlayerState.playing);
      c.onPlayerState(150, PlayerState.buffering, 30000);
      c.onPoll(200, 30000, PlayerState.buffering);
      expect(c.seekMs, [34]);
    });

    test('an undetected seek is recorded once, not as a growing value', () {
      final c = playing();
      c.onFrame(100, reportedMs: 10100, state: PlayerState.playing);
      c.onFrame(116, reportedMs: 30000, state: PlayerState.playing);
      c.onPoll(3000, 10000, PlayerState.playing);
      c.onPoll(60000, 10000, PlayerState.playing);
      expect(c.seekMs, [2884]);
    });
  });

  group('collector reactions', () {
    test('resume is measured from the API call to the state event', () {
      final c = ViabilityCollector();
      c.onPoll(0, 1000, PlayerState.playing);
      c.onApiCall(PlayerState.paused, 100);
      c.onPlayerState(180, PlayerState.paused, 1100);
      c.onApiCall(PlayerState.playing, 500);
      c.onPlayerState(784, PlayerState.playing, 1100);
      expect(c.pauseMs, [80]);
      expect(c.resumeMs, [284]);
    });

    test('hidden tab pause is not counted as a pause reaction', () {
      final c = ViabilityCollector();
      c.onHidden(100);
      c.onPlayerState(350, PlayerState.paused, 0);
      expect(c.hiddenMs, 250);
      expect(c.pauseMs, isEmpty);
    });
  });
}

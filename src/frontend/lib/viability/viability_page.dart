/// Disposable viability prototype (milestone 1, Assumption A2): the official
/// YouTube player next to a typing area and scrolling lines, with the
/// measurements of Requirement 1 shown in a table. Texts are hard-coded on
/// purpose: the page is deleted or rewritten before the game screen exists.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';

import 'iframe_player.dart';
import 'keystroke_generator.dart';
import 'metrics.dart';

/// Length of the continuous run required by criterion 1.2.
const Duration runLength = Duration(minutes: 3);

/// Cadence of the game's reading of the player's current time.
const Duration pollCadence = Duration(milliseconds: 100);

/// Rate of the generated keystrokes of the latency run.
const int latencyKeysPerSecond = 25;

/// The viability prototype page.
class ViabilityPage extends StatefulWidget {
  /// Creates the page.
  const ViabilityPage({super.key});

  @override
  State<ViabilityPage> createState() => _ViabilityPageState();
}

enum _Run { latency, burst }

class _ViabilityPageState extends State<ViabilityPage>
    with SingleTickerProviderStateMixin {
  static const double _lineHeight = 28;
  static const int _lineCount = 12;

  final ViabilityCollector _collector = ViabilityCollector();
  final ValueNotifier<double> _scroll = ValueNotifier(0);
  final TextEditingController _videoField = TextEditingController();
  final TextEditingController _otherField = TextEditingController();
  final FocusNode _typingFocus = FocusNode(debugLabel: 'typing area');
  final Map<String, BrowserReport> _others = {};
  late final Ticker _ticker;
  late final KeystrokeGenerator _generator;
  Timer? _pollTimer;
  Timer? _uiTimer;
  IframePlayer? _player;
  _Run? _run;
  List<int> _registered = [];
  String _typed = '';
  int _generatedCount = 0;
  String? _message;
  double? _firstFrameMs;
  double? _runStartedAt;
  int? _heapAtRunEnd;

  @override
  void initState() {
    super.initState();
    _generator = KeystrokeGenerator(
      dispatch: (id) => dispatchGeneratedKey(keyboardTarget(), id),
      nowMs: nowMs,
    );
    _ticker = createTicker(_onTick)..start();
    _pollTimer = Timer.periodic(pollCadence, (_) => _poll());
    _uiTimer = Timer.periodic(const Duration(seconds: 1), (_) => _refresh());
    _videoField.text = queryParameter('v') ?? '';
    observeVisibility(_onVisibility);
    observeCspViolations(() => _collector.cspViolations++);
    if (queryParameter('autorun') == 'keys') {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _focusTyping();
        _startRun();
        _startKeys(_Run.latency);
      });
    }
  }

  @override
  void dispose() {
    _ticker.dispose();
    _pollTimer?.cancel();
    _uiTimer?.cancel();
    _generator.cancel();
    _scroll.dispose();
    _videoField.dispose();
    _otherField.dispose();
    _typingFocus.dispose();
    super.dispose();
  }

  void _onTick(Duration elapsed) {
    final now = nowMs();
    _firstFrameMs ??= now;
    _scroll.value =
        (elapsed.inMicroseconds / 1000 * 0.05) % (_lineHeight * _lineCount);
    final player = _player;
    final ready = player != null && player.isReady;
    _collector.onFrame(
      now,
      reportedMs: ready ? player.currentTimeMs : null,
      state: ready ? player.state : null,
    );
  }

  void _poll() {
    final player = _player;
    if (player == null || !player.isReady) return;
    _collector.onPoll(nowMs(), player.currentTimeMs, player.state);
  }

  void _refresh() {
    final started = _runStartedAt;
    if (started != null &&
        !_collector.runComplete &&
        nowMs() - started >= runLength.inMilliseconds) {
      _heapAtRunEnd = usedHeapBytes();
      _collector.stopRun();
    }
    setState(() {});
  }

  void _onVisibility(bool hidden) {
    _collector.onVisibility(hidden);
    final player = _player;
    if (!hidden || player == null || !player.isReady) return;
    _collector.onHidden(nowMs());
    player.pause();
  }

  void _onPlayerState(int state) {
    final player = _player;
    if (player == null) return;
    _collector.onPlayerState(nowMs(), state, player.currentTimeMs);
  }

  void _loadVideo() {
    final id = _videoField.text.trim();
    if (!isValidVideoId(id)) {
      setState(() => _message = 'Enter an 11 character video id.');
      return;
    }
    setState(() {
      _message = null;
      _player = IframePlayer(
        videoId: id,
        onState: _onPlayerState,
        onError: (code) => setState(() => _message = 'Player error $code'),
      );
    });
  }

  void _focusTyping() {
    focusFlutterView();
    _typingFocus.requestFocus();
  }

  void _startRun() {
    _collector.startRun();
    _runStartedAt = nowMs();
    _heapAtRunEnd = null;
  }

  void _startKeys(_Run run) {
    if (_generator.isRunning) return;
    _focusTyping();
    _run = run;
    _registered = [];
    final latency = run == _Run.latency;
    final count = latency
        ? minLatencyKeystrokes
        : burstCharsPerSecond * burstSeconds;
    final rate = latency ? latencyKeysPerSecond : burstCharsPerSecond;
    _generator.start(
      count: count,
      perSecond: rate,
      onDone: () => _finishKeys(run),
    );
  }

  void _finishKeys(_Run run) {
    if (run == _Run.burst) {
      _collector
        ..burst = keystrokeIntegrity(_generator.sent, _registered)
        ..burstSent = _generator.sent.length
        ..burstDurationMs =
            (_generator.finishedAtMs ?? 0) - _generator.startedAtMs;
    }
    _run = null;
  }

  KeyEventResult _onKey(FocusNode node, KeyEvent event) {
    final character = event.character;
    if (event is! KeyDownEvent || character == null) {
      return KeyEventResult.ignored;
    }
    final startMs = event.timeStamp.inMicroseconds / 1000;
    final id = idForChar(character);
    setState(() {
      if (id == null) {
        _typed = '$_typed$character';
        if (_typed.length > 40) _typed = _typed.substring(_typed.length - 40);
      } else {
        _generatedCount++;
        if (_run != null) _registered.add(id);
      }
    });
    final latencyRun = _run == _Run.latency;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final latency = nowMs() - startMs;
      if (id == null) {
        _collector.addHandLatency(latency);
      } else if (latencyRun) {
        _collector.addGeneratedLatency(latency);
      }
    });
    return KeyEventResult.handled;
  }

  BrowserReport _report() => _collector.report(
    browserName(),
    now: nowMs(),
    visibility: _player?.visibility(),
    cspMeta: hasCspMeta(),
  );

  Future<void> _copy(BrowserReport report) async {
    final hand = _collector.handLatencies;
    final data = {
      'browser': report.browser,
      'userAgent': userAgent(),
      'verdictThisBrowser': report.verdict.name,
      'verdictOverall': overallVerdict([
        ..._others.values.where((o) => o.browser != report.browser),
        report,
      ]).name,
      'report': report.toJson(),
      'informational': _informational(),
      'handTyped': {
        'count': hand.length,
        'medianMs': median(hand),
        'p95Ms': percentile(hand, 95),
      },
    };
    await Clipboard.setData(
      ClipboardData(text: const JsonEncoder.withIndent('  ').convert(data)),
    );
    setState(() => _message = 'Copied.');
  }

  void _import() {
    try {
      final json = jsonDecode(_otherField.text) as Map<String, dynamic>;
      final other = BrowserReport.fromJson(
        json['report'] as Map<String, dynamic>,
      );
      setState(() {
        _others[other.browser] = other;
        _message = 'Imported ${other.browser}.';
      });
    } on Object {
      setState(() => _message = 'Not a report copied from this page.');
    }
  }

  Map<String, Object?> _informational() {
    final sizes = loadSizes();
    final started = _runStartedAt;
    return {
      'firstFrameMs': _firstFrameMs,
      'resourceEncodedBytes': sizes.encodedBytes,
      'loadServedFromCache': sizes.cached,
      'heapBytesNow': usedHeapBytes(),
      'heapBytesAfter3Minutes': _heapAtRunEnd,
      'runElapsedSeconds': started == null
          ? null
          : math.min(runLength.inSeconds, (nowMs() - started) / 1000),
      'devicePixelRatio': WidgetsBinding
          .instance
          .platformDispatcher
          .views
          .first
          .devicePixelRatio,
    };
  }

  @override
  Widget build(BuildContext context) {
    final report = _report();
    final overall = overallVerdict([
      ..._others.values.where((o) => o.browser != report.browser),
      report,
    ]);
    return Scaffold(
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(width: 660, child: _leftColumn()),
            const SizedBox(width: 16),
            Expanded(child: _rightColumn(report, overall)),
          ],
        ),
      ),
    );
  }

  Widget _leftColumn() {
    final player = _player;
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _videoField,
                  decoration: const InputDecoration(
                    labelText: 'Video id (typed here, never stored)',
                  ),
                ),
              ),
              const SizedBox(width: 8),
              FilledButton(onPressed: _loadVideo, child: const Text('Load')),
            ],
          ),
          const SizedBox(height: 8),
          SizedBox(
            width: 640,
            height: 360,
            child: player == null
                ? const ColoredBox(
                    color: Colors.black12,
                    child: Center(child: Text('Load a video to start')),
                  )
                : player.buildView(),
          ),
          const SizedBox(height: 8),
          _scrollingLines(),
          const SizedBox(height: 8),
          _typingArea(),
          const SizedBox(height: 8),
          _controls(),
        ],
      ),
    );
  }

  Widget _scrollingLines() {
    final lines = [
      for (var i = 0; i < _lineCount * 2; i++)
        Text(
          'line ${i % _lineCount + 1} alpha bravo charlie delta echo foxtrot',
          style: const TextStyle(fontSize: 18, height: 28 / 18),
        ),
    ];
    return SizedBox(
      width: 640,
      height: 112,
      child: ClipRect(
        child: ValueListenableBuilder<double>(
          valueListenable: _scroll,
          child: OverflowBox(
            alignment: Alignment.topLeft,
            maxHeight: double.infinity,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: lines,
            ),
          ),
          builder: (context, offset, child) =>
              Transform.translate(offset: Offset(0, -offset), child: child),
        ),
      ),
    );
  }

  Widget _typingArea() {
    return Focus(
      focusNode: _typingFocus,
      onKeyEvent: _onKey,
      child: GestureDetector(
        onTap: _focusTyping,
        child: ListenableBuilder(
          listenable: _typingFocus,
          builder: (context, _) => Container(
            width: 640,
            height: 72,
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              border: Border.all(
                color: _typingFocus.hasFocus ? Colors.blue : Colors.grey,
                width: 2,
              ),
            ),
            child: Text(
              'Typing area (click here, then type). Generated keys: '
              '$_generatedCount\n$_typed',
            ),
          ),
        ),
      ),
    );
  }

  Widget _controls() {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        FilledButton(
          onPressed: _startRun,
          child: const Text('Start 3 min run'),
        ),
        OutlinedButton(
          onPressed: () => _startKeys(_Run.latency),
          child: const Text('Generate 500 keys'),
        ),
        OutlinedButton(
          onPressed: () => _startKeys(_Run.burst),
          child: const Text('Burst 15/s for 10 s'),
        ),
        OutlinedButton(
          onPressed: () {
            _collector.onApiCall(PlayerState.paused, nowMs());
            _player?.pause();
          },
          child: const Text('Pause (API)'),
        ),
        OutlinedButton(
          onPressed: () {
            _collector.onApiCall(PlayerState.playing, nowMs());
            _player?.play();
          },
          child: const Text('Resume (API)'),
        ),
        OutlinedButton(
          onPressed: () => setState(() => _collector.focusOk = true),
          child: const Text('Typing worked after one click'),
        ),
        OutlinedButton(
          onPressed: () => setState(() => _collector.focusOk = false),
          child: const Text('Typing needed more clicks'),
        ),
      ],
    );
  }

  Widget _rightColumn(BrowserReport report, Verdict overall) {
    final started = _runStartedAt;
    final elapsed = started == null
        ? 0
        : math.min(runLength.inSeconds, (nowMs() - started) / 1000);
    final hand = _collector.handLatencies;
    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '${report.browser}: ${report.verdict.name.toUpperCase()}'
            '    Overall (both browsers): ${overall.name.toUpperCase()}',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          Text(
            _collector.runComplete
                ? 'Run complete (${runLength.inSeconds} s)'
                : 'Run: ${elapsed.toStringAsFixed(0)} s of ${runLength.inSeconds} s',
          ),
          if (_message != null) Text(_message!),
          const SizedBox(height: 8),
          for (final r in report.results) _row(r),
          const Divider(),
          Text('Informational (A3): ${jsonEncode(_informational())}'),
          Text(
            'Hand typed: ${hand.length} keys, median '
            '${median(hand)?.toStringAsFixed(1)} ms, p95 '
            '${percentile(hand, 95)?.toStringAsFixed(1)} ms',
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              FilledButton(
                onPressed: () => unawaited(_copy(report)),
                child: const Text('Copy JSON'),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: TextField(
                  controller: _otherField,
                  decoration: const InputDecoration(
                    labelText: 'Paste the other browser JSON',
                  ),
                ),
              ),
              TextButton(onPressed: _import, child: const Text('Import')),
            ],
          ),
          Text('Imported: ${_others.keys.join(', ')}'),
        ],
      ),
    );
  }

  Widget _row(CriterionResult r) {
    final values = r.values.entries
        .map((e) => '${e.key}=${e.value.toStringAsFixed(2)}')
        .join(', ');
    final color = switch (r.outcome) {
      Outcome.pass => Colors.green,
      Outcome.fail => Colors.red,
      _ => Colors.orange,
    };
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(width: 40, child: Text(r.id)),
          SizedBox(
            width: 90,
            child: Text(r.outcome.name, style: TextStyle(color: color)),
          ),
          Expanded(child: Text('$values  [${r.threshold}]')),
        ],
      ),
    );
  }
}

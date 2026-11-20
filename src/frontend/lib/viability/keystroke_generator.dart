/// Generated keystrokes for the viability check. Each keystroke carries a
/// unique id encoded as one printable character, so the typing area can tell
/// which keystroke it registered and detect loss, duplication and reordering.
library;

import 'dart:async';

import 'package:web/web.dart' as web;

/// First code point used to encode keystroke ids (CJK unified ideographs, all
/// printable, none a combining mark or whitespace).
const int _baseCodePoint = 0x4E00;

/// Largest number of distinct keystroke ids.
const int maxKeystrokeIds = 1000;

/// The character that encodes keystroke [id].
String charForId(int id) => String.fromCharCode(_baseCodePoint + id);

/// The keystroke id encoded by [character], or null for any other character.
int? idForChar(String? character) {
  if (character == null || character.runes.length != 1) return null;
  final id = character.runes.first - _baseCodePoint;
  return id >= 0 && id < maxKeystrokeIds ? id : null;
}

/// Dispatches one keydown and one keyup DOM event, with the id encoded in
/// `key`, to the Flutter view ([target]). The events travel the
/// same path as physical keys: the browser event, the engine, the focus tree.
void dispatchGeneratedKey(web.EventTarget target, int id) {
  for (final type in const ['keydown', 'keyup']) {
    target.dispatchEvent(
      web.KeyboardEvent(
        type,
        web.KeyboardEventInit(
          key: charForId(id),
          code: 'KeyA',
          bubbles: true,
          cancelable: true,
        ),
      ),
    );
  }
}

/// Sends a fixed number of keystrokes at a fixed rate; the clock and the
/// dispatch function are injected so the schedule is independent of the DOM.
class KeystrokeGenerator {
  /// Creates a generator.
  KeystrokeGenerator({required this.dispatch, required this.nowMs});

  /// Sends keystroke `id`.
  final void Function(int id) dispatch;

  /// Clock in milliseconds.
  final double Function() nowMs;

  /// Ids sent so far, in order.
  final List<int> sent = [];

  /// Clock value when the run started.
  double startedAtMs = 0;

  /// Clock value when the last keystroke was sent; null while running.
  double? finishedAtMs;

  Timer? _timer;

  /// True while keystrokes are still being sent.
  bool get isRunning => _timer != null;

  /// Starts a run of [count] keystrokes at [perSecond]; ids start at 0 and
  /// keystroke n is due n / [perSecond] seconds after the start, so a run
  /// takes at least count / perSecond seconds. Late keystrokes are sent
  /// together, so the rate holds on average.
  void start({
    required int count,
    required int perSecond,
    required void Function() onDone,
  }) {
    assert(count <= maxKeystrokeIds && !isRunning);
    sent.clear();
    finishedAtMs = null;
    startedAtMs = nowMs();
    _timer = Timer.periodic(const Duration(milliseconds: 5), (timer) {
      final due = ((nowMs() - startedAtMs) / 1000 * perSecond).floor();
      while (sent.length < count && sent.length < due) {
        final id = sent.length;
        sent.add(id);
        dispatch(id);
      }
      if (sent.length == count) {
        timer.cancel();
        _timer = null;
        finishedAtMs = nowMs();
        onDone();
      }
    });
  }

  /// Stops a run in progress.
  void cancel() {
    _timer?.cancel();
    _timer = null;
  }
}

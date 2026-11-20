/// Browser-only glue of the viability prototype: the official YouTube IFrame
/// Player API and a few page probes. Thin by design; no audio or video data is
/// ever touched, the player and its controls stay as YouTube delivers them.
library;

import 'dart:async';
import 'dart:js_interop';
import 'dart:js_interop_unsafe';
import 'dart:ui_web' as ui_web;

import 'package:flutter/widgets.dart';
import 'package:web/web.dart' as web;

/// Official player script, loaded from the YouTube origin.
const String _apiScriptUrl = 'https://www.youtube.com/iframe_api';

final RegExp _videoIdPattern = RegExp(r'^[A-Za-z0-9_-]{11}$');

/// True when [id] has the shape of a YouTube video id.
bool isValidVideoId(String id) => _videoIdPattern.hasMatch(id);

@JS('YT.Player')
extension type _YtPlayer._(JSObject _) implements JSObject {
  external _YtPlayer(web.Element element, JSObject options);
  external double getCurrentTime();
  external int getPlayerState();
  external void pauseVideo();
  external void playVideo();
}

Completer<void>? _apiLoad;

Future<void> _loadApi() {
  final existing = _apiLoad;
  if (existing != null) return existing.future;
  final completer = Completer<void>();
  _apiLoad = completer;
  web.window.setProperty(
    'onYouTubeIframeAPIReady'.toJS,
    (() => completer.complete()).toJS,
  );
  final script = web.HTMLScriptElement()
    ..src = _apiScriptUrl
    ..async = true;
  script.addEventListener(
    'error',
    ((web.Event _) => completer.completeError(
      StateError('Player script failed to load'),
    )).toJS,
  );
  web.document.head!.append(script);
  return completer.future;
}

/// The official YouTube player embedded as a platform view.
class IframePlayer {
  /// Creates a player for [videoId]; callbacks receive API state and error codes.
  IframePlayer({
    required this.videoId,
    required this.onState,
    required this.onError,
  }) : assert(isValidVideoId(videoId)) {
    _iframe = web.HTMLIFrameElement()
      ..src =
          'https://www.youtube.com/embed/$videoId?enablejsapi=1&playsinline=1'
          '&origin=${Uri.encodeComponent(web.window.location.origin)}'
      ..allow = 'autoplay; encrypted-media; picture-in-picture; fullscreen'
      ..allowFullscreen = true
      ..style.border = '0'
      ..style.width = '100%'
      ..style.height = '100%';
    _viewType = 'typeoke-youtube-${_nextView++}';
    ui_web.platformViewRegistry.registerViewFactory(
      _viewType,
      (int _) => _iframe,
    );
  }

  static int _nextView = 0;

  /// The video shown by this player.
  final String videoId;

  /// Called with a `YT.PlayerState` value on every state change.
  final void Function(int state) onState;

  /// Called with a player error code.
  final void Function(int code) onError;

  late final web.HTMLIFrameElement _iframe;
  late final String _viewType;
  _YtPlayer? _player;
  bool _ready = false;

  /// The platform view; the player script is attached once it is in the page.
  Widget buildView() => HtmlElementView(
    viewType: _viewType,
    onPlatformViewCreated: (_) => WidgetsBinding.instance.addPostFrameCallback(
      (_) => unawaited(_attach()),
    ),
  );

  Future<void> _attach() async {
    try {
      await _loadApi();
    } on StateError {
      onError(-1);
      return;
    }
    final events = JSObject()
      ..setProperty('onReady'.toJS, ((JSAny? _) => _ready = true).toJS)
      ..setProperty(
        'onStateChange'.toJS,
        ((JSObject e) {
          onState(e.getProperty<JSNumber>('data'.toJS).toDartInt);
        }).toJS,
      )
      ..setProperty(
        'onError'.toJS,
        ((JSObject e) {
          onError(e.getProperty<JSNumber>('data'.toJS).toDartInt);
        }).toJS,
      );
    final options = JSObject()..setProperty('events'.toJS, events);
    _player = _YtPlayer(_iframe, options);
  }

  /// True once the player fired `onReady`; its methods are unavailable before.
  bool get isReady => _ready;

  /// Reported current time in milliseconds.
  double get currentTimeMs => (_player?.getCurrentTime() ?? 0) * 1000;

  /// Current `YT.PlayerState`, or -1 when not ready.
  int get state => _player?.getPlayerState() ?? -1;

  /// Pauses through the API.
  void pause() => _player?.pauseVideo();

  /// Plays through the API.
  void play() => _player?.playVideo();

  /// Size of the player in CSS pixels and whether another element covers it.
  /// Returns null when the player is not in the visible viewport.
  ({double width, double height, bool covered})? visibility() {
    final rect = _iframe.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return null;
    final points = [
      (rect.left + rect.width / 2, rect.top + rect.height / 2),
      (rect.left + 4, rect.top + 4),
      (rect.right - 4, rect.top + 4),
      (rect.left + 4, rect.bottom - 4),
      (rect.right - 4, rect.bottom - 4),
    ];
    var covered = false;
    for (final (x, y) in points) {
      final hit = web.document.elementFromPoint(x, y);
      if (hit == null) return null;
      if (!identical(hit, _iframe)) covered = true;
    }
    return (width: rect.width, height: rect.height, covered: covered);
  }
}

/// High resolution time in milliseconds since the page started.
double nowMs() => web.window.performance.now();

/// Calls [onChange] with `true` when the tab becomes hidden, `false` when shown.
void observeVisibility(void Function(bool hidden) onChange) {
  web.document.addEventListener(
    'visibilitychange',
    ((web.Event _) => onChange(web.document.hidden)).toJS,
  );
}

/// Calls [onViolation] for every Content Security Policy violation of the page.
void observeCspViolations(void Function() onViolation) {
  web.document.addEventListener(
    'securitypolicyviolation',
    ((web.Event _) => onViolation()).toJS,
  );
}

/// True when the page carries a Content Security Policy meta tag.
bool hasCspMeta() =>
    web.document.querySelector('meta[http-equiv="Content-Security-Policy"]') !=
    null;

/// Browser family from the user agent: `Firefox`, `Edge`, `Chrome` or `Other`.
String browserName() {
  final agent = web.window.navigator.userAgent;
  if (agent.contains('Firefox/')) return 'Firefox';
  if (agent.contains('Edg/')) return 'Edge';
  if (agent.contains('Chrome/')) return 'Chrome';
  return 'Other';
}

/// The user agent string.
String userAgent() => web.window.navigator.userAgent;

/// Query parameter of the page URL, or null.
String? queryParameter(String name) => Uri.base.queryParameters[name];

/// Used JavaScript heap in bytes (Chromium only), or null.
int? usedHeapBytes() {
  final memory = web.window.performance.getProperty<JSAny?>('memory'.toJS);
  if (memory == null || memory.isUndefinedOrNull) return null;
  final used = (memory as JSObject).getProperty<JSAny?>('usedJSHeapSize'.toJS);
  if (used == null || used.isUndefinedOrNull) return null;
  return (used as JSNumber).toDartInt;
}

/// Sum of the encoded (as transferred, before decoding) body sizes of every
/// resource of the page, in bytes, and whether the page load came from cache.
({int encodedBytes, bool cached}) loadSizes() {
  var total = 0;
  var cached = true;
  final entries = web.window.performance.getEntriesByType('resource').toDart;
  for (final item in entries) {
    final entry = item as web.PerformanceResourceTiming;
    total += entry.encodedBodySize;
    if (entry.transferSize > 0) cached = false;
  }
  return (encodedBytes: total, cached: cached);
}

web.HTMLElement? _flutterView() =>
    (web.document.querySelector('flutter-view') ??
            web.document.querySelector('flt-glass-pane'))
        as web.HTMLElement?;

/// Moves DOM keyboard focus out of any frame (for example the YouTube player)
/// back to the Flutter view, which is where key events must arrive.
void focusFlutterView() {
  final active = web.document.activeElement;
  if (active != null && active.tagName == 'IFRAME') {
    (active as web.HTMLElement).blur();
  }
  final view = _flutterView();
  if (view == null) return;
  if (!view.hasAttribute('tabindex')) view.setAttribute('tabindex', '-1');
  view.focus();
}

/// The element that generated keystrokes are dispatched to: the Flutter view.
web.EventTarget keyboardTarget() =>
    _flutterView() ?? web.document.body ?? web.window;

import 'dart:js_interop';

@JS('ieltsAudio')
external _IeltsAudio get _audio;

extension type _IeltsAudio._(JSObject _) implements JSObject {
  external JSPromise<JSAny?> startMic(JSFunction onPcm);
  external void play(JSArrayBuffer buffer);
  external double remainingMs();
  external double level();
  external void stop();
}

/// Microphone and speaker. The Web Audio code is in web/audio.js.
class BrowserAudio {
  /// Starts the mic; [onPcm] gets PCM16 mono 16 kHz chunks.
  static Future<void> startMic(void Function(JSArrayBuffer pcm) onPcm) =>
      _audio.startMic(onPcm.toJS).toDart;

  /// Queues PCM16 mono 24 kHz speech.
  static void play(JSArrayBuffer pcm) => _audio.play(pcm);

  /// Queued speech that has not been played yet.
  static Duration get remaining => Duration(milliseconds: _audio.remainingMs().round());

  /// Loudness of the speech playing now, 0..1.
  static double get level => _audio.level();

  static void stop() => _audio.stop();
}

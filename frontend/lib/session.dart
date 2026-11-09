import 'dart:async';
import 'dart:convert';
import 'dart:js_interop';

import 'package:flutter/foundation.dart';
import 'package:web/web.dart' as web;

import 'api.dart';
import 'audio.dart';

enum Phase { idle, connecting, examinerSpeaking, yourTurn, hearing, thinking, ending, error }

class Message {
  Message({required this.fromExaminer, this.text = ''});

  /// A message from a past session (GET /api/sessions/{id}).
  Message.fromStored(Map<String, dynamic> json)
    : fromExaminer = json['role'] == 'examiner',
      text = json['text'],
      answer = json['answer'],
      hasAudio = json['has_audio'] ?? false,
      feedback = json['feedback'] == null ? null : AnswerFeedback.fromJson(json['feedback']),
      delivery = json['delivery'] == null ? null : Delivery.fromJson(json['delivery']);

  final bool fromExaminer;
  String text;
  AnswerFeedback? feedback; // for the candidate's answers, once the analyst has checked it
  Delivery? delivery; // measured fluency and pronunciation of the answer
  int? answer; // stored answers: 0, 1, 2, ...
  bool hasAudio = false; // stored answers: the recording can be played
}

/// Measured numbers for one answer. Any of them can be missing for very short answers.
class Delivery {
  Delivery.fromJson(Map<String, dynamic> json)
    : wpm = json['fluency']['wpm'],
      words = json['fluency']['words'],
      pauses = json['fluency']['pauses'],
      longestPause = (json['fluency']['longest_pause'] as num?)?.toDouble(),
      fillers = json['fluency']['fillers'],
      repetitions = json['fluency']['repetitions'],
      pronunciation = (json['pronunciation']['score'] as num?)?.toDouble(),
      unclearWords = [
        for (final w in json['pronunciation']['words'])
          (word: w['word'] as String, expected: w['expected'] as String, heard: w['heard'] as String),
      ],
      sounds = [
        for (final s in json['pronunciation']['sounds'])
          (expected: s['expected'] as String, heard: s['heard'] as String, count: s['count'] as int),
      ];

  final int? wpm, words, pauses, fillers, repetitions;
  final double? longestPause, pronunciation;
  final List<({String word, String expected, String heard})> unclearWords;
  final List<({String expected, String heard, int count})> sounds; // heard '' = left out
}

class Correction {
  Correction.fromJson(Map<String, dynamic> json)
    : category = json['category'],
      original = json['original'],
      better = json['better'],
      why = json['why'];

  final String category, original, better, why;
}

class AnswerFeedback {
  AnswerFeedback.fromJson(Map<String, dynamic> json)
    : corrections = [for (final c in json['corrections']) Correction.fromJson(c)],
      good = json['good'],
      tip = json['tip'];

  final List<Correction> corrections;
  final String good, tip;
}

/// One practice session: talks to the backend over /ws (protocol in backend/app/main.py).
class Session extends ChangeNotifier {
  Phase phase = Phase.idle;
  final messages = <Message>[];
  String partial = ''; // live transcript of the answer being spoken
  String error = '';
  String? id; // the stored session, once the backend has created it

  /// Called with the session id when a session with answers has been saved.
  void Function(String id)? onEnded;

  web.WebSocket? _ws;
  bool _micOpen = false; // closed while the examiner speaks, so it can't hear itself
  Timer? _turnTimer;

  bool get active => phase != Phase.idle && phase != Phase.error && phase != Phase.ending;

  List<Message> get answers => [
    for (final m in messages)
      if (!m.fromExaminer) m,
  ];

  int get correctionCount => answers.fold(0, (sum, a) => sum + (a.feedback?.corrections.length ?? 0));

  Future<void> start({required String mode, required String voice, String? topic}) async {
    messages.clear();
    partial = '';
    id = null;
    _setPhase(Phase.connecting);
    try {
      await BrowserAudio.startMic(_sendMic);
    } catch (e) {
      _fail('The microphone is not available. Allow it in the browser and try again.');
      return;
    }
    final ws = web.WebSocket(sessionUri.toString())..binaryType = 'arraybuffer';
    _ws = ws;
    ws.onopen = ((web.Event _) {
      ws.send(jsonEncode({'type': 'start', 'mode': mode, 'voice': voice, 'topic': topic}).toJS);
    }).toJS;
    ws.onmessage = ((web.MessageEvent event) => _receive(event.data)).toJS;
    ws.onclose = ((web.CloseEvent _) {
      if (_ws == ws) _fail('Lost the connection to the backend. Is `make run` still running?');
    }).toJS;
  }

  /// Ends the session. With answers, waits until the backend has saved their feedback.
  void end() {
    final ws = _ws;
    if (ws == null || answers.isEmpty || ws.readyState != web.WebSocket.OPEN) return stop();
    _cleanUp();
    ws.send(jsonEncode({'type': 'end'}).toJS);
    _setPhase(Phase.ending);
  }

  void stop() {
    final ws = _ws;
    _ws = null; // so onclose does not report an error
    ws?.close();
    _cleanUp();
    _setPhase(Phase.idle);
  }

  @override
  void dispose() {
    final ws = _ws;
    _ws = null;
    ws?.close();
    _cleanUp();
    super.dispose();
  }

  void _sendMic(JSArrayBuffer pcm) {
    if (_micOpen && _ws?.readyState == web.WebSocket.OPEN) _ws!.send(pcm);
  }

  void _receive(JSAny? data) {
    if (data.isA<JSArrayBuffer>()) {
      if (phase != Phase.ending) BrowserAudio.play(data as JSArrayBuffer);
      return;
    }
    final message = jsonDecode((data as JSString).toDart) as Map<String, dynamic>;
    switch (message['type']) {
      case 'ready':
        id = message['session'];
        _setPhase(Phase.examinerSpeaking);
      case 'ended':
        _ws = null; // the backend closes the connection
        _setPhase(Phase.idle);
        onEnded?.call(message['session']);
      case 'examiner' when phase != Phase.ending:
        if (messages.isEmpty || !messages.last.fromExaminer) messages.add(Message(fromExaminer: true));
        messages.last.text = '${messages.last.text} ${message['text']}'.trim();
        _setPhase(Phase.examinerSpeaking);
      case 'examiner_done':
        // Open the mic only after the queued speech has finished playing.
        _turnTimer = Timer(BrowserAudio.remaining + const Duration(milliseconds: 300), () {
          _micOpen = true;
          _setPhase(Phase.yourTurn);
        });
      case 'listening':
        _setPhase(Phase.hearing);
      case 'partial':
        partial = message['text'];
        notifyListeners();
      case 'transcript':
        _micOpen = false;
        partial = '';
        messages.add(Message(fromExaminer: false, text: message['text']));
        _setPhase(Phase.thinking);
      case 'feedback':
        final index = message['answer'] as int;
        if (index < answers.length) answers[index].feedback = AnswerFeedback.fromJson(message);
        notifyListeners();
      case 'delivery':
        final index = message['answer'] as int;
        if (index < answers.length) answers[index].delivery = Delivery.fromJson(message);
        notifyListeners();
    }
  }

  void _fail(String text) {
    _ws = null;
    _cleanUp();
    error = text;
    _setPhase(Phase.error);
  }

  void _cleanUp() {
    _turnTimer?.cancel();
    _micOpen = false;
    partial = '';
    BrowserAudio.stop();
  }

  void _setPhase(Phase value) {
    phase = value;
    notifyListeners();
  }
}

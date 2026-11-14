/// The Listening module's requests (backend/app/listening/router.py).
library;

import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../core/api.dart';
import '../reading/api.dart' show ReadingContent;

/// The modes' titles, as the backend names them.
String listeningModeTitle(String mode) => const {'test': 'Full test'}[mode] ?? mode;

/// A Listening test that can be taken, for the picker.
typedef ListeningBookTest = ({String book, String bookTitle, String test, int minutes});

Future<List<ListeningBookTest>> fetchListeningTests() async => [
  for (final b in await getJson(http.get(apiUri('/api/listening/books'))) as List)
    for (final t in b['tests'] as List)
      (
        book: b['id'] as String,
        bookTitle: b['title'] as String,
        test: t['test'] as String,
        minutes: t['minutes'] as int,
      ),
];

/// A recording of a test: one for each part, or one for the whole test (part 0).
typedef Recording = ({int part, String file, double seconds});

String recordingUrl(String book, String file) => apiUri('/api/listening/audio/$book/$file').toString();

class ListeningTestState {
  ListeningTestState.fromJson(Map<String, dynamic> json)
    : session = json['session'],
      title = json['title'] ?? '',
      book = json['book'],
      test = json['test'],
      audio = [
        for (final a in json['audio'])
          (part: a['part'] as int, file: a['file'] as String, seconds: (a['seconds'] as num).toDouble()),
      ],
      recordingSeconds = (json['recording_seconds'] as num).toDouble(),
      checkSeconds = (json['check_seconds'] as num).toDouble(),
      questions = json['questions'],
      content = json['content'] == null ? null : ReadingContent.fromJson(json['content']),
      transcripts = [for (final p in json['content']?['parts'] ?? []) List<String>.from(p['transcript'] ?? const [])],
      started = json['started'],
      elapsed = (json['elapsed'] as num).toDouble(),
      answers = Map<String, String>.from(json['answers']),
      secondsLeft = json['seconds_left'],
      finished = json['finished'];

  final String session, title, book, test;
  final List<Recording> audio;
  final double recordingSeconds; // how long the recordings play
  final double checkSeconds; // then this long to check the answers
  final int questions, secondsLeft;
  final ReadingContent? content; // the questions as text (the same groups as in Reading)
  final List<List<String>> transcripts; // what is said in each part: only after the test
  final bool started; // the recording's clock runs
  final double elapsed; // seconds since it started: where the recording is now
  final Map<String, String> answers; // "1" → the answer saved on the server
  final bool finished;
}

Future<ListeningTestState> startListeningTest({String? book, String? test}) async => ListeningTestState.fromJson(
  await getJson(
    http.post(
      apiUri('/api/listening/tests'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'book': ?book, 'test': ?test}),
    ),
  ),
);

Future<ListeningTestState> fetchListeningTest(String id) async =>
    ListeningTestState.fromJson(await getJson(http.get(apiUri('/api/listening/tests/$id'))));

/// Starts the recording's clock (the first time) and says where it is now.
Future<ListeningTestState> playListeningTest(String id) async =>
    ListeningTestState.fromJson(await getJson(http.post(apiUri('/api/listening/tests/$id/play'))));

/// Saves the answers so far; returns the seconds left, or null when the time is up (the server
/// keeps what was saved in time).
Future<int?> saveListeningAnswers(String id, Map<String, String> answers) async {
  final response = await http.put(
    apiUri('/api/listening/tests/$id/answers'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode(answers),
  );
  if (response.statusCode == 409) return null;
  if (response.statusCode != 200) throw Exception('HTTP ${response.statusCode}');
  return jsonDecode(response.body)['seconds_left'];
}

Future<void> finishListeningTest(String id, Map<String, String> answers) => getJson(
  http.post(
    apiUri('/api/listening/tests/$id/finish'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode(answers),
  ),
);

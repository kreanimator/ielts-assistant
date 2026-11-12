/// The Reading module's requests (backend/app/reading/router.py).
library;

import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../core/api.dart';

/// The modes' titles, as the backend names them.
String readingModeTitle(String mode) => const {'test': 'Full test'}[mode] ?? mode;

const readingKinds = {'academic': 'Academic', 'general': 'General Training'};

/// A Reading test in your books, for the picker.
typedef ReadingBookTest = ({String book, String bookTitle, String test, String kind});

Future<List<ReadingBookTest>> fetchReadingTests() async => [
  for (final b in await getJson(http.get(apiUri('/api/reading/books'))) as List)
    for (final t in b['tests'] as List)
      (book: b['id'] as String, bookTitle: b['title'] as String, test: t['test'] as String, kind: t['kind'] as String),
];

/// A page of a test, as the book prints it.
String pagePicture(String book, int page) => apiUri('/api/reading/pages/$book/$page.jpg').toString();

/// A part of a page (a group of questions as printed); `box` in fractions of the page.
String cropPicture(String book, int page, List<double> box) =>
    apiUri('/api/reading/crops/$book/$page.jpg').replace(queryParameters: {'box': box.join(',')}).toString();

/// The test as text, like the computer-delivered test (backend/app/reading/content.py).
class ReadingContent {
  ReadingContent.fromJson(Map<String, dynamic> json)
    : parts = [for (final p in json['parts']) ReadingPartText.fromJson(p)];

  final List<ReadingPartText> parts;
}

class ReadingPartText {
  ReadingPartText.fromJson(Map<String, dynamic> json)
    : part = json['part'],
      first = json['first'],
      last = json['last'],
      pages = List<int>.from(json['pages'] ?? []),
      intro = json['intro'] ?? '',
      passage = [
        for (final b in json['passage'])
          (
            title: b['kind'] == 'title',
            note: b['kind'] == 'note',
            text: b['text'] as String,
            letter: b['letter'] as String?,
          ),
      ],
      groups = [for (final g in json['groups']) QuestionGroup.fromJson(g)];

  final int part, first, last;
  final List<int> pages;
  final String intro;
  final List<({bool title, bool note, String text, String? letter})> passage; // note: "Read the text below ..."
  final List<QuestionGroup> groups;
}

typedef ReadingOption = ({String letter, String text});

List<ReadingOption> _options(dynamic list) => [
  for (final o in list ?? []) (letter: o['letter'] as String, text: (o['text'] ?? '') as String),
];

/// Questions first..last with one kind of control: "tfng", "ynng", "choice", "multi", "match",
/// "gaps" or "notes". When `printed`, their text is shown as the pictures of the page.
class QuestionGroup {
  QuestionGroup.fromJson(Map<String, dynamic> json)
    : first = json['first'],
      last = json['last'],
      type = json['type'],
      printed = json['printed'] ?? false,
      instructions = List<String>.from(json['instructions'] ?? []),
      options = _options(json['options']),
      stem = json['stem'] ?? '',
      questions = [
        for (final q in json['questions'] ?? [])
          (q: q['q'] as int, text: (q['text'] ?? '') as String, options: _options(q['options'])),
      ],
      notes = [for (final line in json['notes'] ?? []) List<Object>.from(line)],
      pictures = [
        for (final p in json['pictures'] ?? [])
          (page: p['page'] as int, box: [for (final v in p['box']) (v as num).toDouble()]),
      ];

  final int first, last;
  final String type, stem;
  final bool printed;
  final List<String> instructions;
  final List<ReadingOption> options;
  final List<({int q, String text, List<ReadingOption> options})> questions;
  final List<List<Object>> notes; // lines of text (String) and gaps (int: the question)
  final List<({int page, List<double> box})> pictures;

  Iterable<int> get numbers sync* {
    for (var q = first; q <= last; q++) {
      yield q;
    }
  }
}

/// Where a passage (Academic) or a section (General Training) starts.
typedef ReadingPart = ({int part, int page});

class ReadingTestState {
  ReadingTestState.fromJson(Map<String, dynamic> json)
    : session = json['session'],
      title = json['title'] ?? '',
      book = json['book'],
      test = json['test'],
      kind = json['kind'],
      pages = List<int>.from(json['pages']),
      parts = [for (final p in json['parts']) (part: p['part'] as int, page: p['page'] as int)],
      sections = [for (final s in json['sections'] ?? []) (first: s[0] as int, last: s[1] as int)],
      questions = json['questions'],
      content = json['content'] == null ? null : ReadingContent.fromJson(json['content']),
      minutes = json['minutes'],
      answers = Map<String, String>.from(json['answers']),
      secondsLeft = json['seconds_left'],
      finished = json['finished'];

  final String session, title, book, test, kind;
  final List<int> pages;
  final List<ReadingPart> parts;
  final List<({int first, int last})> sections; // the questions of each part; empty if unknown
  final int questions, minutes, secondsLeft;
  final Map<String, String> answers; // "1" → the answer saved on the server
  final ReadingContent? content; // the passages and questions as text; null: show the printed pages
  final bool finished;

  /// "Passage" in Academic tests, "Section" in General Training ones.
  String get partName => kind == 'academic' ? 'Passage' : 'Section';
}

Future<ReadingTestState> startReadingTest({String? book, String? test, String? kind}) async {
  final body = {'book': ?book, 'test': ?test, 'kind': ?kind};
  return ReadingTestState.fromJson(
    await getJson(
      http.post(apiUri('/api/reading/tests'), headers: {'Content-Type': 'application/json'}, body: jsonEncode(body)),
    ),
  );
}

Future<ReadingTestState> fetchReadingTest(String id) async =>
    ReadingTestState.fromJson(await getJson(http.get(apiUri('/api/reading/tests/$id'))));

/// Saves the answers so far; returns the seconds left, or null when the time is up (the server
/// keeps what was saved in time).
Future<int?> saveReadingAnswers(String id, Map<String, String> answers) async {
  final response = await http.put(
    apiUri('/api/reading/tests/$id/answers'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode(answers),
  );
  if (response.statusCode == 409) return null;
  if (response.statusCode != 200) throw Exception('HTTP ${response.statusCode}');
  return jsonDecode(response.body)['seconds_left'];
}

Future<void> finishReadingTest(String id, Map<String, String> answers) => getJson(
  http.post(
    apiUri('/api/reading/tests/$id/finish'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode(answers),
  ),
);

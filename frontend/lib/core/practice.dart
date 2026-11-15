import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api.dart';

/// Lessons and exercises for one type of mistake (backend/app/core/practice.py).

/// A type you can practise, with how often you make it and your last result.
class PracticeType {
  PracticeType.fromJson(Map<String, dynamic> json)
    : id = json['id'],
      title = json['title'],
      covers = json['covers'],
      mistakes = json['mistakes'],
      improving = json['improving'],
      units = json['units'],
      last = json['last'] == null ? null : PracticeResult.fromJson(json['last']);

  final String id, title, covers;
  final int mistakes; // of this type in your sessions
  final bool improving;
  final int units; // finished
  final PracticeResult? last;
}

class PracticeResult {
  PracticeResult.fromJson(Map<String, dynamic> json)
    : score = json['score'],
      of = json['of'],
      passed = json['passed'],
      unit = json['unit'],
      date = json['date'] == null ? null : DateTime.parse(json['date']).toLocal();

  final int score, of;
  final bool passed; // enough right to count as practised well
  final String? unit; // the unit's id, in a type's last result
  final DateTime? date;
}

/// One rule of the lesson, with a sentence that breaks it and the same sentence right.
typedef LessonPoint = ({String rule, String wrong, String right});

/// One of your own mistakes of the type, as it was corrected.
typedef OwnMistake = ({String original, String better, String why});

class Exercise {
  Exercise.fromJson(Map<String, dynamic> json)
    : n = json['n'],
      kind = json['kind'],
      sentence = json['sentence'],
      options = List<String>.from(json['options'] ?? const []),
      checked = json.containsKey('right'),
      right = json['right'] ?? false,
      given = json['given'],
      answer = json['answer'],
      why = json['why'] ?? '';

  final int n;
  final String kind; // 'choice': fill the gap with one of [options]; 'fix': write the sentence correctly
  final String sentence;
  final List<String> options;
  // Once the unit is checked:
  final bool checked, right;
  final Object? given; // what you answered: an option's index, or your sentence
  final Object? answer; // the right option's index, or the correct sentence
  final String why;
}

class PracticeUnit {
  PracticeUnit.fromJson(Map<String, dynamic> json)
    : id = json['id'],
      type = json['type'],
      title = json['title'],
      covers = json['covers'],
      intro = json['lesson']['intro'],
      points = [
        for (final p in json['lesson']['points'])
          (rule: p['rule'] as String, wrong: p['wrong'] as String, right: p['right'] as String),
      ],
      yours = [
        for (final e in json['lesson']['yours'])
          (original: e['original'] as String, better: e['better'] as String, why: e['why'] as String),
      ],
      exercises = [for (final e in json['exercises']) Exercise.fromJson(e)],
      result = json['result'] == null ? null : PracticeResult.fromJson(json['result']);

  final String id, type, title, covers, intro;
  final List<LessonPoint> points;
  final List<OwnMistake> yours;
  final List<Exercise> exercises;
  final PracticeResult? result; // null until the answers are checked
}

/// The types to practise, the ones you make most mistakes in first.
Future<List<PracticeType>> fetchPracticeTypes() async => [
  for (final t in (await getJson(http.get(apiUri('/api/practice'))))['types']) PracticeType.fromJson(t),
];

Future<dynamic> _post(String path, Map<String, dynamic> body) =>
    getJson(http.post(apiUri(path), headers: {'Content-Type': 'application/json'}, body: jsonEncode(body)));

/// Writes a new unit for [type]: takes about half a minute.
Future<PracticeUnit> startPracticeUnit(String type) async =>
    PracticeUnit.fromJson(await _post('/api/practice/units', {'type': type}));

Future<PracticeUnit> fetchPracticeUnit(String id) async =>
    PracticeUnit.fromJson(await getJson(http.get(apiUri('/api/practice/units/$id'))));

/// [answers]: exercise number → the chosen option's index, or the sentence you wrote.
Future<PracticeUnit> checkPracticeUnit(String id, Map<int, Object> answers) async => PracticeUnit.fromJson(
  await _post('/api/practice/units/$id/answers', {
    'answers': {for (final a in answers.entries) '${a.key}': a.value},
  }),
);

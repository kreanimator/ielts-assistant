/// The Writing module's requests (backend/app/writing/router.py).
library;

import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../core/api.dart';

/// The modes' titles, as the backend names them (for pages opened outside the dashboard).
String writingModeTitle(String mode) => const {'task1': 'Task 1 · Letter', 'task2': 'Task 2 · Essay'}[mode] ?? mode;

/// A task to practise, as the backend gives it; sent back unchanged with the answer.
class WritingTask {
  WritingTask.fromJson(this.json)
    : task = json['task'],
      kind = json['kind'],
      prompt = json['prompt'],
      bullets = List<String>.from(json['bullets'] ?? []),
      begin = json['begin'] ?? '',
      minutes = json['minutes'],
      words = json['words'],
      title = json['title'],
      fromBook = json['source'] == 'book';

  final Map<String, dynamic> json;
  final int task, minutes, words;
  final String kind, prompt, begin, title;
  final List<String> bullets;
  final bool fromBook;
}

/// A test in your books with its tasks, for the picker.
typedef BookTest = ({String book, String bookTitle, String test, bool hasTask1, bool hasTask2});

class WritingOptions {
  WritingOptions.fromJson(Map<String, dynamic> json)
    : letterTypes = List<String>.from(json['letter_types']),
      essayTypes = Map<String, String>.from(json['essay_types']),
      bookTasks = {for (final e in (json['book_tasks'] as Map).entries) int.parse(e.key): e.value as int};

  final List<String> letterTypes;
  final Map<String, String> essayTypes; // type → the question it asks
  final Map<int, int> bookTasks; // task number → how many your books have
}

Future<WritingOptions> fetchWritingOptions() async =>
    WritingOptions.fromJson(await getJson(http.get(apiUri('/api/writing/options'))));

Future<List<BookTest>> fetchBookTests() async => [
  for (final b in await getJson(http.get(apiUri('/api/writing/books'))))
    for (final t in b['tests'])
      (
        book: b['id'] as String,
        bookTitle: b['title'] as String,
        test: t['test'] as String,
        hasTask1: t['task1'] != null && t['type'] == 'general',
        hasTask2: t['task2'] != null,
      ),
];

/// From your books ([book] and [test], or a random one), or a new one written by the LLM.
Future<WritingTask> fetchTask({
  required int task,
  required bool fromBook,
  String? book,
  String? test,
  String? topic,
  String? kind,
}) async {
  final query = {
    'task': '$task',
    'source': fromBook ? 'book' : 'new',
    'book': ?book,
    'test': ?test,
    if (topic != null && topic.trim().isNotEmpty) 'topic': topic.trim(),
    'kind': ?kind,
  };
  return WritingTask.fromJson(await getJson(http.get(apiUri('/api/writing/task').replace(queryParameters: query))));
}

/// Saves the answer as a session; returns its id (the report is written when the session opens).
Future<String> saveAnswer(WritingTask task, String answer, int seconds) async {
  final reply = await getJson(
    http.post(
      apiUri('/api/writing/answers'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'task': task.json, 'answer': answer, 'seconds': seconds}),
    ),
  );
  return reply['session'];
}

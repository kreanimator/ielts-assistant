import 'dart:convert';

import 'package:http/http.dart' as http;

/// The backend's address. Empty means the page's own origin (the backend serves
/// the built app). For `flutter run`, pass --dart-define=BACKEND=http://127.0.0.1:8000
const _backend = String.fromEnvironment('BACKEND');

Uri get _base => _backend.isEmpty ? Uri.base : Uri.parse(_backend);

Uri apiUri(String path) => Uri(scheme: _base.scheme, host: _base.host, port: _base.port, path: path);

Uri get sessionUri =>
    Uri(scheme: _base.scheme == 'https' ? 'wss' : 'ws', host: _base.host, port: _base.port, path: '/ws');

class Voice {
  Voice.fromJson(Map<String, dynamic> json)
    : id = json['id'],
      name = json['name'],
      accent = json['accent'],
      gender = json['gender'];

  final String id, name, accent, gender;

  String get label => '$name · $accent $gender';
}

class Mode {
  Mode.fromJson(Map<String, dynamic> json) : id = json['id'], title = json['title'], description = json['description'];

  final String id, title, description;
}

class Options {
  Options.fromJson(Map<String, dynamic> json)
    : model = json['model'],
      voices = [for (final v in json['voices']) Voice.fromJson(v)],
      modes = [for (final m in json['modes']) Mode.fromJson(m)];

  final String model;
  final List<Voice> voices;
  final List<Mode> modes;
}

Future<Options> fetchOptions() async {
  final response = await http.get(apiUri('/api/options'));
  if (response.statusCode != 200) throw Exception('HTTP ${response.statusCode}');
  return Options.fromJson(jsonDecode(response.body));
}

/// One Speaking test imported from your books: its topics, for the picker.
class BookTest {
  BookTest.fromJson(this.bookId, this.bookTitle, Map<String, dynamic> json)
    : number = json['test'],
      part1 = List<String>.from(json['part1']),
      part2 = json['part2'],
      part3 = List<String>.from(json['part3']);

  final String bookId, bookTitle, part2;
  final int number;
  final List<String> part1, part3;

  String get key => '$bookId#$number';
  String get label => '$bookTitle · Test $number';

  /// What this test gives the chosen mode.
  String outline(String mode) => switch (mode) {
    'part1' => 'Topics: ${part1.join(', ')}',
    'part2' => 'Cue card: $part2',
    'part3' => 'Topics: ${part3.join(', ')}',
    _ => 'Part 1: ${part1.join(', ')}\nPart 2: $part2\nPart 3: ${part3.join(', ')}',
  };
}

/// All imported tests, book by book (empty until you run `make books`).
Future<List<BookTest>> fetchBookTests() async {
  final response = await http.get(apiUri('/api/books'));
  if (response.statusCode != 200) throw Exception('HTTP ${response.statusCode}');
  return [
    for (final book in jsonDecode(utf8.decode(response.bodyBytes)))
      for (final test in book['tests']) BookTest.fromJson(book['id'], book['title'], test),
  ];
}

/// A topic to talk about: from the app's A-Z list or from your books.
class Topic {
  Topic.fromJson(Map<String, dynamic> json) : name = json['name'], fromBooks = json['source'] == 'books';

  final String name;
  final bool fromBooks;

  String get letter => name.substring(0, 1).toUpperCase();
}

Future<List<Topic>> fetchTopics() async {
  final response = await http.get(apiUri('/api/topics'));
  if (response.statusCode != 200) throw Exception('HTTP ${response.statusCode}');
  return [for (final t in jsonDecode(utf8.decode(response.bodyBytes))) Topic.fromJson(t)];
}

/// A drill: one sound to repeat, or one structure to use in answers.
class Drill {
  Drill.fromJson(Map<String, dynamic> json, this.reason)
    : id = json['id'],
      kind = json['kind'],
      title = json['title'],
      description = json['description'];

  final String id, kind, title, description;
  final String? reason; // why your past sessions suggest it

  bool get isSound => kind == 'sound';
}

/// All drills, the ones your past sessions suggest first.
Future<List<Drill>> fetchDrills() async {
  final response = await http.get(apiUri('/api/drills'));
  if (response.statusCode != 200) throw Exception('HTTP ${response.statusCode}');
  final json = jsonDecode(utf8.decode(response.bodyBytes));
  final reasons = {for (final s in json['suggested']) s['id'] as String: s['reason'] as String};
  final drills = [for (final d in json['drills']) Drill.fromJson(d, reasons[d['id']])];
  return [...drills.where((d) => d.reason != null), ...drills.where((d) => d.reason == null)];
}

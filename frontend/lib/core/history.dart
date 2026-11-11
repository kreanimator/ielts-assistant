import 'package:http/http.dart' as http;

import 'api.dart';

/// Past sessions of every module and their band reports (backend/app/core/history.py).

class Criterion {
  Criterion.fromJson(Map<String, dynamic> json)
    : id = json['id'],
      name = json['name'],
      band = (json['band'] as num).toDouble(),
      summary = json['summary'],
      evidence = List<String>.from(json['evidence']);

  final String id, name, summary;
  final double band;
  final List<String> evidence;
}

class Report {
  Report.fromJson(Map<String, dynamic> json)
    : enough = json['enough'],
      note = json['note'],
      overall = (json['overall'] as num?)?.toDouble(),
      criteria = [for (final c in json['criteria'] ?? []) Criterion.fromJson(c)],
      strengths = List<String>.from(json['strengths'] ?? []),
      priorities = List<String>.from(json['priorities'] ?? []);

  final bool enough; // false: too little speech for band estimates, see [note]
  final String? note;
  final double? overall;
  final List<Criterion> criteria;
  final List<String> strengths, priorities;

  double? band(String criterion) {
    for (final c in criteria) {
      if (c.id == criterion) return c.band;
    }
    return null;
  }
}

class StoredSession {
  StoredSession.fromJson(Map<String, dynamic> json)
    : id = json['id'],
      startedAt = DateTime.parse(json['started_at']).toLocal(),
      module = json['module'] ?? 'speaking',
      mode = json['mode'],
      topic = json['topic'],
      voice = json['voice'],
      answerCount = json['answers'],
      report = json['report'] == null ? null : Report.fromJson(json['report']),
      messageJson = List<Map<String, dynamic>>.from(json['messages'] ?? []);

  final String id, module, mode, voice;
  final String? topic;
  final DateTime startedAt;
  final int answerCount;
  Report? report;
  final List<Map<String, dynamic>> messageJson; // read by the module; empty in the session list

  /// "Part 1 · Interview: Travel", given the mode's title.
  String title(String modeTitle) => topic == null ? modeTitle : '$modeTitle: $topic';
}

/// Newest first: every module's, or only [module]'s.
Future<List<StoredSession>> fetchSessions({String? module}) async => [
  for (final s in await getJson(
    http.get(apiUri('/api/sessions').replace(queryParameters: module == null ? null : {'module': module})),
  ))
    StoredSession.fromJson(s),
];

Future<StoredSession> fetchSession(String id) async =>
    StoredSession.fromJson(await getJson(http.get(apiUri('/api/sessions/$id'))));

/// Writes the report if there is none yet (takes 10-30 s), or a new one with [again].
Future<Report> writeReport(String id, {bool again = false}) async {
  final uri = apiUri('/api/sessions/$id/report').replace(queryParameters: again ? {'again': 'true'} : null);
  return Report.fromJson(await getJson(http.post(uri)));
}

Future<void> deleteSession(String id) => getJson(http.delete(apiUri('/api/sessions/$id')));

Uri answerAudioUri(String id, int answer) => apiUri('/api/sessions/$id/answers/$answer.wav');

import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api.dart';
import 'session.dart';

/// Past sessions and their reports (backend/app/history.py).

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
      mode = json['mode'],
      topic = json['topic'],
      voice = json['voice'],
      answerCount = json['answers'],
      report = json['report'] == null ? null : Report.fromJson(json['report']),
      messages = [for (final m in json['messages'] ?? []) Message.fromStored(m)];

  final String id, mode, voice;
  final String? topic;
  final DateTime startedAt;
  final int answerCount;
  Report? report;
  final List<Message> messages; // empty in the session list
}

Future<List<StoredSession>> fetchSessions() async => [
  for (final s in await _json(http.get(apiUri('/api/sessions')))) StoredSession.fromJson(s),
];

Future<StoredSession> fetchSession(String id) async =>
    StoredSession.fromJson(await _json(http.get(apiUri('/api/sessions/$id'))));

/// Writes the report if there is none yet (takes 10-30 s), or a new one with [again].
Future<Report> writeReport(String id, {bool again = false}) async {
  final uri = apiUri('/api/sessions/$id/report').replace(queryParameters: again ? {'again': 'true'} : null);
  return Report.fromJson(await _json(http.post(uri)));
}

Future<void> deleteSession(String id) => _json(http.delete(apiUri('/api/sessions/$id')));

Uri answerAudioUri(String id, int answer) => apiUri('/api/sessions/$id/answers/$answer.wav');

Future<dynamic> _json(Future<http.Response> request) async {
  final response = await request;
  if (response.statusCode != 200) throw Exception('HTTP ${response.statusCode}');
  return jsonDecode(utf8.decode(response.bodyBytes));
}

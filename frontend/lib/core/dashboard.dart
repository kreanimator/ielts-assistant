import 'package:http/http.dart' as http;

import 'api.dart';
import 'widgets/progress_chart.dart';

/// The home screen's numbers (backend/app/core/dashboard.py).

class Skill {
  Skill.fromJson(Map<String, dynamic> json)
    : id = json['id'],
      title = json['title'],
      available = json['available'],
      modes = Map<String, String>.from(json['modes']),
      band = (json['band'] as num?)?.toDouble(),
      fromSessions = json['from_sessions'],
      latest = (json['latest'] as num?)?.toDouble(),
      sessions = json['sessions'],
      unscored = json['unscored'],
      lastPractised = json['last_practised'] == null ? null : DateTime.parse(json['last_practised']).toLocal(),
      progress = [
        for (final p in json['progress'])
          (date: DateTime.parse(p['date']).toLocal(), band: (p['band'] as num).toDouble()),
      ];

  final String id, title;
  final bool available; // false: coming soon
  final Map<String, String> modes; // mode id → title
  final double? band; // the average of the last few sessions with a band
  final double? latest;
  final int fromSessions, sessions, unscored;
  final DateTime? lastPractised;
  final List<BandPoint> progress; // oldest first

  String modeTitle(String mode) => modes[mode] ?? mode;
}

class Dashboard {
  Dashboard.fromJson(Map<String, dynamic> json)
    : overall = (json['overall']['band'] as num?)?.toDouble(),
      skillsCounted = json['overall']['skills'],
      skillCount = json['overall']['of'],
      recent = json['recent'],
      skills = [for (final s in json['skills']) Skill.fromJson(s)];

  final double? overall;
  final int skillsCounted, skillCount; // the overall band averages skillsCounted of skillCount skills
  final int recent; // a skill's band averages up to this many sessions
  final List<Skill> skills; // in test order: Listening, Reading, Writing, Speaking

  Skill? skill(String id) => skills.where((s) => s.id == id).firstOrNull;
}

Future<Dashboard> fetchDashboard() async => Dashboard.fromJson(await getJson(http.get(apiUri('/api/dashboard'))));

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

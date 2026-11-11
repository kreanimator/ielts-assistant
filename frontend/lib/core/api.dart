/// The backend's address and JSON requests, shared by every module.
library;

import 'dart:convert';

import 'package:http/http.dart' as http;

/// Empty means the page's own origin (the backend serves the built app). For
/// `flutter run`, pass --dart-define=BACKEND=http://127.0.0.1:8000
const _backend = String.fromEnvironment('BACKEND');

Uri get _base => _backend.isEmpty ? Uri.base : Uri.parse(_backend);

Uri apiUri(String path) => Uri(scheme: _base.scheme, host: _base.host, port: _base.port, path: path);

Uri wsUri(String path) =>
    Uri(scheme: _base.scheme == 'https' ? 'wss' : 'ws', host: _base.host, port: _base.port, path: path);

/// The decoded JSON of a request's response; throws unless it is 200 OK.
Future<dynamic> getJson(Future<http.Response> request) async {
  final response = await request;
  if (response.statusCode != 200) throw Exception('HTTP ${response.statusCode}');
  return jsonDecode(utf8.decode(response.bodyBytes));
}

/// The backend's address, shared by every module.
library;

/// Empty means the page's own origin (the backend serves the built app). For
/// `flutter run`, pass --dart-define=BACKEND=http://127.0.0.1:8000
const _backend = String.fromEnvironment('BACKEND');

Uri get _base => _backend.isEmpty ? Uri.base : Uri.parse(_backend);

Uri apiUri(String path) => Uri(scheme: _base.scheme, host: _base.host, port: _base.port, path: path);

Uri wsUri(String path) =>
    Uri(scheme: _base.scheme == 'https' ? 'wss' : 'ws', host: _base.host, port: _base.port, path: path);

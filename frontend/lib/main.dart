import 'package:flutter/material.dart';

import 'api.dart';
import 'session.dart';
import 'widgets/corrections_panel.dart';
import 'widgets/dialogue_panel.dart';
import 'widgets/setup_panel.dart';

void main() => runApp(const App());

class App extends StatelessWidget {
  const App({super.key});

  ThemeData _theme(Brightness brightness) => ThemeData(
        fontFamily: 'Roboto',
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF3F51B5), brightness: brightness),
      );

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'IELTS Speaking Assistant',
        debugShowCheckedModeBanner: false,
        theme: _theme(Brightness.light),
        darkTheme: _theme(Brightness.dark),
        home: const HomePage(),
      );
}

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  final _session = Session();
  final _topic = TextEditingController();
  Options? _options;
  String? _loadError;
  String _mode = 'part1';
  String _voice = 'bf_emma';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loadError = null);
    try {
      final options = await fetchOptions();
      setState(() {
        _options = options;
        if (!options.voices.any((v) => v.id == _voice)) _voice = options.voices.first.id;
        if (!options.modes.any((m) => m.id == _mode)) _mode = options.modes.first.id;
      });
    } catch (_) {
      setState(() => _loadError = 'Cannot reach the backend at ${apiUri('/')}.\nStart it with `make run`.');
    }
  }

  @override
  void dispose() {
    _session.dispose();
    _topic.dispose();
    super.dispose();
  }

  void _start() {
    final topic = _topic.text.trim();
    _session.start(mode: _mode, voice: _voice, topic: topic.isEmpty ? null : topic);
  }

  @override
  Widget build(BuildContext context) {
    final options = _options;
    if (options == null) return Scaffold(body: Center(child: _loading()));

    final voice = options.voices.firstWhere((v) => v.id == _voice);
    final dialogue = DialoguePanel(
      session: _session,
      examinerName: voice.name,
      female: voice.gender == 'female',
      onStart: _start,
    );
    final setup = ListenableBuilder(
      listenable: _session,
      builder: (context, _) => SetupPanel(
        options: options,
        mode: _mode,
        voice: _voice,
        topic: _topic,
        enabled: !_session.active,
        onMode: (id) => setState(() => _mode = id),
        onVoice: (id) => setState(() => _voice = id),
      ),
    );

    return LayoutBuilder(builder: (context, constraints) {
      if (constraints.maxWidth < 760) {
        // Phone width: setup in a drawer.
        return Scaffold(
          appBar: AppBar(title: const Text('IELTS Speaking')),
          drawer: Drawer(child: SafeArea(child: setup)),
          body: SafeArea(child: dialogue),
        );
      }
      return Scaffold(
        body: SafeArea(
          child: Row(
            children: [
              SizedBox(width: 320, child: setup),
              const VerticalDivider(width: 1),
              Expanded(child: dialogue),
              if (constraints.maxWidth >= 1100) ...[
                const VerticalDivider(width: 1),
                const SizedBox(width: 320, child: CorrectionsPanel()),
              ],
            ],
          ),
        ),
      );
    });
  }

  Widget _loading() {
    if (_loadError == null) return const CircularProgressIndicator();
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Padding(padding: const EdgeInsets.all(16), child: Text(_loadError!, textAlign: TextAlign.center)),
        FilledButton(onPressed: _load, child: const Text('Try again')),
      ],
    );
  }
}

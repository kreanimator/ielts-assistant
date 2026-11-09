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
  bool _live = true; // show corrections during the session

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
    final corrections = CorrectionsPanel(session: _session, live: _live);
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
        liveCorrections: _live,
        onLiveCorrections: (on) => setState(() => _live = on),
      ),
    );
    DialoguePanel dialogue({Widget? headerAction}) => DialoguePanel(
          session: _session,
          examinerName: voice.name,
          female: voice.gender == 'female',
          onStart: _start,
          liveCorrections: _live,
          headerAction: headerAction,
        );

    return LayoutBuilder(builder: (context, constraints) {
      final wide = constraints.maxWidth >= 1100;
      final phone = constraints.maxWidth < 760;
      // Without room for the side panel, corrections open from a button.
      final body = wide ? dialogue() : dialogue(headerAction: _CorrectionsButton(session: _session, live: _live));
      return Scaffold(
        appBar: phone ? AppBar(title: const Text('IELTS Speaking')) : null,
        drawer: phone ? Drawer(child: SafeArea(child: setup)) : null,
        endDrawer: wide ? null : Drawer(width: 360, child: SafeArea(child: corrections)),
        body: SafeArea(
          child: phone
              ? body
              : Row(
                  children: [
                    SizedBox(width: 320, child: setup),
                    const VerticalDivider(width: 1),
                    Expanded(child: body),
                    if (wide) ...[
                      const VerticalDivider(width: 1),
                      SizedBox(width: 340, child: corrections),
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

/// Opens the corrections drawer; the badge counts corrections you can see.
class _CorrectionsButton extends StatelessWidget {
  const _CorrectionsButton({required this.session, required this.live});

  final Session session;
  final bool live;

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: session,
        builder: (context, _) {
          final count = live || !session.active ? session.correctionCount : 0;
          return IconButton(
            tooltip: 'Corrections',
            onPressed: () => Scaffold.of(context).openEndDrawer(),
            icon: Badge(label: Text('$count'), isLabelVisible: count > 0, child: const Icon(Icons.spellcheck)),
          );
        },
      );
}

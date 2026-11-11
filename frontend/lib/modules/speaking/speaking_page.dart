import 'dart:math';

import 'package:flutter/material.dart';

import 'api.dart';
import 'session.dart';
import 'speaking.dart';
import 'widgets/corrections_panel.dart';
import 'widgets/dialogue_panel.dart';
import 'widgets/setup_panel.dart';

/// The Speaking module: choose a mode and talk to the examiner.
class SpeakingPage extends StatefulWidget {
  const SpeakingPage({super.key});

  @override
  State<SpeakingPage> createState() => _SpeakingPageState();
}

class _SpeakingPageState extends State<SpeakingPage> {
  final _session = Session();
  final _topic = TextEditingController();
  Options? _options;
  List<BookTest> _tests = []; // imported from your books
  List<Topic> _topics = [];
  List<Drill> _drills = [];
  List<EslTopic> _cards = []; // the "By letter" topic cards
  String? _card; // EslTopic.slug: the card dealt for the chosen letter
  String _level = 'mixed';
  String? _drill; // Drill.id
  String? _test; // BookTest.key, or null for questions made up by the examiner
  String? _loadError;
  String _mode = 'part1';
  String _voice = 'bf_emma';
  bool _live = true; // show corrections during the session

  @override
  void initState() {
    super.initState();
    _session.onEnded = _showReport;
    _load();
  }

  String _modeTitle(String id) => _options?.modes.where((m) => m.id == id).firstOrNull?.title ?? id;

  void _showReport(String id) => openSpeakingSession(context, id, _modeTitle);

  void _showHistory() => openSpeakingHistory(context, _modeTitle);

  /// Back to the dashboard (not during a session: leaving would cut it off).
  void _home() => Navigator.popUntil(context, (route) => route.isFirst); // also closes the drawer on phones

  Future<void> _load() async {
    setState(() => _loadError = null);
    try {
      final options = await fetchOptions();
      final tests = await fetchBookTests();
      final topics = await fetchTopics();
      final drills = await fetchDrills();
      final cards = await fetchEslTopics();
      setState(() {
        _cards = cards;
        _drills = drills;
        _drill ??= drills.firstOrNull?.id;
        _tests = tests;
        _topics = topics;
        _options = options;
        if (!options.voices.any((v) => v.id == _voice)) _voice = options.voices.first.id;
        if (!options.modes.any((m) => m.id == _mode)) _mode = options.modes.first.id;
      });
    } catch (_) {
      setState(() => _loadError = 'Cannot reach the backend at ${apiUri('/')}.\nStart it with `make start`.');
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
    _session.start(
      mode: _mode,
      voice: _voice,
      topic: topic.isEmpty ? null : topic,
      test: _chosenTest,
      drill: _mode == 'drill' ? _drill : null,
      esl: _mode == 'letter' ? (_card ?? (_cards.isEmpty ? null : _cards[Random().nextInt(_cards.length)].slug)) : null,
      level: _level,
    );
  }

  /// The chosen book test, when the mode can use one.
  BookTest? get _chosenTest {
    if (_mode == 'free' || _mode == 'drill' || _mode == 'letter') return null;
    return _tests.where((t) => t.key == _test).firstOrNull;
  }

  @override
  Widget build(BuildContext context) {
    final options = _options;
    if (options == null) return Scaffold(body: Center(child: _loading()));

    final voice = options.voices.firstWhere((v) => v.id == _voice);
    final live = _live && _mode != 'exam'; // the full exam shows feedback only at the end
    final corrections = CorrectionsPanel(session: _session, live: live);
    final setup = ListenableBuilder(
      listenable: _session,
      builder: (context, _) => SetupPanel(
        options: options,
        mode: _mode,
        voice: _voice,
        topic: _topic,
        tests: _tests,
        topics: _topics,
        drills: _drills,
        drill: _drills.where((d) => d.id == _drill).firstOrNull,
        onDrill: (id) => setState(() => _drill = id),
        cards: _cards,
        card: _cards.where((c) => c.slug == _card).firstOrNull,
        onCard: (slug) => setState(() => _card = slug),
        level: _level,
        onLevel: (level) => setState(() => _level = level),
        test: _chosenTest,
        onTest: (key) => setState(() => _test = key),
        enabled: !_session.active && _session.phase != Phase.ending,
        onHistory: _showHistory,
        onHome: _home,
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
      liveCorrections: live,
      headerAction: headerAction,
    );

    return LayoutBuilder(
      builder: (context, constraints) {
        final wide = constraints.maxWidth >= 1100;
        final phone = constraints.maxWidth < 760;
        // Without room for the side panel, corrections open from a button.
        final body = wide
            ? dialogue()
            : dialogue(
                headerAction: _CorrectionsButton(session: _session, live: live),
              );
        return Scaffold(
          appBar: phone
              ? AppBar(
                  title: const Text('IELTS Speaking'),
                  actions: [
                    ListenableBuilder(
                      listenable: _session,
                      builder: (context, _) => IconButton(
                        tooltip: 'Home',
                        onPressed: _session.active ? null : _home,
                        icon: const Icon(Icons.home_outlined),
                      ),
                    ),
                    IconButton(tooltip: 'History', onPressed: _showHistory, icon: const Icon(Icons.history)),
                  ],
                )
              : null,
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
                      if (wide) ...[const VerticalDivider(width: 1), SizedBox(width: 340, child: corrections)],
                    ],
                  ),
          ),
        );
      },
    );
  }

  Widget _loading() {
    if (_loadError == null) return const CircularProgressIndicator();
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Padding(
          padding: const EdgeInsets.all(16),
          child: Text(_loadError!, textAlign: TextAlign.center),
        ),
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

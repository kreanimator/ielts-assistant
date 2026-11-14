import 'package:flutter/material.dart';

import 'api.dart';
import 'pages/listening_session_page.dart';
import 'pages/listening_test_page.dart';

/// Listening: choose a test from your books and take it, or continue the test in progress.
class ListeningPage extends StatefulWidget {
  const ListeningPage({super.key});

  @override
  State<ListeningPage> createState() => _ListeningPageState();
}

class _ListeningPageState extends State<ListeningPage> {
  List<ListeningBookTest>? _tests;
  String? _error;
  ListeningBookTest? _test; // null: a random one
  bool _starting = false;
  ListeningTestState? _activeTest; // a test started before (in progress, or ended while away)

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final tests = await fetchListeningTests();
      setState(() => _tests = tests);
      await _refreshActive();
    } catch (e) {
      setState(() => _error = 'Could not reach the backend ($e).');
    }
  }

  Future<void> _refreshActive() async {
    final active = rememberedListeningTest();
    ListeningTestState? state;
    if (active != null) {
      try {
        state = await fetchListeningTest(active);
      } catch (_) {
        rememberListeningTest(null); // deleted, or another database
      }
    }
    if (mounted) setState(() => _activeTest = state);
  }

  Future<void> _start() async {
    setState(() => _starting = true);
    try {
      final state = await startListeningTest(book: _test?.book, test: _test?.test);
      if (mounted) await _open(state);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('No test ($e).')));
    } finally {
      if (mounted) setState(() => _starting = false);
    }
  }

  Future<void> _open(ListeningTestState state) async {
    if (state.finished) {
      rememberListeningTest(null);
      setState(() => _activeTest = null);
      await Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => ListeningSessionPage(id: state.session, modeTitle: listeningModeTitle),
        ),
      );
      return;
    }
    await Navigator.push(context, MaterialPageRoute(builder: (_) => ListeningTestPage(state: state)));
    await _refreshActive(); // back from the test: its recording goes on, or it was handed in
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Listening')),
      body: _setup(context),
    );
  }

  Widget _setup(BuildContext context) {
    final theme = Theme.of(context);
    final tests = _tests;
    if (tests == null) {
      return Center(child: _error == null ? const CircularProgressIndicator() : Text(_error!));
    }
    final active = _activeTest;
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 640),
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (active != null)
              Card(
                margin: const EdgeInsets.only(bottom: 16),
                color: theme.colorScheme.tertiaryContainer,
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        active.finished ? 'Your test has ended' : 'Test in progress',
                        style: theme.textTheme.titleMedium,
                      ),
                      Text(
                        active.finished
                            ? 'The recording ended while you were away. What was saved has been handed in.'
                            : active.started
                            ? '${active.title}: ${_clockText(active.secondsLeft)} left. The recording keeps '
                                  'running: what plays while you are away is not played again.'
                            : '${active.title}: not started yet.',
                      ),
                      const SizedBox(height: 8),
                      FilledButton(
                        onPressed: () => _open(active),
                        child: Text(active.finished ? 'See the result' : 'Continue the test'),
                      ),
                    ],
                  ),
                ),
              ),
            if (tests.isEmpty)
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Text(
                    'No Listening tests yet. A test needs its recording (make listening-books, with the '
                    'folder of your books\' CDs as audio files) and its questions as text (make web-tests). '
                    'The README says how.',
                    style: theme.textTheme.bodyMedium,
                  ),
                ),
              )
            else ...[
              DropdownButtonFormField<ListeningBookTest?>(
                initialValue: _test,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Test', border: OutlineInputBorder()),
                items: [
                  const DropdownMenuItem(value: null, child: Text('Any test (random)')),
                  for (final t in tests)
                    DropdownMenuItem(value: t, child: Text('${t.bookTitle} · Test ${t.test} · ${t.minutes} min')),
                ],
                onChanged: (t) => setState(() => _test = t),
              ),
              const SizedBox(height: 20),
              Text(
                'Four recordings and 40 questions, about 30 minutes. As in the real test, each recording '
                'plays once: it cannot be paused or played again. When it ends you have two minutes to '
                'check your answers. Then each answer is marked with the key, and the score gives your '
                'band on the official table. Use headphones.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: 12),
              Align(
                alignment: Alignment.centerLeft,
                child: FilledButton.icon(
                  onPressed: _starting || (active != null && !active.finished) ? null : _start,
                  icon: _starting
                      ? const SizedBox.square(dimension: 18, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.headphones_outlined),
                  label: const Text('Open the test'),
                ),
              ),
              if (active != null && !active.finished)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text('Finish the test in progress first.', style: theme.textTheme.bodySmall),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

/// 1740 → "29:00".
String _clockText(int seconds) => '${seconds ~/ 60}:${(seconds % 60).toString().padLeft(2, '0')}';

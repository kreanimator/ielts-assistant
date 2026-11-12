import 'package:flutter/material.dart';

import 'api.dart';
import 'pages/reading_session_page.dart';
import 'pages/reading_test_page.dart';

/// Reading: choose a test from your books (Academic or General Training) and take it in 60
/// minutes, or continue the test in progress.
class ReadingPage extends StatefulWidget {
  const ReadingPage({super.key});

  @override
  State<ReadingPage> createState() => _ReadingPageState();
}

class _ReadingPageState extends State<ReadingPage> {
  List<ReadingBookTest>? _tests;
  String? _error;
  String _kind = 'academic';
  ReadingBookTest? _test; // null: a random one
  bool _starting = false;
  ReadingTestState? _activeTest; // a test started before (in progress, or ended while away)

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final tests = await fetchReadingTests();
      setState(() {
        _tests = tests;
        if (!tests.any((t) => t.kind == _kind) && tests.isNotEmpty) _kind = tests.first.kind;
      });
      await _refreshActive();
    } catch (e) {
      setState(() => _error = 'Could not reach the backend ($e).');
    }
  }

  Future<void> _refreshActive() async {
    final active = rememberedReadingTest();
    ReadingTestState? state;
    if (active != null) {
      try {
        state = await fetchReadingTest(active);
      } catch (_) {
        rememberReadingTest(null); // deleted, or another database
      }
    }
    if (mounted) setState(() => _activeTest = state);
  }

  Future<void> _start() async {
    setState(() => _starting = true);
    try {
      final test = _test;
      final state = await startReadingTest(book: test?.book, test: test?.test, kind: test == null ? _kind : null);
      if (mounted) await _open(state);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('No test ($e).')));
    } finally {
      if (mounted) setState(() => _starting = false);
    }
  }

  Future<void> _open(ReadingTestState state) async {
    if (state.finished) {
      rememberReadingTest(null);
      setState(() => _activeTest = null);
      await Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => ReadingSessionPage(id: state.session, modeTitle: readingModeTitle),
        ),
      );
      return;
    }
    await Navigator.push(context, MaterialPageRoute(builder: (_) => ReadingTestPage(state: state)));
    await _refreshActive(); // back from the test: it may go on (the clock runs on the server) or be handed in
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Reading')),
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
    final ofKind = [
      for (final t in tests)
        if (t.kind == _kind) t,
    ];
    int count(String kind) => tests.where((t) => t.kind == kind).length;
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
                            ? 'The time ran out while you were away. What was saved has been handed in.'
                            : '${active.title}: ${_clockText(active.secondsLeft)} left. The clock keeps running.',
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
                    'No Reading tests yet. Import your own IELTS books with make books: their Reading '
                    'tests appear here as the books print them, marked with their answer keys.',
                    style: theme.textTheme.bodyMedium,
                  ),
                ),
              )
            else ...[
              Text('Module', style: theme.textTheme.titleMedium),
              const SizedBox(height: 8),
              SegmentedButton<String>(
                showSelectedIcon: false,
                segments: [
                  for (final MapEntry(key: kind, value: name) in readingKinds.entries)
                    ButtonSegment(value: kind, label: Text('$name (${count(kind)})'), enabled: count(kind) > 0),
                ],
                selected: {_kind},
                onSelectionChanged: (s) => setState(() {
                  _kind = s.first;
                  _test = null;
                }),
              ),
              const SizedBox(height: 4),
              Text(
                _kind == 'academic'
                    ? 'Three long passages from books, journals and newspapers.'
                    : 'Three sections: everyday notices and adverts, work texts, then one longer text.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: 20),
              DropdownButtonFormField<ReadingBookTest?>(
                key: ValueKey(_kind),
                initialValue: _test,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Test', border: OutlineInputBorder()),
                items: [
                  const DropdownMenuItem(value: null, child: Text('Any test (random)')),
                  for (final t in ofKind) DropdownMenuItem(value: t, child: Text('${t.bookTitle} · Test ${t.test}')),
                ],
                onChanged: (t) => setState(() => _test = t),
              ),
              const SizedBox(height: 20),
              Text(
                '40 questions in 60 minutes, timed like the real test: the clock runs on the server and '
                'your answers are handed in when it stops. Then each answer is marked with the book\'s '
                'key, and the score gives your band on the official table.',
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: 12),
              Align(
                alignment: Alignment.centerLeft,
                child: FilledButton.icon(
                  onPressed: _starting || (active != null && !active.finished) ? null : _start,
                  icon: _starting
                      ? const SizedBox.square(dimension: 18, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.play_arrow),
                  label: const Text('Start the test'),
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

/// 3540 → "59:00".
String _clockText(int seconds) => '${seconds ~/ 60}:${(seconds % 60).toString().padLeft(2, '0')}';

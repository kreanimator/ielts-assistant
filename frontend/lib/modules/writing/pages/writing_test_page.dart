import 'dart:async';

import 'package:flutter/material.dart';
import 'package:web/web.dart' as web;

import '../api.dart';
import '../widgets/task_card.dart';
import '../words.dart';
import 'writing_session_page.dart';

/// The browser remembers the test in progress, so the Writing page can offer to continue it.
const activeTestKey = 'writing-test';

void rememberTest(String? id) {
  try {
    if (id == null) {
      web.window.localStorage.removeItem(activeTestKey);
    } else {
      web.window.localStorage.setItem(activeTestKey, id);
    }
  } catch (_) {}
}

String? rememberedTest() {
  try {
    return web.window.localStorage.getItem(activeTestKey);
  } catch (_) {
    return null;
  }
}

/// The full Writing test: Task 1 and Task 2 in one sitting, with the server's clock.
///
/// Your answers are saved on the server every few seconds. When the time is up, the server stops
/// accepting them, the editors lock, and the test ends with what was saved.
class WritingTestPage extends StatefulWidget {
  const WritingTestPage({super.key, required this.state});

  final TestState state;

  @override
  State<WritingTestPage> createState() => _WritingTestPageState();
}

class _WritingTestPageState extends State<WritingTestPage> {
  static const saveEvery = Duration(seconds: 5);

  late final _answers = {
    for (final t in widget.state.tasks) t.task: TextEditingController(text: widget.state.answers['${t.task}'] ?? ''),
  };
  late final Map<int, String> _saved = {for (final e in _answers.entries) e.key: e.value.text};
  int _current = 1; // the task shown
  late int _secondsLeft = widget.state.secondsLeft;
  late final _deadline = DateTime.now().add(Duration(seconds: widget.state.secondsLeft));
  Timer? _tick, _autosave;
  bool _ending = false;
  String? _saveProblem; // the last save failed (the server is unreachable)

  @override
  void initState() {
    super.initState();
    rememberTest(widget.state.session);
    for (final c in _answers.values) {
      c.addListener(() => setState(() {}));
    }
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      final left = _deadline.difference(DateTime.now()).inSeconds;
      setState(() => _secondsLeft = left < 0 ? 0 : left);
      if (left <= 0) _end(timeUp: true);
    });
    _autosave = Timer.periodic(saveEvery, (_) => _save());
  }

  @override
  void dispose() {
    _tick?.cancel();
    _autosave?.cancel();
    // Leaving the page (the test goes on): send what was not saved yet.
    if (!_ending && _answers.entries.any((e) => e.value.text != _saved[e.key])) {
      saveTestAnswers(widget.state.session, _texts).ignore();
    }
    for (final c in _answers.values) {
      c.dispose();
    }
    super.dispose();
  }

  Map<String, String> get _texts => {for (final e in _answers.entries) '${e.key}': e.value.text};

  /// Saves what changed. Returns false when the server says the time is up.
  Future<bool> _save() async {
    if (_ending) return true;
    final changed = _answers.entries.any((e) => e.value.text != _saved[e.key]);
    if (!changed) return true;
    final texts = _texts;
    try {
      final left = await saveTestAnswers(widget.state.session, texts);
      if (left == null) {
        _end(timeUp: true);
        return false;
      }
      _saved.addAll({for (final e in texts.entries) int.parse(e.key): e.value});
      if (mounted) setState(() => _saveProblem = null);
    } catch (e) {
      if (mounted) setState(() => _saveProblem = 'Not saved: the backend cannot be reached. Keep writing; it retries.');
    }
    return true;
  }

  Future<void> _end({required bool timeUp}) async {
    if (_ending) return;
    setState(() => _ending = true);
    _tick?.cancel();
    _autosave?.cancel();
    try {
      // The last answers go with it; the server keeps what was saved in time if they are late.
      await finishTest(widget.state.session, _texts);
      rememberTest(null);
      if (!mounted) return;
      if (timeUp) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Time is up. Your answers were handed in.')));
      }
      await Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (_) => WritingSessionPage(id: widget.state.session, modeTitle: writingModeTitle),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() => _ending = false);
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('Could not hand in the test ($e). Try again.')));
    }
  }

  Future<void> _finish() async {
    final notes = [
      for (final t in widget.state.tasks)
        if (wordCount(_answers[t.task]!.text) < t.words)
          'Task ${t.task} has ${wordCount(_answers[t.task]!.text)} words (at least ${t.words}).',
    ];
    final sure = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Hand in the test?'),
        content: Text(
          [...notes, 'You cannot change your answers afterwards. ${_clockText(_secondsLeft)} is left.'].join('\n\n'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Keep writing')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Hand in')),
        ],
      ),
    );
    if (sure == true) _end(timeUp: false);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final task = widget.state.tasks.firstWhere((t) => t.task == _current);
    final low = _secondsLeft <= 5 * 60;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Writing test'),
        actions: [
          Icon(Icons.timer_outlined, color: low ? theme.colorScheme.error : null),
          const SizedBox(width: 6),
          Text(
            '${_clockText(_secondsLeft)} left',
            style: theme.textTheme.titleMedium?.copyWith(
              color: low ? theme.colorScheme.error : null,
              fontWeight: low ? FontWeight.w700 : null,
            ),
          ),
          const SizedBox(width: 16),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SegmentedButton<int>(
              showSelectedIcon: false,
              segments: [
                for (final t in widget.state.tasks)
                  ButtonSegment(
                    value: t.task,
                    label: Text('Task ${t.task} · ${wordCount(_answers[t.task]!.text)}/${t.words} words'),
                  ),
              ],
              selected: {_current},
              onSelectionChanged: (s) {
                _save();
                setState(() => _current = s.first);
              },
            ),
            const SizedBox(height: 4),
            Text(
              'Advised: about 20 minutes for Task 1 and 40 for Task 2. Task 2 counts twice.',
              style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: 8),
            Expanded(child: _taskAndEditor(context, task)),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: Text(
                    _saveProblem ?? 'Saved on this computer\'s server every few seconds.',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: _saveProblem == null ? theme.colorScheme.onSurfaceVariant : theme.colorScheme.error,
                    ),
                  ),
                ),
                FilledButton.icon(
                  onPressed: _ending ? null : _finish,
                  icon: _ending
                      ? const SizedBox.square(dimension: 18, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.assignment_turned_in_outlined),
                  label: const Text('Hand in'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _taskAndEditor(BuildContext context, WritingTask task) {
    final theme = Theme.of(context);
    final editor = TextField(
      key: ValueKey(task.task),
      controller: _answers[task.task],
      readOnly: _ending,
      maxLines: null,
      expands: true,
      textAlignVertical: TextAlignVertical.top,
      autocorrect: false,
      enableSuggestions: false,
      spellCheckConfiguration: const SpellCheckConfiguration.disabled(),
      style: theme.textTheme.bodyLarge?.copyWith(height: 1.5),
      decoration: InputDecoration(
        hintText: task.task == 1
            ? '${task.begin}\n\n...'
            : 'Write your essay here. Leave a blank line between paragraphs.',
        border: const OutlineInputBorder(),
      ),
    );
    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth >= 900) {
          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(
                width: 380,
                child: SingleChildScrollView(child: TaskCard(task: task)),
              ),
              const SizedBox(width: 16),
              Expanded(child: editor),
            ],
          );
        }
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ConstrainedBox(
              constraints: BoxConstraints(maxHeight: constraints.maxHeight * 0.35),
              child: SingleChildScrollView(child: TaskCard(task: task)),
            ),
            const SizedBox(height: 12),
            Expanded(child: editor),
          ],
        );
      },
    );
  }
}

/// 3540 → "59:00".
String _clockText(int seconds) => '${seconds ~/ 60}:${(seconds % 60).toString().padLeft(2, '0')}';

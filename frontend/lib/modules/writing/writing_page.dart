import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:web/web.dart' as web;

import 'api.dart';
import 'pages/writing_session_page.dart';
import 'widgets/task_card.dart';
import 'words.dart';

/// Writing practice: choose a task (from your books or a new one), write your answer with a
/// word counter and the clock, then get the report with corrections.
///
/// The answer being written is kept in the browser (localStorage) as a draft, so a closed tab or
/// a reload does not lose it. It never leaves this computer until you finish.
class WritingPage extends StatefulWidget {
  const WritingPage({super.key});

  @override
  State<WritingPage> createState() => _WritingPageState();
}

const _draftKey = 'writing-draft';

class _WritingPageState extends State<WritingPage> {
  WritingOptions? _options;
  List<BookTest> _tests = [];
  String? _error;

  // The setup.
  int _taskNumber = 2;
  bool _fromBook = true;
  BookTest? _test; // null: a random test
  String? _kind; // null: any type
  final _topic = TextEditingController();
  bool _loading = false; // a task is being fetched (a new one takes a few seconds)

  // Writing.
  WritingTask? _task;
  final _answer = TextEditingController();
  int _seconds = 0;
  Timer? _clock;
  bool _saving = false;
  ({WritingTask task, String text, int seconds})? _draft; // an unfinished answer from before

  @override
  void initState() {
    super.initState();
    _answer.addListener(_changed);
    _draft = _loadDraft();
    _load();
  }

  @override
  void dispose() {
    _clock?.cancel();
    _answer.dispose();
    _topic.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final options = await fetchWritingOptions();
      final tests = await fetchBookTests();
      setState(() {
        _options = options;
        _tests = tests;
        _fromBook = (options.bookTasks[_taskNumber] ?? 0) > 0;
      });
    } catch (e) {
      setState(() => _error = 'Could not reach the backend ($e).');
    }
  }

  void _changed() {
    setState(() {}); // the word counter
    _saveDraft();
  }

  // The draft in the browser. Storage can be missing (a private window): then there is none.
  ({WritingTask task, String text, int seconds})? _loadDraft() {
    try {
      final raw = web.window.localStorage.getItem(_draftKey);
      if (raw == null) return null;
      final json = jsonDecode(raw) as Map<String, dynamic>;
      if (wordCount(json['text'] ?? '') == 0) return null;
      return (task: WritingTask.fromJson(json['task']), text: json['text'] as String, seconds: json['seconds'] as int);
    } catch (_) {
      return null;
    }
  }

  void _saveDraft() {
    final task = _task;
    if (task == null) return;
    try {
      web.window.localStorage.setItem(
        _draftKey,
        jsonEncode({'task': task.json, 'text': _answer.text, 'seconds': _seconds}),
      );
    } catch (_) {}
  }

  void _clearDraft() {
    try {
      web.window.localStorage.removeItem(_draftKey);
    } catch (_) {}
  }

  void _begin(WritingTask task, {String text = '', int seconds = 0}) {
    _clock?.cancel();
    setState(() {
      _task = task;
      _answer.text = text;
      _seconds = seconds;
      _draft = null;
    });
    _clock = Timer.periodic(const Duration(seconds: 1), (_) {
      setState(() => _seconds++);
      if (_seconds % 10 == 0) _saveDraft();
    });
  }

  Future<void> _start() async {
    setState(() => _loading = true);
    try {
      final task = await fetchTask(
        task: _taskNumber,
        fromBook: _fromBook,
        book: _fromBook ? _test?.book : null,
        test: _fromBook ? _test?.test : null,
        topic: _fromBook ? null : _topic.text,
        kind: _fromBook ? null : _kind,
      );
      _clearDraft();
      _begin(task);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('No task ($e).')));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<bool> _confirm(String title, String text, String yes) async =>
      await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text(title),
          content: Text(text),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Keep writing')),
            FilledButton(onPressed: () => Navigator.pop(context, true), child: Text(yes)),
          ],
        ),
      ) ??
      false;

  Future<void> _finish() async {
    final task = _task!;
    final words = wordCount(_answer.text);
    if (words == 0) return;
    if (words < task.words &&
        !await _confirm(
          'Finish with $words words?',
          'Task ${task.task} needs at least ${task.words} words. A shorter answer loses marks for '
              'Task ${task.task == 1 ? 'Achievement' : 'Response'}.',
          'Finish',
        )) {
      return;
    }
    setState(() => _saving = true);
    try {
      final id = await saveAnswer(task, _answer.text, _seconds);
      _clock?.cancel();
      _clearDraft();
      if (!mounted) return;
      await Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (_) => WritingSessionPage(id: id, modeTitle: writingModeTitle),
        ),
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not save your answer ($e). It is kept as a draft in this browser.')),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _newTask() async {
    if (wordCount(_answer.text) > 0 &&
        !await _confirm('Leave this answer?', 'What you wrote is discarded.', 'Discard')) {
      return;
    }
    _clock?.cancel();
    _clearDraft();
    setState(() {
      _task = null;
      _answer.clear();
    });
  }

  @override
  Widget build(BuildContext context) {
    final task = _task;
    return Scaffold(
      appBar: AppBar(
        title: Text(task == null ? 'Writing' : 'Writing Task ${task.task}'),
        actions: [
          if (task != null)
            TextButton.icon(onPressed: _newTask, icon: const Icon(Icons.close), label: const Text('New task')),
        ],
      ),
      body: task == null ? _setup(context) : _writing(context, task),
    );
  }

  Widget _setup(BuildContext context) {
    final theme = Theme.of(context);
    final options = _options;
    if (options == null) {
      return Center(child: _error == null ? const CircularProgressIndicator() : Text(_error!));
    }
    final inBooks = options.bookTasks[_taskNumber] ?? 0;
    final tests = [
      for (final t in _tests)
        if (_taskNumber == 1 ? t.hasTask1 : t.hasTask2) t,
    ];
    final draft = _draft;
    final kinds = _taskNumber == 1 ? options.letterTypes : options.essayTypes.keys.toList();
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 640),
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (draft != null)
              Card(
                margin: const EdgeInsets.only(bottom: 16),
                color: theme.colorScheme.secondaryContainer,
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Unfinished answer', style: theme.textTheme.titleMedium),
                      Text(
                        'Task ${draft.task.task}: ${draft.task.title}, ${wordCount(draft.text)} words, '
                        '${_clockText(draft.seconds)} written.',
                      ),
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 8,
                        children: [
                          FilledButton(
                            onPressed: () => _begin(draft.task, text: draft.text, seconds: draft.seconds),
                            child: const Text('Continue'),
                          ),
                          TextButton(
                            onPressed: () {
                              _clearDraft();
                              setState(() => _draft = null);
                            },
                            child: const Text('Discard'),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            Text('Task', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            SegmentedButton<int>(
              segments: const [
                ButtonSegment(value: 1, label: Text('Task 1 · Letter'), icon: Icon(Icons.mail_outline)),
                ButtonSegment(value: 2, label: Text('Task 2 · Essay'), icon: Icon(Icons.article_outlined)),
              ],
              selected: {_taskNumber},
              onSelectionChanged: (s) => setState(() {
                _taskNumber = s.first;
                _test = null;
                _kind = null;
                _fromBook = (options.bookTasks[_taskNumber] ?? 0) > 0;
              }),
            ),
            const SizedBox(height: 4),
            Text(
              _taskNumber == 1
                  ? 'General Training: a letter of at least 150 words in about 20 minutes.'
                  : 'An essay of at least 250 words in about 40 minutes. It counts twice in the writing band.',
              style: theme.textTheme.bodySmall,
            ),
            const SizedBox(height: 20),
            Text('Where the task comes from', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            SegmentedButton<bool>(
              segments: [
                ButtonSegment(
                  value: true,
                  label: Text('Your books ($inBooks)'),
                  icon: const Icon(Icons.menu_book_outlined),
                  enabled: inBooks > 0,
                ),
                const ButtonSegment(value: false, label: Text('New task'), icon: Icon(Icons.auto_awesome_outlined)),
              ],
              selected: {_fromBook},
              onSelectionChanged: (s) => setState(() => _fromBook = s.first),
            ),
            const SizedBox(height: 12),
            if (_fromBook)
              DropdownButtonFormField<BookTest?>(
                initialValue: _test,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Test', border: OutlineInputBorder()),
                items: [
                  const DropdownMenuItem(value: null, child: Text('Any test (random)')),
                  for (final t in tests) DropdownMenuItem(value: t, child: Text('${t.bookTitle} · Test ${t.test}')),
                ],
                onChanged: (t) => setState(() => _test = t),
              )
            else ...[
              if (inBooks == 0)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Text(
                    'Import your own IELTS books with make books to practise their real tasks too.',
                    style: theme.textTheme.bodySmall,
                  ),
                ),
              TextField(
                controller: _topic,
                decoration: const InputDecoration(
                  labelText: 'Topic (optional)',
                  hintText: 'e.g. work, a holiday, technology',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String?>(
                key: ValueKey(_taskNumber), // a new list of types
                initialValue: _kind,
                isExpanded: true,
                decoration: InputDecoration(
                  labelText: _taskNumber == 1 ? 'Kind of letter' : 'Kind of essay',
                  border: const OutlineInputBorder(),
                ),
                items: [
                  const DropdownMenuItem(value: null, child: Text('Any (random)')),
                  for (final k in kinds)
                    DropdownMenuItem(
                      value: k,
                      child: Text(_taskNumber == 1 ? _capital(k) : '${_capital(k)}: ${options.essayTypes[k]}'),
                    ),
                ],
                onChanged: (k) => setState(() => _kind = k),
              ),
            ],
            const SizedBox(height: 20),
            FilledButton.icon(
              onPressed: _loading ? null : _start,
              icon: _loading
                  ? const SizedBox.square(dimension: 18, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.edit_outlined),
              label: Text(_loading && !_fromBook ? 'Writing a new task...' : 'Start writing'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _writing(BuildContext context, WritingTask task) {
    final theme = Theme.of(context);
    final words = wordCount(_answer.text);
    final enough = words >= task.words;
    final left = task.minutes * 60 - _seconds;
    final editor = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Icon(
              enough ? Icons.check_circle_outline : Icons.short_text,
              size: 20,
              color: enough ? theme.colorScheme.primary : theme.colorScheme.onSurfaceVariant,
            ),
            const SizedBox(width: 6),
            Text('$words / ${task.words} words', style: theme.textTheme.titleSmall),
            const Spacer(),
            Icon(Icons.timer_outlined, size: 20, color: left < 0 ? theme.colorScheme.error : null),
            const SizedBox(width: 6),
            Text(
              left >= 0 ? '${_clockText(left)} left' : '${_clockText(-left)} over time',
              style: theme.textTheme.titleSmall?.copyWith(color: left < 0 ? theme.colorScheme.error : null),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Expanded(
          child: TextField(
            controller: _answer,
            maxLines: null,
            expands: true,
            textAlignVertical: TextAlignVertical.top,
            // As in the computer-delivered test: no spelling help.
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
          ),
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            Expanded(
              child: Text(
                'Your draft is kept in this browser until you finish.',
                style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
              ),
            ),
            FilledButton.icon(
              onPressed: words == 0 || _saving ? null : _finish,
              icon: const Icon(Icons.fact_check_outlined),
              label: const Text('Finish and get feedback'),
            ),
          ],
        ),
      ],
    );
    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth >= 900) {
          return Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(
                  width: 380,
                  child: SingleChildScrollView(child: TaskCard(task: task)),
                ),
                const SizedBox(width: 16),
                Expanded(child: editor),
              ],
            ),
          );
        }
        return Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              ConstrainedBox(
                constraints: BoxConstraints(maxHeight: constraints.maxHeight * 0.35),
                child: SingleChildScrollView(child: TaskCard(task: task)),
              ),
              const SizedBox(height: 12),
              Expanded(child: editor),
            ],
          ),
        );
      },
    );
  }
}

String _capital(String s) => s.isEmpty ? s : s[0].toUpperCase() + s.substring(1);

/// 1180 → "19:40".
String _clockText(int seconds) => '${seconds ~/ 60}:${(seconds % 60).toString().padLeft(2, '0')}';

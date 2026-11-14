import 'dart:js_interop';

import 'package:flutter/material.dart';
import 'package:web/web.dart' as web;

import '../../../core/history.dart';
import '../../../core/widgets/exam_shell.dart';
import '../../../core/widgets/report_view.dart';
import '../../reading/widgets/question_panel.dart';
import '../api.dart';
import 'listening_test_page.dart';

/// One Listening test: the band, the score of each part, and every answer marked with the key.
class ListeningSessionPage extends StatefulWidget {
  const ListeningSessionPage({super.key, required this.id, required this.modeTitle});

  final String id;
  final String Function(String mode) modeTitle;

  @override
  State<ListeningSessionPage> createState() => _ListeningSessionPageState();
}

class _ListeningSessionPageState extends State<ListeningSessionPage> {
  StoredSession? _session;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      var session = await fetchSession(widget.id);
      if (_inProgress(session)) {
        await fetchListeningTest(widget.id); // finishes it on the server if its time ran out
        session = await fetchSession(widget.id);
      }
      setState(() => _session = session);
      if (session.report == null && !_inProgress(session)) {
        final report = await writeReport(widget.id);
        setState(() => session.report = report);
      }
    } catch (e) {
      setState(() => _error = 'Could not load this test ($e).');
    }
  }

  bool _inProgress(StoredSession s) => s.details?['finished'] == false;

  Future<void> _continueTest() async {
    final state = await fetchListeningTest(widget.id);
    if (!mounted) return;
    await Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => ListeningTestPage(state: state)));
  }

  /// The test as it was taken, marked, with what was said and the recordings to hear again.
  Future<void> _review(Map<String, dynamic> details, List<Map<String, dynamic>> questions) async {
    try {
      final state = await fetchListeningTest(widget.id);
      if (!mounted || state.content == null) return;
      await Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => ListeningReviewPage(
            state: state,
            title: details['title'] ?? 'The test',
            marks: {for (final q in questions) q['q'] as int: (right: q['right'] == true, key: '${q['key']}')},
          ),
        ),
      );
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not open the test ($e).')));
    }
  }

  Future<void> _delete() async {
    final sure = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete this test?'),
        content: const Text('Your answers and their marks are removed from this computer.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Delete')),
        ],
      ),
    );
    if (sure != true) return;
    await deleteSession(widget.id);
    if (mounted) Navigator.pop(context, true);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final session = _session;
    final details = session?.details;
    final report = session?.report;
    final questions = [for (final q in report?.json['questions'] ?? []) q as Map<String, dynamic>];
    final parts = [for (final p in report?.json['parts'] ?? []) p as Map<String, dynamic>];
    return Scaffold(
      appBar: AppBar(
        title: Text(session == null ? 'Listening' : session.title(widget.modeTitle(session.mode))),
        actions: [
          if (session != null)
            IconButton(tooltip: 'Delete this test', onPressed: _delete, icon: const Icon(Icons.delete_outline)),
        ],
      ),
      body: session == null
          ? Center(child: _error == null ? const CircularProgressIndicator() : Text(_error!))
          : Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 860),
                child: ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    if (_inProgress(session))
                      Card(
                        child: ListTile(
                          leading: const Icon(Icons.headphones_outlined),
                          title: const Text('This test is still in progress'),
                          subtitle: const Text('Once started, its recording keeps running on the server\'s clock.'),
                          trailing: FilledButton(onPressed: _continueTest, child: const Text('Continue')),
                        ),
                      )
                    else if (report == null)
                      const Center(child: CircularProgressIndicator())
                    else ...[
                      ReportView(report: report),
                      const SizedBox(height: 16),
                      Wrap(
                        spacing: 12,
                        runSpacing: 8,
                        children: [
                          for (final (i, p) in parts.indexed)
                            Chip(
                              avatar: const Icon(Icons.headphones_outlined, size: 18),
                              label: Text('Part ${i + 1}: ${p['right']} of ${p['of']}'),
                            ),
                        ],
                      ),
                      const SizedBox(height: 16),
                      Row(
                        children: [
                          Expanded(child: Text('Your answers', style: theme.textTheme.titleLarge)),
                          if (details != null)
                            OutlinedButton.icon(
                              onPressed: () => _review(details, questions),
                              icon: const Icon(Icons.hearing_outlined),
                              label: const Text('See and hear the test'),
                            ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      for (final q in questions) _AnswerRow(q),
                    ],
                  ],
                ),
              ),
            ),
    );
  }
}

/// One question: your answer, right or wrong, and the key's answer when it was wrong.
class _AnswerRow extends StatelessWidget {
  const _AnswerRow(this.question);

  final Map<String, dynamic> question;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final right = question['right'] == true;
    final given = (question['given'] as String?) ?? '';
    final muted = theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 32,
            child: Text('${question['q']}', textAlign: TextAlign.right, style: theme.textTheme.titleSmall),
          ),
          const SizedBox(width: 8),
          Icon(
            right ? Icons.check_circle_outline : Icons.cancel_outlined,
            size: 20,
            color: right ? Colors.green.shade700 : theme.colorScheme.error,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text.rich(
              TextSpan(
                children: [
                  TextSpan(text: given.isEmpty ? 'no answer' : given, style: given.isEmpty ? muted : null),
                  if (!right) TextSpan(text: '   key: ${question['key']}', style: muted),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// A finished test, part by part: the questions with your answers marked, what was said (when
/// the test has its transcript), and the part's recording to hear again, as often as you like.
class ListeningReviewPage extends StatefulWidget {
  const ListeningReviewPage({super.key, required this.state, required this.marks, required this.title});

  final ListeningTestState state;
  final Map<int, ({bool right, String key})> marks;
  final String title;

  @override
  State<ListeningReviewPage> createState() => _ListeningReviewPageState();
}

class _ListeningReviewPageState extends State<ListeningReviewPage> {
  final Map<int, TextEditingController> _controllers = {};
  final Map<int, GlobalKey> _keys = {};
  final web.HTMLAudioElement _audio = web.HTMLAudioElement();
  int _part = 0;
  bool _showQuestions = true;
  bool _playing = false;
  String? _loaded; // the recording in the player

  @override
  void initState() {
    super.initState();
    _audio.onended = ((web.Event _) {
      if (mounted) setState(() => _playing = false);
    }).toJS;
  }

  @override
  void dispose() {
    _audio.pause();
    _audio.removeAttribute('src');
    for (final c in _controllers.values) {
      c.dispose();
    }
    super.dispose();
  }

  String _value(int q) => widget.state.answers['$q'] ?? '';

  late final _access = AnswerAccess(
    value: _value,
    set: (_, _) {},
    controller: (q) => _controllers.putIfAbsent(q, () => TextEditingController(text: _value(q))),
    keyOf: (q) => _keys.putIfAbsent(q, GlobalKey.new),
    readOnly: true,
    marks: widget.marks,
  );

  /// The recording of the part shown: its own, or the one recording of the whole test.
  Recording get _recording {
    final audio = widget.state.audio;
    return audio.firstWhere((a) => a.part == _part + 1, orElse: () => audio.first);
  }

  Future<void> _toggle() async {
    if (_playing) {
      _audio.pause();
      setState(() => _playing = false);
      return;
    }
    final file = _recording.file;
    if (_loaded != file) {
      _audio.src = recordingUrl(widget.state.book, file);
      _loaded = file;
    }
    try {
      await _audio.play().toDart;
      if (mounted) setState(() => _playing = true);
    } catch (_) {}
  }

  void _skip(double seconds) {
    if (_loaded == null) return;
    final at = _audio.currentTime + seconds;
    _audio.currentTime = at < 0 ? 0 : at;
  }

  void _show(int part) {
    _audio.pause();
    setState(() {
      _part = part;
      _playing = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final state = widget.state;
    final parts = state.content!.parts;
    final part = parts[_part];
    final said = _part < state.transcripts.length ? state.transcripts[_part] : const <String>[];
    final whole = state.audio.length == 1;
    int right(int first, int last) =>
        [for (var q = first; q <= last; q++) q].where((q) => widget.marks[q]?.right == true).length;
    final transcript = ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
      children: [
        Row(
          children: [
            FilledButton.tonalIcon(
              onPressed: _toggle,
              icon: Icon(_playing ? Icons.pause : Icons.play_arrow),
              label: Text(_playing ? 'Pause' : (whole ? 'Play the recording' : 'Play part ${part.part}')),
            ),
            IconButton(tooltip: 'Back 10 seconds', onPressed: () => _skip(-10), icon: const Icon(Icons.replay_10)),
            IconButton(tooltip: 'Forward 10 seconds', onPressed: () => _skip(10), icon: const Icon(Icons.forward_10)),
          ],
        ),
        if (whole)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text('This test is one recording: all four parts.', style: theme.textTheme.bodySmall),
          ),
        const SizedBox(height: 12),
        if (said.isEmpty)
          Text('This test has no transcript.', style: theme.textTheme.bodyMedium)
        else
          for (final paragraph in said)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: SelectableText(paragraph, style: const TextStyle(fontSize: 16, height: 1.5)),
            ),
      ],
    );
    final questions = QuestionPanel(
      key: PageStorageKey('listening-review-$_part'),
      book: state.book,
      part: part,
      access: _access,
    );
    final palette = ExamPalette.of(ExamContrast.normal);
    return Theme(
      data: examTheme(palette),
      child: ExamStyle(
        palette: palette,
        child: Scaffold(
          appBar: AppBar(title: Text(widget.title)),
          body: LayoutBuilder(
            builder: (context, constraints) {
              final wide = constraints.maxWidth >= 900;
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Padding(
                    padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
                    child: Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        for (final (i, p) in parts.indexed)
                          ChoiceChip(
                            label: Text('Part ${p.part}: ${right(p.first, p.last)} of ${p.last - p.first + 1}'),
                            selected: i == _part,
                            onSelected: (_) => _show(i),
                          ),
                        if (!wide)
                          ActionChip(
                            avatar: Icon(_showQuestions ? Icons.article_outlined : Icons.checklist, size: 18),
                            label: Text(_showQuestions ? 'The recording' : 'The questions'),
                            onPressed: () => setState(() => _showQuestions = !_showQuestions),
                          ),
                      ],
                    ),
                  ),
                  Divider(height: 1, color: theme.colorScheme.outlineVariant),
                  Expanded(
                    child: wide
                        ? Row(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Expanded(child: transcript),
                              VerticalDivider(width: 1, color: theme.colorScheme.outlineVariant),
                              Expanded(child: questions),
                            ],
                          )
                        : IndexedStack(index: _showQuestions ? 1 : 0, children: [transcript, questions]),
                  ),
                ],
              );
            },
          ),
        ),
      ),
    );
  }
}

import 'package:flutter/material.dart';

import '../../../core/history.dart';
import '../../../core/widgets/band.dart';
import '../../../core/widgets/report_view.dart';
import '../api.dart';
import '../widgets/task_card.dart';
import 'writing_test_page.dart';

/// A correction's colour by what it is about (backend/app/writing/assessor.py, KINDS; the
/// others are the names older reports used).
const _categoryColors = {
  'grammar': Color(0xFFC62828),
  'spelling': Color(0xFFEF6C00),
  'precision': Color(0xFF1565C0),
  'style': Color(0xFF558B2F),
  'task': Color(0xFF6A1B9A),
  'vocabulary': Color(0xFF1565C0),
  'punctuation': Color(0xFF00838F),
  'linking': Color(0xFF6A1B9A),
};
const _registerNames = {'informal': 'Informal', 'semi-formal': 'Semi-formal', 'formal': 'Formal'};

/// One Writing session: the band report, then each task with your answer, its corrections
/// marked in the text, and the numbers measured.
class WritingSessionPage extends StatefulWidget {
  const WritingSessionPage({super.key, required this.id, required this.modeTitle});

  final String id;
  final String Function(String mode) modeTitle;

  @override
  State<WritingSessionPage> createState() => _WritingSessionPageState();
}

class _WritingSessionPageState extends State<WritingSessionPage> {
  StoredSession? _session;
  String? _error;
  bool _writing = false; // the report is being written

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      var session = await fetchSession(widget.id);
      if (_inProgress(session)) {
        await fetchTest(widget.id); // finishes it on the server if its time ran out
        session = await fetchSession(widget.id);
      }
      setState(() => _session = session);
      if (session.report == null && !_inProgress(session)) await _writeReport();
    } catch (e) {
      setState(() => _error = 'Could not load this session ($e).');
    }
  }

  bool _inProgress(StoredSession s) => s.mode == 'test' && s.details?['finished'] == false;

  Future<void> _continueTest() async {
    final state = await fetchTest(widget.id);
    if (!mounted) return;
    await Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => WritingTestPage(state: state)));
  }

  Future<void> _writeReport({bool again = false}) async {
    setState(() => _writing = true);
    try {
      final report = await writeReport(widget.id, again: again);
      setState(() => _session!.report = report);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('The report failed ($e).')));
    } finally {
      if (mounted) setState(() => _writing = false);
    }
  }

  Future<void> _delete() async {
    final sure = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete this session?'),
        content: const Text('Your answer and its report are removed from this computer.'),
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
    final session = _session;
    final answers = [
      for (final m in session?.messageJson ?? <Map<String, dynamic>>[])
        if (m['role'] == 'candidate') m,
    ];
    final assessed = [for (final t in session?.report?.json['tasks'] ?? []) t as Map<String, dynamic>];
    return Scaffold(
      appBar: AppBar(
        title: Text(session == null ? 'Writing' : session.title(widget.modeTitle(session.mode))),
        actions: [
          if (session != null && !_writing && !_inProgress(session))
            IconButton(
              tooltip: 'Write the report again',
              onPressed: () => _writeReport(again: true),
              icon: const Icon(Icons.refresh),
            ),
          if (session != null)
            IconButton(tooltip: 'Delete session', onPressed: _delete, icon: const Icon(Icons.delete_outline)),
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
                          leading: const Icon(Icons.timer_outlined),
                          title: const Text('This test is still in progress'),
                          subtitle: const Text('The clock keeps running on the server.'),
                          trailing: FilledButton(onPressed: _continueTest, child: const Text('Continue')),
                        ),
                      )
                    else if (_writing)
                      const _WritingReport()
                    else if (session.report != null)
                      ReportView(report: session.report!),
                    for (final m in answers) ...[
                      const SizedBox(height: 24),
                      _TaskSection(
                        message: m,
                        assessed: assessed.where((t) => t['task'] == m['delivery']?['task']?['task']).firstOrNull,
                        showBand: answers.length > 1,
                      ),
                    ],
                  ],
                ),
              ),
            ),
    );
  }
}

/// One task: the task, your answer with the corrections marked, the corrections, the numbers.
class _TaskSection extends StatelessWidget {
  const _TaskSection({required this.message, required this.assessed, required this.showBand});

  final Map<String, dynamic> message;
  final Map<String, dynamic>? assessed; // null until the report is written
  final bool showBand; // with two tasks, each task's own band

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final delivery = message['delivery'] as Map<String, dynamic>?;
    final task = delivery == null ? null : WritingTask.fromJson(delivery['task']);
    final text = message['text'] as String;
    final corrections = [for (final c in assessed?['corrections'] ?? []) c as Map<String, dynamic>];
    final suggestions = [for (final c in assessed?['suggestions'] ?? []) c as Map<String, dynamic>];
    final taskNotes = [for (final c in assessed?['task_notes'] ?? []) c as Map<String, dynamic>];
    final register = assessed?['register'] as Map<String, dynamic>?;
    final stats = assessed?['stats'] as Map<String, dynamic>?;
    final seconds = delivery?['seconds'] as int?;
    final muted = theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(child: Text('Task ${task?.task ?? ''}', style: theme.textTheme.titleLarge)),
            if (showBand && assessed != null) BandBadge(band: (assessed!['band'] as num).toDouble()),
          ],
        ),
        const SizedBox(height: 8),
        if (task != null) TaskCard(task: task),
        const SizedBox(height: 16),
        Text('Your answer', style: theme.textTheme.titleMedium),
        const SizedBox(height: 4),
        Wrap(
          spacing: 16,
          children: [
            for (final s in [
              '${stats?['words'] ?? delivery?['words']} words'
                  '${task == null ? '' : ' (at least ${task.words})'}',
              if (stats != null) '${stats['paragraphs']} paragraph${stats['paragraphs'] == 1 ? '' : 's'}',
              if (stats?['words_per_sentence'] != null) '${stats!['words_per_sentence']} words per sentence',
              if (seconds != null) '${(seconds / 60).round()} min${task == null ? '' : ' of ${task.minutes}'}',
            ])
              Text(s, style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
          ],
        ),
        const SizedBox(height: 8),
        Card(
          margin: EdgeInsets.zero,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: _MarkedText(text: text, corrections: corrections),
          ),
        ),
        if (register != null) ...[const SizedBox(height: 12), _RegisterNote(register: register)],
        if (corrections.isNotEmpty) ...[
          const SizedBox(height: 16),
          Text('Corrections', style: theme.textTheme.titleMedium),
          Text(
            'Errors: grammar, spelling, and wording that does not say what you mean. They are marked in your answer.',
            style: muted,
          ),
          const SizedBox(height: 4),
          for (final (i, c) in corrections.indexed) _CorrectionTile(number: i + 1, correction: c),
        ] else if (assessed != null) ...[
          const SizedBox(height: 16),
          const Text('No errors found: well done.'),
        ],
        if (taskNotes.isNotEmpty) ...[
          const SizedBox(height: 20),
          Text('The task', style: theme.textTheme.titleMedium),
          Text('What the task asks for and your answer lacks.', style: muted),
          const SizedBox(height: 4),
          for (final c in taskNotes) _NoteTile(note: c),
        ],
        if (suggestions.isNotEmpty) ...[
          const SizedBox(height: 20),
          Text('Optional suggestions', style: theme.textTheme.titleMedium),
          Text(
            'These are correct English, not errors, and they do not lower your band: only other ways to say it.',
            style: muted,
          ),
          const SizedBox(height: 4),
          for (final c in suggestions) _CorrectionTile(number: null, correction: c),
        ],
      ],
    );
  }
}

/// The answer with each corrected stretch underlined in its category's colour and numbered.
class _MarkedText extends StatelessWidget {
  const _MarkedText({required this.text, required this.corrections});

  final String text;
  final List<Map<String, dynamic>> corrections; // sorted by start, from the backend

  @override
  Widget build(BuildContext context) {
    final base = Theme.of(context).textTheme.bodyLarge?.copyWith(height: 1.6);
    final spans = <InlineSpan>[];
    var at = 0;
    for (final (i, c) in corrections.indexed) {
      final start = c['start'] as int, end = c['end'] as int;
      if (start < at || end > text.length) continue; // overlaps the one before
      spans.add(TextSpan(text: text.substring(at, start)));
      final color = _categoryColors[c['category']] ?? Colors.grey;
      spans.add(
        TextSpan(
          text: text.substring(start, end),
          style: TextStyle(
            decoration: TextDecoration.underline,
            decorationColor: color,
            decorationThickness: 2,
            backgroundColor: color.withValues(alpha: 0.10),
          ),
        ),
      );
      spans.add(
        WidgetSpan(
          alignment: PlaceholderAlignment.top,
          child: Text(
            '${i + 1}',
            style: TextStyle(fontSize: 10, color: color, fontWeight: FontWeight.w700),
          ),
        ),
      );
      at = end;
    }
    spans.add(TextSpan(text: text.substring(at)));
    return SelectableText.rich(TextSpan(style: base, children: spans));
  }
}

class _CorrectionTile extends StatelessWidget {
  const _CorrectionTile({required this.number, required this.correction});

  final int? number; // its number in the answer; null for a suggestion, which is not marked there
  final Map<String, dynamic> correction;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = _categoryColors[correction['category']] ?? Colors.grey;
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 28,
            child: number == null
                ? Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Icon(Icons.lightbulb_outline, size: 16, color: color),
                  )
                : Text(
                    '$number',
                    style: TextStyle(color: color, fontWeight: FontWeight.w700),
                  ),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text.rich(
                  TextSpan(
                    children: [
                      TextSpan(
                        text: correction['original'],
                        // an error is struck out; a suggestion's words are not wrong
                        style: TextStyle(
                          decoration: number == null ? null : TextDecoration.lineThrough,
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                      TextSpan(text: number == null ? '   or:  ' : '   '),
                      TextSpan(
                        text: correction['better'],
                        style: const TextStyle(fontWeight: FontWeight.w600),
                      ),
                    ],
                  ),
                ),
                Text(
                  '${correction['category']} · ${correction['why']}',
                  style: theme.textTheme.bodySmall?.copyWith(color: color),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// The register a letter needs (from who it is to) and the one it was written in.
class _RegisterNote extends StatelessWidget {
  const _RegisterNote({required this.register});

  final Map<String, dynamic> register;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final required = register['required'] as String?, used = register['used'] as String?;
    final fits = required == used;
    final color = fits ? Colors.green.shade700 : theme.colorScheme.error;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(fits ? Icons.check_circle_outline : Icons.error_outline, size: 18, color: color),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            'Register: ${(_registerNames[required] ?? required ?? '').toLowerCase()}, for a letter to '
            '${register['reader']}. '
            '${fits ? 'Your letter is ${(_registerNames[used] ?? used ?? '').toLowerCase()}: the right tone, and it '
                      'was judged as such.' : 'Your letter reads as ${(_registerNames[used] ?? used ?? '').toLowerCase()}: '
                      'the tone does not fit the reader, which counts in Task Achievement.'}',
            style: theme.textTheme.bodyMedium,
          ),
        ),
      ],
    );
  }
}

/// Something the task asks for that the answer lacks.
class _NoteTile extends StatelessWidget {
  const _NoteTile({required this.note});

  final Map<String, dynamic> note;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = _categoryColors['task']!;
    final original = (note['original'] as String? ?? '').trim();
    final better = (note['better'] as String? ?? '').trim();
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 28,
            child: Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Icon(Icons.assignment_outlined, size: 16, color: color),
            ),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (original.isNotEmpty)
                  Text('"$original"', style: TextStyle(color: theme.colorScheme.onSurfaceVariant)),
                if (better.isNotEmpty) Text(better, style: const TextStyle(fontWeight: FontWeight.w600)),
                Text('${note['why']}', style: theme.textTheme.bodySmall?.copyWith(color: color)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _WritingReport extends StatelessWidget {
  const _WritingReport();

  @override
  Widget build(BuildContext context) => const Card(
    child: Padding(
      padding: EdgeInsets.all(20),
      child: Row(
        children: [
          SizedBox.square(dimension: 24, child: CircularProgressIndicator(strokeWidth: 3)),
          SizedBox(width: 16),
          Expanded(child: Text('Reading your answers and writing the report: about 40 seconds per task.')),
        ],
      ),
    ),
  );
}

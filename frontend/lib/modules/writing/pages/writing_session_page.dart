import 'package:flutter/material.dart';

import '../../../core/history.dart';
import '../../../core/widgets/band.dart';
import '../../../core/widgets/report_view.dart';
import '../api.dart';
import '../widgets/task_card.dart';
import 'writing_test_page.dart';

const _categoryColors = {
  'grammar': Color(0xFFC62828),
  'vocabulary': Color(0xFF1565C0),
  'spelling': Color(0xFFEF6C00),
  'punctuation': Color(0xFF00838F),
  'linking': Color(0xFF6A1B9A),
  'style': Color(0xFF558B2F),
};

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
    final stats = assessed?['stats'] as Map<String, dynamic>?;
    final seconds = delivery?['seconds'] as int?;
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
        if (corrections.isNotEmpty) ...[
          const SizedBox(height: 16),
          Text('Corrections', style: theme.textTheme.titleMedium),
          const SizedBox(height: 4),
          for (final (i, c) in corrections.indexed) _CorrectionTile(number: i + 1, correction: c),
        ] else if (assessed != null) ...[
          const SizedBox(height: 16),
          const Text('No corrections: well done.'),
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

  final int number;
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
            child: Text(
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
                        style: TextStyle(
                          decoration: TextDecoration.lineThrough,
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                      const TextSpan(text: '   '),
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

import 'package:flutter/material.dart';

import '../../../core/history.dart';
import '../../../core/widgets/report_view.dart';
import '../api.dart';
import '../widgets/book_pages.dart';
import 'reading_review_page.dart';
import 'reading_test_page.dart';

/// One Reading test: the band, the score of each passage, and every answer marked with the key.
class ReadingSessionPage extends StatefulWidget {
  const ReadingSessionPage({super.key, required this.id, required this.modeTitle});

  final String id;
  final String Function(String mode) modeTitle;

  @override
  State<ReadingSessionPage> createState() => _ReadingSessionPageState();
}

class _ReadingSessionPageState extends State<ReadingSessionPage> {
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
        await fetchReadingTest(widget.id); // finishes it on the server if its time ran out
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
    final state = await fetchReadingTest(widget.id);
    if (!mounted) return;
    await Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => ReadingTestPage(state: state)));
  }

  /// The test as it was taken, marked; a test without its text: its printed pages.
  Future<void> _review(Map<String, dynamic> details, List<Map<String, dynamic>> questions) async {
    ReadingTestState? state;
    try {
      state = await fetchReadingTest(widget.id);
    } catch (_) {}
    if (!mounted) return;
    if (state?.content != null) {
      await Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => ReadingReviewPage(
            state: state!,
            title: details['title'] ?? 'The test',
            marks: {for (final q in questions) q['q'] as int: (right: q['right'] == true, key: '${q['key']}')},
          ),
        ),
      );
      return;
    }
    final kind = details['kind'] as String;
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => Scaffold(
          appBar: AppBar(title: Text(details['title'] ?? 'The test')),
          body: Padding(
            padding: const EdgeInsets.all(12),
            child: BookPages(
              book: details['book'],
              pages: List<int>.from(details['pages']),
              parts: [for (final p in details['parts']) (part: p['part'] as int, page: p['page'] as int)],
              partName: kind == 'academic' ? 'Passage' : 'Section',
            ),
          ),
        ),
      ),
    );
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
    final partName = details?['kind'] == 'academic' ? 'Passage' : 'Section';
    final questions = [for (final q in report?.json['questions'] ?? []) q as Map<String, dynamic>];
    final parts = [for (final p in report?.json['parts'] ?? []) p as Map<String, dynamic>];
    final seconds = [
      for (final m in session?.messageJson ?? <Map<String, dynamic>>[])
        if (m['role'] == 'candidate') m['delivery']?['test_seconds'],
    ].firstOrNull;
    return Scaffold(
      appBar: AppBar(
        title: Text(session == null ? 'Reading' : session.title(widget.modeTitle(session.mode))),
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
                          leading: const Icon(Icons.timer_outlined),
                          title: const Text('This test is still in progress'),
                          subtitle: const Text('The clock keeps running on the server.'),
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
                              avatar: const Icon(Icons.article_outlined, size: 18),
                              label: Text('$partName ${i + 1}: ${p['right']} of ${p['of']}'),
                            ),
                          if (seconds is int)
                            Chip(label: Text('${(seconds / 60).ceil()} of ${details?['minutes'] ?? 60} minutes')),
                        ],
                      ),
                      const SizedBox(height: 16),
                      Row(
                        children: [
                          Expanded(child: Text('Your answers', style: theme.textTheme.titleLarge)),
                          if (details != null)
                            OutlinedButton.icon(
                              onPressed: () => _review(details, questions),
                              icon: const Icon(Icons.menu_book_outlined),
                              label: const Text('See the test'),
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

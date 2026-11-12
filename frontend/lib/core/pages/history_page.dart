import 'package:flutter/material.dart';

import '../history.dart';
import '../widgets/band.dart';
import '../widgets/progress_chart.dart';

/// One module's progress over time and its past sessions.
class HistoryPage extends StatefulWidget {
  const HistoryPage({
    super.key,
    required this.module,
    required this.title,
    required this.charts,
    required this.modeTitle,
    required this.openSession,
  });

  final String module; // the module's id, e.g. 'speaking'
  final String title; // e.g. 'Speaking history'
  final List<ChartSpec> charts;
  final String Function(String mode) modeTitle;
  final Future<void> Function(BuildContext context, String id) openSession;

  @override
  State<HistoryPage> createState() => _HistoryPageState();
}

class _HistoryPageState extends State<HistoryPage> {
  List<StoredSession>? _sessions;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final sessions = await fetchSessions(module: widget.module);
      setState(() => _sessions = sessions);
    } catch (e) {
      setState(() => _error = 'Could not load your sessions ($e).');
    }
  }

  Future<void> _open(StoredSession s) async {
    await widget.openSession(context, s.id);
    _load(); // a report may have been written, or the session deleted
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final sessions = _sessions;
    return Scaffold(
      appBar: AppBar(title: Text(widget.title)),
      body: sessions == null
          ? Center(child: _error == null ? const CircularProgressIndicator() : Text(_error!))
          : Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 1100),
                child: ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    Text('Progress', style: theme.textTheme.titleLarge),
                    const SizedBox(height: 8),
                    ProgressCharts(sessions: sessions, charts: widget.charts),
                    const SizedBox(height: 24),
                    Text('Sessions', style: theme.textTheme.titleLarge),
                    const SizedBox(height: 8),
                    if (sessions.isEmpty) const Text('No sessions yet. Practise once and it appears here.'),
                    for (final s in sessions)
                      SessionTile(session: s, title: s.title(widget.modeTitle(s.mode)), onTap: () => _open(s)),
                  ],
                ),
              ),
            ),
    );
  }
}

/// A past session in a list: what it was, when, and its band.
class SessionTile extends StatelessWidget {
  const SessionTile({super.key, required this.session, required this.title, required this.onTap, this.leading});

  final StoredSession session;
  final String title;
  final VoidCallback onTap;
  final Widget? leading;

  @override
  Widget build(BuildContext context) {
    final s = session;
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: leading,
        title: Text(title),
        subtitle: Text('${formatWhen(s.startedAt)} · ${_amount(s)}'),
        trailing: _BandText(s.report),
        onTap: onTap,
      ),
    );
  }
}

String formatWhen(DateTime d) {
  String two(int n) => n.toString().padLeft(2, '0');
  return '${d.year}-${two(d.month)}-${two(d.day)} ${two(d.hour)}:${two(d.minute)}';
}

class _BandText extends StatelessWidget {
  const _BandText(this.report);

  final Report? report;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final overall = report?.overall;
    if (report == null) return Text('No report yet', style: theme.textTheme.bodySmall);
    if (overall == null) return Text('No band', style: theme.textTheme.bodySmall);
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Text('Band', style: theme.textTheme.labelSmall),
        Text(formatBand(overall), style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700)),
      ],
    );
  }
}

/// What a session holds: "12 answers", or a marked test's score ("31 of 40 right").
String _amount(StoredSession s) {
  final json = s.report?.json;
  if (json?['raw'] case final int raw) return '$raw of ${json!['of']} right';
  if (s.details?['finished'] == false) return 'in progress';
  return '${s.answerCount} answer${s.answerCount == 1 ? '' : 's'}';
}

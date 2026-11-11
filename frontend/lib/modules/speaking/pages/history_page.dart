import 'package:flutter/material.dart';

import '../history.dart';
import '../widgets/progress_chart.dart';
import 'session_page.dart';

/// Your progress over time and every past session.
class HistoryPage extends StatefulWidget {
  const HistoryPage({super.key, required this.modeTitle});

  final String Function(String mode) modeTitle;

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
      final sessions = await fetchSessions();
      setState(() => _sessions = sessions);
    } catch (e) {
      setState(() => _error = 'Could not load your sessions ($e).');
    }
  }

  Future<void> _open(StoredSession s) async {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => SessionPage(id: s.id, modeTitle: widget.modeTitle),
      ),
    );
    _load(); // a report may have been written, or the session deleted
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final sessions = _sessions;
    return Scaffold(
      appBar: AppBar(title: const Text('History')),
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
                    ProgressCharts(sessions: sessions),
                    const SizedBox(height: 24),
                    Text('Sessions', style: theme.textTheme.titleLarge),
                    const SizedBox(height: 8),
                    if (sessions.isEmpty) const Text('No sessions yet. Practise once and it appears here.'),
                    for (final s in sessions)
                      Card(
                        margin: const EdgeInsets.only(bottom: 8),
                        child: ListTile(
                          title: Text('${widget.modeTitle(s.mode)}${s.topic == null ? '' : ': ${s.topic}'}'),
                          subtitle: Text(
                            '${_when(s.startedAt)} · ${s.answerCount} answer${s.answerCount == 1 ? '' : 's'}',
                          ),
                          trailing: _BandText(s.report),
                          onTap: () => _open(s),
                        ),
                      ),
                  ],
                ),
              ),
            ),
    );
  }

  String _when(DateTime d) {
    String two(int n) => n.toString().padLeft(2, '0');
    return '${d.year}-${two(d.month)}-${two(d.day)} ${two(d.hour)}:${two(d.minute)}';
  }
}

class _BandText extends StatelessWidget {
  const _BandText(this.report);

  final Report? report;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final overall = report?.overall;
    if (report == null) return Text('No report yet', style: theme.textTheme.bodySmall);
    if (overall == null) return Text('Too short', style: theme.textTheme.bodySmall);
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Text('Band', style: theme.textTheme.labelSmall),
        Text(
          overall == overall.roundToDouble() ? overall.toStringAsFixed(0) : overall.toStringAsFixed(1),
          style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
        ),
      ],
    );
  }
}

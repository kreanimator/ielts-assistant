import 'dart:js_interop';

import 'package:flutter/material.dart';
import 'package:web/web.dart' as web;

import '../../../core/history.dart';
import '../../../core/widgets/report_view.dart';
import '../session.dart';
import '../widgets/corrections_panel.dart';

/// One past session: its band report, then every answer with feedback and its recording.
class SessionPage extends StatefulWidget {
  const SessionPage({super.key, required this.id, required this.modeTitle});

  final String id;
  final String Function(String mode) modeTitle;

  @override
  State<SessionPage> createState() => _SessionPageState();
}

class _SessionPageState extends State<SessionPage> {
  StoredSession? _session;
  String? _error;
  bool _writing = false; // the report is being written
  final _player = web.HTMLAudioElement();
  int? _playing; // the answer being played

  @override
  void initState() {
    super.initState();
    _player.onended = ((web.Event _) => setState(() => _playing = null)).toJS;
    _load();
  }

  @override
  void dispose() {
    _player.pause();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final session = await fetchSession(widget.id);
      setState(() => _session = session);
      if (session.report == null) await _writeReport();
    } catch (e) {
      setState(() => _error = 'Could not load this session ($e).');
    }
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

  void _play(int answer) {
    if (_playing == answer) {
      _player.pause();
      setState(() => _playing = null);
      return;
    }
    _player.src = answerAudioUri(widget.id, answer).toString();
    _player.play();
    setState(() => _playing = answer);
  }

  Future<void> _delete() async {
    final sure = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete this session?'),
        content: const Text('Its answers, recordings and report are removed from this computer.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Delete')),
        ],
      ),
    );
    if (sure != true) return;
    await deleteSession(widget.id);
    if (mounted) Navigator.pop(context, true); // true: the list should reload
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final session = _session;
    return Scaffold(
      appBar: AppBar(
        title: Text(session == null ? 'Session' : _title(session)),
        actions: [
          if (session != null && !_writing)
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
                constraints: const BoxConstraints(maxWidth: 800),
                child: ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    if (_writing) const _Writing() else if (session.report != null) ReportView(report: session.report!),
                    const SizedBox(height: 24),
                    Text('Your answers', style: theme.textTheme.titleLarge),
                    const SizedBox(height: 8),
                    for (final (i, m) in [for (final j in session.messageJson) Message.fromStored(j)].indexed)
                      if (m.fromExaminer)
                        Padding(
                          padding: EdgeInsets.only(bottom: 8, top: i == 0 ? 0 : 4),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Icon(Icons.record_voice_over_outlined, size: 18, color: theme.colorScheme.outline),
                              const SizedBox(width: 8),
                              Expanded(child: Text(m.text, style: theme.textTheme.bodyMedium)),
                            ],
                          ),
                        )
                      else
                        AnswerCard(
                          number: m.answer! + 1,
                          answer: m,
                          full: true,
                          action: m.hasAudio
                              ? IconButton(
                                  tooltip: _playing == m.answer ? 'Stop' : 'Play your answer',
                                  onPressed: () => _play(m.answer!),
                                  icon: Icon(
                                    _playing == m.answer ? Icons.stop_circle_outlined : Icons.play_circle_outline,
                                  ),
                                )
                              : null,
                        ),
                  ],
                ),
              ),
            ),
    );
  }

  String _title(StoredSession s) => s.title(widget.modeTitle(s.mode));
}

class _Writing extends StatelessWidget {
  const _Writing();

  @override
  Widget build(BuildContext context) => const Card(
    child: Padding(
      padding: EdgeInsets.all(20),
      child: Row(
        children: [
          SizedBox.square(dimension: 24, child: CircularProgressIndicator(strokeWidth: 3)),
          SizedBox(width: 16),
          Expanded(child: Text('Writing your band report. This takes about 20 seconds.')),
        ],
      ),
    ),
  );
}

import 'package:flutter/material.dart';

import '../session.dart';
import 'avatar.dart';

/// The examiner's avatar, the conversation, your live transcript and the start button.
class DialoguePanel extends StatefulWidget {
  const DialoguePanel({
    super.key,
    required this.session,
    required this.examinerName,
    required this.female,
    required this.onStart,
    required this.liveCorrections,
    this.headerAction,
  });

  final Session session;
  final String examinerName;
  final bool female;
  final VoidCallback onStart;
  final bool liveCorrections; // false: hide feedback until the session ends
  final Widget? headerAction; // shown top right, e.g. a button that opens the corrections

  @override
  State<DialoguePanel> createState() => _DialoguePanelState();
}

class _DialoguePanelState extends State<DialoguePanel> {
  final _scroll = ScrollController();

  @override
  void initState() {
    super.initState();
    widget.session.addListener(_scrollToEnd);
  }

  @override
  void dispose() {
    widget.session.removeListener(_scrollToEnd);
    _scroll.dispose();
    super.dispose();
  }

  void _scrollToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) _scroll.jumpTo(_scroll.position.maxScrollExtent);
    });
  }

  String _status(Session s) => switch (s.phase) {
        Phase.idle => 'Ready when you are',
        Phase.connecting => 'Starting…',
        Phase.examinerSpeaking => '${widget.examinerName} is speaking',
        Phase.yourTurn => 'Your turn: speak when you are ready',
        Phase.hearing => 'Listening…',
        Phase.thinking => '${widget.examinerName} is thinking',
        Phase.error => s.error,
      };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListenableBuilder(
      listenable: widget.session,
      builder: (context, _) {
        final s = widget.session;
        final panel = Column(
          children: [
            const SizedBox(height: 24),
            Avatar(phase: s.phase, female: widget.female),
            const SizedBox(height: 12),
            Text(widget.examinerName, style: theme.textTheme.titleLarge),
            Text(
              _status(s),
              textAlign: TextAlign.center,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: s.phase == Phase.error ? theme.colorScheme.error : theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 12),
            const Divider(height: 1),
            Expanded(
              child: s.messages.isEmpty
                  ? Center(
                      child: Text(
                        'Choose a training mode, then press Start.',
                        style: theme.textTheme.bodyLarge?.copyWith(color: theme.colorScheme.outline),
                      ),
                    )
                  : ListView(
                      controller: _scroll,
                      padding: const EdgeInsets.all(16),
                      children: [for (final m in s.messages) _Bubble(m, showFeedback: widget.liveCorrections || !s.active)],
                    ),
            ),
            _LiveTranscript(session: s),
            Padding(
              padding: const EdgeInsets.all(16),
              child: s.active
                  ? OutlinedButton.icon(
                      onPressed: s.stop,
                      icon: const Icon(Icons.stop),
                      label: const Text('End session'),
                    )
                  : FilledButton.icon(
                      onPressed: widget.onStart,
                      icon: const Icon(Icons.mic),
                      label: const Text('Start'),
                    ),
            ),
          ],
        );
        final action = widget.headerAction;
        if (action == null) return panel;
        return Stack(children: [panel, Positioned(top: 8, right: 8, child: action)]);
      },
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble(this.message, {required this.showFeedback});

  final Message message;
  final bool showFeedback;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final examiner = message.fromExaminer;
    final feedback = message.feedback;
    return Align(
      alignment: examiner ? Alignment.centerLeft : Alignment.centerRight,
      child: Column(
        crossAxisAlignment: examiner ? CrossAxisAlignment.start : CrossAxisAlignment.end,
        children: [
          Container(
            constraints: const BoxConstraints(maxWidth: 560),
            margin: const EdgeInsets.only(bottom: 4),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: examiner ? theme.colorScheme.surfaceContainerHighest : theme.colorScheme.primaryContainer,
              borderRadius: BorderRadius.circular(16),
            ),
            child: SelectableText(message.text),
          ),
          if (!examiner && showFeedback && feedback != null)
            Text(
              switch (feedback.corrections.length) {
                0 => 'No mistakes found',
                1 => '1 correction',
                final n => '$n corrections',
              },
              style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
          const SizedBox(height: 8),
        ],
      ),
    );
  }
}

/// What you are saying right now, transcribed as you speak.
class _LiveTranscript extends StatelessWidget {
  const _LiveTranscript({required this.session});

  final Session session;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final listening = session.phase == Phase.yourTurn || session.phase == Phase.hearing;
    if (!listening) return const SizedBox.shrink();
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.symmetric(horizontal: 16),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        border: Border.all(color: Colors.green.shade600),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Icon(Icons.mic, color: Colors.green.shade600),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              session.partial.isEmpty ? 'Your live transcript appears here.' : session.partial,
              style: theme.textTheme.bodyLarge?.copyWith(
                fontStyle: FontStyle.italic,
                color: session.partial.isEmpty ? theme.colorScheme.outline : null,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

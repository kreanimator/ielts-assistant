import 'dart:async';

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
    Phase.preparing => 'Prepare your talk: you can make notes',
    Phase.yourTurn => 'Your turn: speak when you are ready',
    Phase.hearing => 'Listening…',
    Phase.thinking => '${widget.examinerName} is thinking',
    Phase.ending => 'Saving your session…',
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
            if (s.active && (s.partTitle != null || s.countdown != null)) ...[
              const SizedBox(height: 8),
              _PartAndClock(session: s),
            ],
            const SizedBox(height: 12),
            const Divider(height: 1),
            if (s.active && s.cueCard != null) _CueCardView(session: s),
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
                      children: [
                        for (final m in s.messages) _Bubble(m, showFeedback: widget.liveCorrections || !s.active),
                      ],
                    ),
            ),
            _LiveTranscript(session: s),
            Padding(
              padding: const EdgeInsets.all(16),
              child: s.phase == Phase.ending
                  ? FilledButton.icon(
                      onPressed: null,
                      icon: const SizedBox.square(dimension: 16, child: CircularProgressIndicator(strokeWidth: 2)),
                      label: const Text('Saving your answers'),
                    )
                  : s.active
                  ? OutlinedButton.icon(
                      onPressed: s.end,
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
        return Stack(
          children: [
            panel,
            Positioned(top: 8, right: 8, child: action),
          ],
        );
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
            Text(switch (feedback.corrections.length) {
              0 => 'No mistakes found',
              1 => '1 correction',
              final n => '$n corrections',
            }, style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
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

/// The part of the test, and the time left for preparing or speaking.
class _PartAndClock extends StatefulWidget {
  const _PartAndClock({required this.session});

  final Session session;

  @override
  State<_PartAndClock> createState() => _PartAndClockState();
}

class _PartAndClockState extends State<_PartAndClock> {
  late final Timer _tick;

  @override
  void initState() {
    super.initState();
    _tick = Timer.periodic(const Duration(milliseconds: 250), (_) => setState(() {}));
  }

  @override
  void dispose() {
    _tick.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final part = widget.session.partTitle;
    final countdown = widget.session.countdown;
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      alignment: WrapAlignment.center,
      children: [
        if (part != null) Chip(label: Text(part), visualDensity: VisualDensity.compact),
        if (countdown != null)
          Chip(
            visualDensity: VisualDensity.compact,
            avatar: Icon(Icons.timer_outlined, size: 18, color: _color(theme, countdown)),
            label: Text(
              '${countdown.label} ${_format(countdown.left)}',
              style: TextStyle(fontFeatures: const [FontFeature.tabularFigures()], color: _color(theme, countdown)),
            ),
          ),
      ],
    );
  }

  Color? _color(ThemeData theme, Countdown c) => c.left.inSeconds < 15 ? theme.colorScheme.error : null;

  String _format(Duration d) {
    final seconds = (d.inMilliseconds / 1000).ceil();
    return '${seconds ~/ 60}:${(seconds % 60).toString().padLeft(2, '0')}';
  }
}

/// The Part 2 topic card, with room for notes like the paper in the real test.
class _CueCardView extends StatefulWidget {
  const _CueCardView({required this.session});

  final Session session;

  @override
  State<_CueCardView> createState() => _CueCardViewState();
}

class _CueCardViewState extends State<_CueCardView> {
  final _notes = TextEditingController();

  @override
  void dispose() {
    _notes.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final card = widget.session.cueCard!;
    final preparing = widget.session.phase == Phase.preparing;
    return ConstrainedBox(
      constraints: const BoxConstraints(maxHeight: 420),
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
        child: Card(
          color: theme.colorScheme.secondaryContainer,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(card.task, style: theme.textTheme.titleMedium),
                const SizedBox(height: 8),
                Text('You should say:', style: theme.textTheme.bodyMedium),
                for (final point in card.points)
                  Padding(
                    padding: const EdgeInsets.only(left: 12, top: 2),
                    child: Text('•  $point', style: theme.textTheme.bodyMedium),
                  ),
                const SizedBox(height: 12),
                TextField(
                  controller: _notes,
                  minLines: 2,
                  maxLines: 5,
                  decoration: const InputDecoration(
                    labelText: 'Your notes (not saved)',
                    border: OutlineInputBorder(),
                    isDense: true,
                  ),
                ),
                if (preparing && card.skippable) ...[
                  const SizedBox(height: 8),
                  Align(
                    alignment: Alignment.centerRight,
                    child: TextButton.icon(
                      onPressed: widget.session.skipPreparation,
                      icon: const Icon(Icons.skip_next),
                      label: const Text('I\'m ready to speak'),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

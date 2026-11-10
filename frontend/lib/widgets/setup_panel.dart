import 'package:flutter/material.dart';

import '../api.dart';

/// Choose the training mode, topic and examiner voice before a session.
class SetupPanel extends StatelessWidget {
  const SetupPanel({
    super.key,
    required this.options,
    required this.mode,
    required this.voice,
    required this.topic,
    required this.tests,
    required this.test,
    required this.onTest,
    required this.enabled,
    required this.onMode,
    required this.onVoice,
    required this.liveCorrections,
    required this.onLiveCorrections,
    required this.onHistory,
  });

  final Options options;
  final String mode, voice;
  final TextEditingController topic;
  final List<BookTest> tests; // imported from your books
  final BookTest? test; // the chosen one, if any
  final ValueChanged<String?> onTest;
  final bool enabled;
  final ValueChanged<String> onMode, onVoice;
  final bool liveCorrections; // can be changed during a session too
  final ValueChanged<bool> onLiveCorrections;
  final VoidCallback onHistory;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('IELTS Speaking', style: text.titleLarge),
        Text('Practice session', style: text.bodyMedium),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: enabled ? onHistory : null,
          icon: const Icon(Icons.history),
          label: const Text('History and progress'),
        ),
        const SizedBox(height: 24),
        Text('Training', style: text.titleSmall),
        const SizedBox(height: 8),
        for (final m in options.modes)
          Card(
            margin: const EdgeInsets.only(bottom: 8),
            child: ListTile(
              enabled: enabled,
              selected: m.id == mode,
              leading: Icon(m.id == mode ? Icons.radio_button_checked : Icons.radio_button_unchecked),
              title: Text(m.title),
              subtitle: Text(m.description),
              onTap: () => onMode(m.id),
            ),
          ),
        if (mode != 'free') ...[
          const SizedBox(height: 16),
          _QuestionsPicker(tests: tests, test: test, mode: mode, enabled: enabled, onTest: onTest),
        ],
        const SizedBox(height: 16),
        TextField(
          controller: topic,
          enabled: enabled && test == null,
          decoration: InputDecoration(
            labelText: mode == 'part2' || mode == 'exam' ? 'Cue card topic (optional)' : 'Topic (optional)',
            hintText: 'e.g. hometown, technology',
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 16),
        DropdownMenu<String>(
          key: ValueKey(voice),
          enabled: enabled,
          expandedInsets: EdgeInsets.zero,
          label: const Text('Examiner voice'),
          initialSelection: voice,
          dropdownMenuEntries: [for (final v in options.voices) DropdownMenuEntry(value: v.id, label: v.label)],
          onSelected: (id) => id == null ? null : onVoice(id),
        ),
        const SizedBox(height: 8),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Live corrections'),
          subtitle: Text(
            mode == 'exam'
                ? 'Always off in the full exam: you see them when it ends.'
                : 'Off: see them only when the session ends, like in the real test.',
          ),
          value: liveCorrections && mode != 'exam',
          onChanged: mode == 'exam' ? null : onLiveCorrections,
        ),
        ListTile(
          contentPadding: EdgeInsets.zero,
          leading: const Icon(Icons.memory),
          title: const Text('Language model'),
          subtitle: Text(options.model),
        ),
      ],
    );
  }
}

/// Where the questions come from: the examiner, or a real test from your books.
class _QuestionsPicker extends StatelessWidget {
  const _QuestionsPicker({
    required this.tests,
    required this.test,
    required this.mode,
    required this.enabled,
    required this.onTest,
  });

  final List<BookTest> tests;
  final BookTest? test;
  final String mode;
  final bool enabled;
  final ValueChanged<String?> onTest;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    if (tests.isEmpty) {
      return Text(
        'To practise with real test questions, import your IELTS books: make books BOOKS=\'path/*.pdf\'',
        style: text.bodySmall,
      );
    }
    final chosen = test;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        DropdownMenu<String>(
          key: ValueKey(chosen?.key),
          enabled: enabled,
          expandedInsets: EdgeInsets.zero,
          menuHeight: 400,
          requestFocusOnTap: false, // a list to pick from, not a text field
          label: const Text('Questions'),
          initialSelection: chosen?.key ?? '',
          dropdownMenuEntries: [
            const DropdownMenuEntry(value: '', label: 'Made up by the examiner'),
            for (final t in tests) DropdownMenuEntry(value: t.key, label: t.label),
          ],
          onSelected: (key) => onTest(key == null || key.isEmpty ? null : key),
        ),
        if (chosen != null)
          Padding(
            padding: const EdgeInsets.only(top: 6, left: 4),
            child: Text(chosen.outline(mode), style: text.bodySmall),
          ),
      ],
    );
  }
}

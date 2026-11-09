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
    required this.enabled,
    required this.onMode,
    required this.onVoice,
  });

  final Options options;
  final String mode, voice;
  final TextEditingController topic;
  final bool enabled;
  final ValueChanged<String> onMode, onVoice;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('IELTS Speaking', style: text.titleLarge),
        Text('Practice session', style: text.bodyMedium),
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
        const SizedBox(height: 16),
        TextField(
          controller: topic,
          enabled: enabled,
          decoration: const InputDecoration(
            labelText: 'Topic (optional)',
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
          dropdownMenuEntries: [
            for (final v in options.voices) DropdownMenuEntry(value: v.id, label: v.label),
          ],
          onSelected: (id) => id == null ? null : onVoice(id),
        ),
        const SizedBox(height: 16),
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

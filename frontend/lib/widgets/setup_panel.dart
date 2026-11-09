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
    required this.liveCorrections,
    required this.onLiveCorrections,
    required this.onHistory,
  });

  final Options options;
  final String mode, voice;
  final TextEditingController topic;
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
          dropdownMenuEntries: [for (final v in options.voices) DropdownMenuEntry(value: v.id, label: v.label)],
          onSelected: (id) => id == null ? null : onVoice(id),
        ),
        const SizedBox(height: 8),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Live corrections'),
          subtitle: const Text('Off: see them only when the session ends, like in the real test.'),
          value: liveCorrections,
          onChanged: onLiveCorrections,
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

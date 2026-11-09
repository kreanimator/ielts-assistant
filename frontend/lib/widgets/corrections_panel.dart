import 'package:flutter/material.dart';

/// Live feedback on each answer. Filled in by the analyst in milestone 3.
class CorrectionsPanel extends StatelessWidget {
  const CorrectionsPanel({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Corrections', style: theme.textTheme.titleLarge),
          const SizedBox(height: 24),
          Icon(Icons.spellcheck, size: 40, color: theme.colorScheme.outline),
          const SizedBox(height: 12),
          Text(
            'Grammar, vocabulary and pronunciation feedback on each answer will appear here.',
            style: theme.textTheme.bodyMedium,
          ),
          const SizedBox(height: 8),
          Text('Coming in the next milestone.', style: theme.textTheme.bodySmall),
        ],
      ),
    );
  }
}

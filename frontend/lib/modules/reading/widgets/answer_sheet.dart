import 'package:flutter/material.dart';

/// The answer sheet: a box for each question, grouped by passage (or section).
class AnswerSheet extends StatelessWidget {
  const AnswerSheet({
    super.key,
    required this.controllers,
    required this.groups,
    required this.partName,
    this.readOnly = false,
  });

  final Map<int, TextEditingController> controllers; // question → its box
  final List<({int first, int last})> groups; // the questions of each part; empty: one list
  final String partName;
  final bool readOnly;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final numbers = controllers.keys.toList()..sort();
    final parts = groups.isEmpty ? [(first: numbers.first, last: numbers.last)] : groups;
    return ListView(
      padding: const EdgeInsets.only(right: 8),
      children: [
        for (final (i, part) in parts.indexed) ...[
          if (groups.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(4, 8, 0, 4),
              child: Text(
                '$partName ${i + 1} · Questions ${part.first}-${part.last}',
                style: theme.textTheme.titleSmall,
              ),
            ),
          for (var q = part.first; q <= part.last; q++)
            if (controllers[q] case final controller?)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(
                  children: [
                    SizedBox(
                      width: 32,
                      child: Text('$q', textAlign: TextAlign.right, style: theme.textTheme.titleSmall),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: TextField(
                        controller: controller,
                        readOnly: readOnly,
                        maxLength: 60,
                        autocorrect: false,
                        enableSuggestions: false,
                        spellCheckConfiguration: const SpellCheckConfiguration.disabled(),
                        textInputAction: TextInputAction.next,
                        decoration: const InputDecoration(
                          isDense: true,
                          counterText: '',
                          border: OutlineInputBorder(),
                          contentPadding: EdgeInsets.symmetric(horizontal: 10, vertical: 10),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
        ],
        const SizedBox(height: 8),
        Text(
          'Write a letter (A, B ...), a numeral (i, ii ...), TRUE / FALSE / NOT GIVEN (or T / F / NG), '
          'YES / NO / NOT GIVEN, or words from the text. Spelling counts.',
          style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
        ),
      ],
    );
  }
}

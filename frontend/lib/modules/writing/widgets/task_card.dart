import 'package:flutter/material.dart';

import '../api.dart';

/// The task as the test prints it: the time, the prompt, the bullet points, how to begin.
class TaskCard extends StatelessWidget {
  const TaskCard({super.key, required this.task});

  final WritingTask task;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final muted = theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Writing Task ${task.task}', style: theme.textTheme.titleMedium),
            Text(task.fromBook ? task.title : 'New task · ${task.title}', style: muted),
            const SizedBox(height: 12),
            Text('You should spend about ${task.minutes} minutes on this task.', style: muted),
            const SizedBox(height: 8),
            Text(task.prompt, style: theme.textTheme.bodyLarge),
            if (task.bullets.isNotEmpty) ...[
              const SizedBox(height: 8),
              const Text('In your letter'),
              for (final b in task.bullets)
                Padding(
                  padding: const EdgeInsets.only(left: 8, top: 4),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const SizedBox(width: 16, child: Text('-')),
                      Expanded(child: Text(b)),
                    ],
                  ),
                ),
            ],
            const SizedBox(height: 12),
            Text('Write at least ${task.words} words.', style: theme.textTheme.titleSmall),
            if (task.task == 1) ...[
              Text('You do NOT need to write any addresses.', style: muted),
              const SizedBox(height: 8),
              Text('Begin your letter as follows:', style: muted),
              Text(task.begin, style: theme.textTheme.bodyLarge),
            ],
          ],
        ),
      ),
    );
  }
}

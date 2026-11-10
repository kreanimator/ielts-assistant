import 'package:flutter/material.dart';

import '../session.dart';

const categoryColors = {
  'grammar': Color(0xFFC62828),
  'vocabulary': Color(0xFF1565C0),
  'fluency': Color(0xFFEF6C00),
  'coherence': Color(0xFF6A1B9A),
};

/// Feedback on each answer, newest first.
class CorrectionsPanel extends StatelessWidget {
  const CorrectionsPanel({super.key, required this.session, required this.live});

  final Session session;
  final bool live; // false: hidden until the session ends

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListenableBuilder(
      listenable: session,
      builder: (context, _) {
        final answers = session.answers;
        final Widget body;
        if (!live && session.active) {
          body = _Note(
            icon: Icons.visibility_off_outlined,
            text: 'Live corrections are off. You will see them when the session ends.',
          );
        } else if (answers.isEmpty) {
          body = _Note(
            icon: Icons.spellcheck,
            text:
                'After each answer, your speaking speed, pauses and pronunciation, and feedback '
                'on grammar, vocabulary, fluency and coherence appear here.',
          );
        } else {
          body = Expanded(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
              children: [for (var i = answers.length - 1; i >= 0; i--) AnswerCard(number: i + 1, answer: answers[i])],
            ),
          );
        }
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text('Corrections', style: theme.textTheme.titleLarge),
            ),
            body,
          ],
        );
      },
    );
  }
}

class _Note extends StatelessWidget {
  const _Note({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 40, color: theme.colorScheme.outline),
          const SizedBox(height: 12),
          Text(text, style: theme.textTheme.bodyMedium),
        ],
      ),
    );
  }
}

/// One answer's measured numbers and corrections.
class AnswerCard extends StatelessWidget {
  const AnswerCard({super.key, required this.number, required this.answer, this.full = false, this.action});

  final int number;
  final Message answer;
  final bool full; // show the whole answer, not two lines
  final Widget? action; // shown next to the title, e.g. a play button

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final feedback = answer.feedback;
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(child: Text('Answer $number', style: theme.textTheme.labelLarge)),
                ?action,
              ],
            ),
            const SizedBox(height: 4),
            Text(
              answer.text,
              maxLines: full ? null : 2,
              overflow: full ? null : TextOverflow.ellipsis,
              style: theme.textTheme.bodySmall?.copyWith(fontStyle: FontStyle.italic),
            ),
            const SizedBox(height: 8),
            if (answer.delivery != null) _DeliveryView(answer.delivery!),
            if (feedback == null && !full)
              const Row(
                children: [
                  SizedBox.square(dimension: 14, child: CircularProgressIndicator(strokeWidth: 2)),
                  SizedBox(width: 8),
                  Text('Checking your answer…'),
                ],
              )
            else if (feedback != null) ...[
              if (feedback.corrections.isEmpty)
                _Line(icon: Icons.check_circle_outline, color: Colors.green.shade700, text: 'No mistakes found.'),
              for (final c in feedback.corrections) _CorrectionView(c),
              _Line(icon: Icons.thumb_up_alt_outlined, color: Colors.green.shade700, text: feedback.good),
              _Line(icon: Icons.lightbulb_outline, color: Colors.amber.shade800, text: feedback.tip),
            ],
          ],
        ),
      ),
    );
  }
}

/// Measured numbers: amber when outside the range of a fluent IELTS answer.
class _DeliveryView extends StatelessWidget {
  const _DeliveryView(this.delivery);

  final Delivery delivery;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final d = delivery;
    String plural(int n, String word) => '$n $word${n == 1 ? '' : 's'}';
    final stats = [
      if (d.wpm != null) (text: '${d.wpm} words/min', warn: d.wpm! < 90 || d.wpm! > 180),
      if (d.pauses != null)
        (text: d.pauses == 0 ? 'No long pauses' : plural(d.pauses!, 'long pause'), warn: d.pauses! >= 3),
      if (d.fillers != null && d.fillers! > 0)
        (text: plural(d.fillers!, 'filler'), warn: d.words != null && d.fillers! / d.words! > 0.06),
      if (d.repetitions != null && d.repetitions! > 0)
        (text: plural(d.repetitions!, 'repetition'), warn: d.repetitions! >= 3),
      if (d.pronunciation != null)
        (text: 'Pronunciation ${(d.pronunciation! * 100).round()}%', warn: d.pronunciation! < 0.84),
    ];
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [for (final s in stats) _Stat(text: s.text, warn: s.warn)],
          ),
          if (d.sounds.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              'Sounds to practise: ${d.sounds.map(_describe).join(', ')}',
              style: theme.textTheme.bodySmall?.copyWith(fontWeight: FontWeight.w500),
            ),
          ],
          for (final w in d.unclearWords)
            Text('${w.word}: heard /${w.heard}/, expected /${w.expected}/', style: theme.textTheme.bodySmall),
        ],
      ),
    );
  }
}

String _describe(({String expected, String heard, int count}) s) =>
    s.heard.isEmpty ? '/${s.expected}/ left out (${s.count}×)' : '/${s.expected}/ said as /${s.heard}/ (${s.count}×)';

class _Stat extends StatelessWidget {
  const _Stat({required this.text, required this.warn});

  final String text;
  final bool warn;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final color = warn ? Colors.amber.shade900 : colors.onSurfaceVariant;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        border: Border.all(color: warn ? Colors.amber.shade700 : colors.outlineVariant),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(text, style: Theme.of(context).textTheme.labelMedium?.copyWith(color: color)),
    );
  }
}

class _CorrectionView extends StatelessWidget {
  const _CorrectionView(this.correction);

  final Correction correction;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = categoryColors[correction.category] ?? theme.colorScheme.primary;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            correction.category.toUpperCase(),
            style: theme.textTheme.labelSmall?.copyWith(color: color, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 2),
          Text.rich(
            TextSpan(
              children: [
                TextSpan(
                  text: correction.original,
                  style: TextStyle(color: theme.colorScheme.error, decoration: TextDecoration.lineThrough),
                ),
                // An icon, not the "→" character: Roboto has no arrow, and a missing
                // character would make Flutter download a fallback font.
                const WidgetSpan(
                  alignment: PlaceholderAlignment.middle,
                  child: Padding(
                    padding: EdgeInsets.symmetric(horizontal: 6),
                    child: Icon(Icons.arrow_forward, size: 14),
                  ),
                ),
                TextSpan(
                  text: correction.better,
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
              ],
            ),
          ),
          Text(correction.why, style: theme.textTheme.bodySmall),
        ],
      ),
    );
  }
}

class _Line extends StatelessWidget {
  const _Line({required this.icon, required this.color, required this.text});

  final IconData icon;
  final Color color;
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 4),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 18, color: color),
        const SizedBox(width: 8),
        Expanded(child: Text(text, style: Theme.of(context).textTheme.bodyMedium)),
      ],
    ),
  );
}

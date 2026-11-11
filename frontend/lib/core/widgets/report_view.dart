import 'package:flutter/material.dart';

import '../history.dart';
import 'band.dart';

/// The band report: overall band, each criterion with its evidence, strengths and priorities.
class ReportView extends StatelessWidget {
  const ReportView({super.key, required this.report});

  final Report report;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (!report.enough) {
      return _Section(
        icon: Icons.info_outline,
        title: 'No band estimate',
        children: [Text(report.note ?? 'This session is too short for band estimates.')],
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            BandBadge(band: report.overall!, large: true),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Estimated overall band', style: theme.textTheme.titleMedium),
                  Text(
                    'A practice estimate from this session, not an official IELTS score.',
                    style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                  ),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        for (final c in report.criteria) _CriterionCard(c),
        if (report.strengths.isNotEmpty)
          _Section(
            icon: Icons.thumb_up_alt_outlined,
            title: 'What you do well',
            children: [for (final s in report.strengths) _Bullet(s)],
          ),
        if (report.priorities.isNotEmpty)
          _Section(
            icon: Icons.flag_outlined,
            title: 'Practise next',
            children: [for (final (i, p) in report.priorities.indexed) _Bullet(p, number: i + 1)],
          ),
      ],
    );
  }
}

class _CriterionCard extends StatelessWidget {
  const _CriterionCard(this.criterion);

  final Criterion criterion;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            BandBadge(band: criterion.band),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(criterion.name, style: theme.textTheme.titleSmall),
                  const SizedBox(height: 4),
                  Text(criterion.summary),
                  for (final e in criterion.evidence)
                    Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Text(
                        e,
                        style: theme.textTheme.bodySmall?.copyWith(
                          fontStyle: FontStyle.italic,
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Section extends StatelessWidget {
  const _Section({required this.icon, required this.title, required this.children});

  final IconData icon;
  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 8, bottom: 8),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(icon, size: 20),
            const SizedBox(width: 8),
            Text(title, style: Theme.of(context).textTheme.titleSmall),
          ],
        ),
        const SizedBox(height: 6),
        ...children,
      ],
    ),
  );
}

class _Bullet extends StatelessWidget {
  const _Bullet(this.text, {this.number});

  final String text;
  final int? number;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(left: 28, bottom: 4),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(width: 20, child: Text(number == null ? '-' : '$number.')),
        Expanded(child: Text(text)),
      ],
    ),
  );
}

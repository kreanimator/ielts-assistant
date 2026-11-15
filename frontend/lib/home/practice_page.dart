import 'package:flutter/material.dart';

import '../core/pages/history_page.dart' show formatWhen;
import '../core/practice.dart';
import 'practice_unit_page.dart';

/// Opens a new unit for a type of mistake (or [unit], one done before).
Future<void> openPracticeUnit(BuildContext context, String type, String title, {String? unit}) => Navigator.push(
  context,
  MaterialPageRoute(
    builder: (context) => PracticeUnitPage(type: type, title: title, unit: unit),
  ),
);

/// The types of mistake you can practise: the ones you make first.
class PracticePage extends StatefulWidget {
  const PracticePage({super.key});

  @override
  State<PracticePage> createState() => _PracticePageState();
}

class _PracticePageState extends State<PracticePage> {
  List<PracticeType>? _types;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final types = await fetchPracticeTypes();
      if (mounted) setState(() => _types = types);
    } catch (e) {
      if (mounted) setState(() => _error = 'Could not load the practice ($e).');
    }
  }

  Future<void> _practise(PracticeType t, {String? unit}) async {
    await openPracticeUnit(context, t.id, t.title, unit: unit);
    _load();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final muted = theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final types = _types;
    final yours = [...?types?.where((t) => t.mistakes > 0)];
    final others = [...?types?.where((t) => t.mistakes == 0)];
    return Scaffold(
      appBar: AppBar(title: const Text('Practice')),
      body: types == null
          ? Center(child: _error == null ? const CircularProgressIndicator() : Text(_error!))
          : Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 1100),
                child: ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    Text(
                      'A short lesson and about ten exercises on one type of mistake. Each unit is written new by '
                      'the AI and takes about half a minute to prepare.',
                      style: muted,
                    ),
                    const SizedBox(height: 24),
                    Text('For your mistakes', style: theme.textTheme.titleLarge),
                    const SizedBox(height: 8),
                    if (yours.isEmpty)
                      Text(
                        'Nothing yet: after a Speaking or Writing session, the types of mistake you made come first '
                        'here. Until then, choose any topic below.',
                        style: muted,
                      ),
                    for (final t in yours) _TypeTile(type: t, onPractise: _practise),
                    const SizedBox(height: 24),
                    Text(yours.isEmpty ? 'All topics' : 'Other topics', style: theme.textTheme.titleLarge),
                    const SizedBox(height: 8),
                    for (final t in others) _TypeTile(type: t, onPractise: _practise),
                  ],
                ),
              ),
            ),
    );
  }
}

class _TypeTile extends StatelessWidget {
  const _TypeTile({required this.type, required this.onPractise});

  final PracticeType type;
  final void Function(PracticeType type, {String? unit}) onPractise;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final t = type;
    final last = t.last;
    final facts = [
      if (t.mistakes > 0) '${t.mistakes} mistake${t.mistakes == 1 ? '' : 's'} in your sessions',
      if (t.improving) 'improving',
      if (last != null) 'last unit ${last.score} of ${last.of} on ${formatWhen(last.date!).split(' ').first}',
    ];
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: Icon(
          last == null ? Icons.circle_outlined : (last.passed ? Icons.check_circle : Icons.timelapse),
          color: last?.passed == true ? Colors.green.shade700 : null,
        ),
        title: Text(t.title),
        subtitle: Text(
          '${t.covers[0].toUpperCase()}${t.covers.substring(1)}${facts.isEmpty ? '' : '\n${facts.join(' · ')}'}',
        ),
        isThreeLine: facts.isNotEmpty,
        trailing: Wrap(
          spacing: 8,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            if (last != null)
              TextButton(
                onPressed: () => onPractise(t, unit: last.unit),
                child: const Text('Last unit'),
              ),
            FilledButton.tonal(onPressed: () => onPractise(t), child: const Text('Practise')),
          ],
        ),
        titleTextStyle: theme.textTheme.titleMedium,
      ),
    );
  }
}

import 'package:flutter/material.dart';

import '../core/practice.dart';

/// One unit: the lesson, the exercises, and their check.
class PracticeUnitPage extends StatefulWidget {
  const PracticeUnitPage({super.key, required this.type, required this.title, this.unit});

  final String type, title;
  final String? unit; // a unit done before, to look at again; null: a new one is written

  @override
  State<PracticeUnitPage> createState() => _PracticeUnitPageState();
}

class _PracticeUnitPageState extends State<PracticeUnitPage> {
  PracticeUnit? _unit;
  String? _error;
  bool _checking = false;
  final _chosen = <int, int>{}; // exercise number → the option chosen
  final _written = <int, TextEditingController>{}; // exercise number → the sentence written

  @override
  void initState() {
    super.initState();
    _load(widget.unit);
  }

  @override
  void dispose() {
    for (final c in _written.values) {
      c.dispose();
    }
    super.dispose();
  }

  /// Shows the unit [id], or writes a new one.
  Future<void> _load(String? id) async {
    setState(() {
      _unit = null;
      _error = null;
      _chosen.clear();
      for (final c in _written.values) {
        c.dispose();
      }
      _written.clear();
    });
    try {
      final unit = id == null ? await startPracticeUnit(widget.type) : await fetchPracticeUnit(id);
      if (!mounted) return;
      setState(() {
        _unit = unit;
        for (final e in unit.exercises) {
          if (e.kind == 'fix') _written[e.n] = TextEditingController(text: e.given is String ? e.given as String : '');
          if (e.kind == 'choice' && e.given is int) _chosen[e.n] = e.given as int;
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(
        () => _error = '$e'.contains('503')
            ? 'The exercises did not come out well enough this time. Please try again.'
            : 'Could not prepare the unit ($e). Is the app still running?',
      );
    }
  }

  Future<void> _check() async {
    final unit = _unit!;
    setState(() => _checking = true);
    try {
      final checked = await checkPracticeUnit(unit.id, {
        ..._chosen,
        for (final w in _written.entries)
          if (w.value.text.trim().isNotEmpty) w.key: w.value.text.trim(),
      });
      if (mounted) setState(() => _unit = checked);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not check your answers ($e).')));
      }
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final unit = _unit;
    return Scaffold(
      appBar: AppBar(title: Text('Practice · ${widget.title}')),
      body: unit == null
          ? Center(
              child: _error == null
                  ? Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const CircularProgressIndicator(),
                        const SizedBox(height: 16),
                        Text(
                          widget.unit == null
                              ? 'Writing your lesson and exercises, and checking them.\nThis takes about half a minute.'
                              : 'Loading…',
                          textAlign: TextAlign.center,
                        ),
                      ],
                    )
                  : Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Padding(
                          padding: const EdgeInsets.all(16),
                          child: Text(_error!, textAlign: TextAlign.center),
                        ),
                        FilledButton(onPressed: () => _load(widget.unit), child: const Text('Try again')),
                      ],
                    ),
            )
          : Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 820),
                child: ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    Text('Lesson', style: theme.textTheme.titleLarge),
                    const SizedBox(height: 8),
                    _Lesson(unit: unit),
                    const SizedBox(height: 24),
                    Text('Exercises', style: theme.textTheme.titleLarge),
                    const SizedBox(height: 8),
                    if (unit.result != null) _Score(result: unit.result!),
                    for (final e in unit.exercises)
                      e.kind == 'choice'
                          ? _Choice(
                              exercise: e,
                              chosen: _chosen[e.n],
                              onChosen: (i) => setState(() => _chosen[e.n] = i),
                            )
                          : _Fix(exercise: e, controller: _written[e.n]!),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 12,
                      runSpacing: 8,
                      children: [
                        if (unit.result == null)
                          FilledButton.icon(
                            onPressed: _checking ? null : _check,
                            icon: _checking
                                ? const SizedBox.square(dimension: 16, child: CircularProgressIndicator(strokeWidth: 2))
                                : const Icon(Icons.fact_check_outlined),
                            label: Text(_checking ? 'Checking' : 'Check my answers'),
                          )
                        else ...[
                          FilledButton.icon(
                            onPressed: () => _load(null),
                            icon: const Icon(Icons.refresh),
                            label: const Text('Another unit on this'),
                          ),
                          OutlinedButton(onPressed: () => Navigator.pop(context), child: const Text('Done')),
                        ],
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'The lesson and the exercises are written by the AI. Each exercise was checked before it '
                      'was shown, but a wrong one can still slip through.',
                      style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.outline),
                    ),
                  ],
                ),
              ),
            ),
    );
  }
}

class _Lesson extends StatelessWidget {
  const _Lesson({required this.unit});

  final PracticeUnit unit;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final green = Colors.green.shade700;
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(unit.intro, style: theme.textTheme.bodyLarge),
            for (final (i, p) in unit.points.indexed) ...[
              const SizedBox(height: 14),
              Text('${i + 1}. ${p.rule}', style: theme.textTheme.titleSmall),
              const SizedBox(height: 4),
              _Marked(icon: Icons.close, color: theme.colorScheme.error, text: p.wrong),
              _Marked(icon: Icons.check, color: green, text: p.right),
            ],
            if (unit.yours.isNotEmpty) ...[
              const Divider(height: 32),
              Text('Your own mistakes of this type', style: theme.textTheme.titleSmall),
              for (final m in unit.yours)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text.rich(
                        TextSpan(
                          children: [
                            TextSpan(
                              text: m.original,
                              style: TextStyle(color: theme.colorScheme.error, decoration: TextDecoration.lineThrough),
                            ),
                            const TextSpan(text: '  →  '),
                            TextSpan(
                              text: m.better,
                              style: TextStyle(color: green, fontWeight: FontWeight.w600),
                            ),
                          ],
                        ),
                      ),
                      Text(m.why, style: theme.textTheme.bodySmall),
                    ],
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

/// A line with a tick or a cross before it.
class _Marked extends StatelessWidget {
  const _Marked({required this.icon, required this.color, required this.text});

  final IconData icon;
  final Color color;
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(left: 12, top: 2),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 18, color: color),
        const SizedBox(width: 6),
        Expanded(child: Text(text)),
      ],
    ),
  );
}

class _Score extends StatelessWidget {
  const _Score({required this.result});

  final PracticeResult result;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      color: result.passed ? Colors.green.shade50 : theme.colorScheme.secondaryContainer,
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: Icon(
          result.passed ? Icons.check_circle : Icons.timelapse,
          color: result.passed ? Colors.green.shade700 : null,
        ),
        title: Text('${result.score} of ${result.of} right', style: const TextStyle(color: Colors.black87)),
        subtitle: Text(
          result.passed
              ? 'Well done. Use it in your next Speaking or Writing session.'
              : 'Read the answers below, then try another unit on this.',
          style: const TextStyle(color: Colors.black87),
        ),
      ),
    );
  }
}

/// The frame of one exercise: its number, and once checked whether it was right and why.
class _ExerciseCard extends StatelessWidget {
  const _ExerciseCard({required this.exercise, required this.children});

  final Exercise exercise;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final e = exercise;
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 32,
              child: e.checked
                  ? Icon(
                      e.right ? Icons.check_circle : Icons.cancel,
                      color: e.right ? Colors.green.shade700 : theme.colorScheme.error,
                    )
                  : Text('${e.n}.', style: theme.textTheme.titleMedium),
            ),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  ...children,
                  if (e.checked && e.why.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Text(e.why, style: theme.textTheme.bodySmall),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Fill the gap with one of three options.
class _Choice extends StatelessWidget {
  const _Choice({required this.exercise, required this.chosen, required this.onChosen});

  final Exercise exercise;
  final int? chosen;
  final ValueChanged<int> onChosen;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final e = exercise;
    return _ExerciseCard(
      exercise: e,
      children: [
        Text(e.sentence, style: theme.textTheme.bodyLarge),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final (i, option) in e.options.indexed)
              ChoiceChip(
                label: Text(option),
                selected: chosen == i,
                onSelected: e.checked ? null : (_) => onChosen(i),
                // Once checked: the right option green, a wrong choice red.
                avatar: !e.checked
                    ? null
                    : i == e.answer
                    ? Icon(Icons.check, size: 18, color: Colors.green.shade700)
                    : (chosen == i ? Icon(Icons.close, size: 18, color: theme.colorScheme.error) : null),
                showCheckmark: !e.checked,
              ),
          ],
        ),
        if (e.checked && chosen == null) ...[
          const SizedBox(height: 4),
          Text('Not answered.', style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.error)),
        ],
      ],
    );
  }
}

/// A sentence with one mistake, to write correctly.
class _Fix extends StatelessWidget {
  const _Fix({required this.exercise, required this.controller});

  final Exercise exercise;
  final TextEditingController controller;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final e = exercise;
    return _ExerciseCard(
      exercise: e,
      children: [
        Text('One mistake. Write the sentence correctly:', style: theme.textTheme.bodySmall),
        const SizedBox(height: 4),
        Text(e.sentence, style: theme.textTheme.bodyLarge?.copyWith(fontStyle: FontStyle.italic)),
        const SizedBox(height: 8),
        TextField(
          controller: controller,
          readOnly: e.checked,
          autocorrect: false,
          enableSuggestions: false,
          spellCheckConfiguration: const SpellCheckConfiguration.disabled(),
          decoration: const InputDecoration(border: OutlineInputBorder(), isDense: true, hintText: 'Your sentence'),
        ),
        if (e.checked && !e.right) ...[
          const SizedBox(height: 8),
          _Marked(icon: Icons.check, color: Colors.green.shade700, text: '${e.answer}'),
        ],
      ],
    );
  }
}

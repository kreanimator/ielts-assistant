import 'dart:async';

import 'package:flutter/material.dart';

import '../core/dashboard.dart';
import '../core/mistakes.dart';
import '../core/pages/history_page.dart' show formatWhen;
import '../modules/registry.dart';
import 'practice_page.dart';

/// Your mistakes from every Speaking and Writing session: by type, with your own examples.
class MistakesPage extends StatefulWidget {
  const MistakesPage({super.key, required this.dashboard});

  final Dashboard dashboard; // for the skills' titles, and to open a session

  @override
  State<MistakesPage> createState() => _MistakesPageState();
}

class _MistakesPageState extends State<MistakesPage> {
  Mistakes? _mistakes;
  String? _error;
  Timer? _again;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _again?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final mistakes = await fetchMistakes();
      if (!mounted) return;
      setState(() {
        _mistakes = mistakes;
        _error = null;
      });
      // The types are worked out in the background: ask again until all have one.
      if (mistakes.pending > 0) _again = Timer(const Duration(seconds: 3), _load);
    } catch (e) {
      if (mounted) setState(() => _error = 'Could not load your mistakes ($e).');
    }
  }

  String _skill(String module) => widget.dashboard.skill(module)?.title ?? module;

  Future<void> _open(MistakeExample e) async {
    final open = skillModules[e.module]?.openSession;
    if (open == null) return;
    _again?.cancel();
    await open(context, e.session, widget.dashboard.skill(e.module)?.modeTitle ?? (mode) => mode);
    _load(); // the session may have been deleted, or its report written again
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final muted = theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final m = _mistakes;
    return Scaffold(
      appBar: AppBar(title: const Text('Your mistakes')),
      body: m == null
          ? Center(child: _error == null ? const CircularProgressIndicator() : Text(_error!))
          : Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 1100),
                child: ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    if (m.isEmpty)
                      Text(
                        'No mistakes yet. After a Speaking or Writing session, its corrections are collected here, '
                        'sorted by the type of mistake.',
                        style: muted,
                      )
                    else
                      Text(
                        '${_count(m.total, 'correction')} from ${_count(m.sessions, 'session')} of Speaking and Writing, '
                        'sorted by the type of mistake. The types are worked out by the AI and can be wrong.',
                        style: muted,
                      ),
                    if (m.pending > 0) ...[
                      const SizedBox(height: 12),
                      const LinearProgressIndicator(),
                      const SizedBox(height: 4),
                      Text(
                        'Working out the type of ${_count(m.pending, 'mistake')}…',
                        style: theme.textTheme.bodySmall,
                      ),
                    ],
                    if (m.types.isNotEmpty) ...[
                      const SizedBox(height: 24),
                      Text('By type', style: theme.textTheme.titleLarge),
                      const SizedBox(height: 4),
                      Text(
                        'The most frequent first. A correction that mends two things counts for both.',
                        style: muted,
                      ),
                      const SizedBox(height: 8),
                      for (final t in m.types)
                        _TypeCard(type: t, most: m.types.first.count, skill: _skill, onOpen: _open),
                    ],
                    if (m.spelling.isNotEmpty) ...[
                      const SizedBox(height: 24),
                      Text('Spelling', style: theme.textTheme.titleLarge),
                      const SizedBox(height: 4),
                      Text('The words you misspelled in Writing, with how you wrote them.', style: muted),
                      const SizedBox(height: 8),
                      Wrap(spacing: 8, runSpacing: 8, children: [for (final w in m.spelling) _SpellingChip(word: w)]),
                    ],
                    if (m.sounds.isNotEmpty) ...[
                      const SizedBox(height: 24),
                      Text('Sounds', style: theme.textTheme.titleLarge),
                      const SizedBox(height: 4),
                      Text(
                        'The sounds heard as another sound in your Speaking answers. '
                        'To practise one, choose Drill in Speaking.',
                        style: muted,
                      ),
                      const SizedBox(height: 8),
                      Wrap(spacing: 8, runSpacing: 8, children: [for (final s in m.sounds) _SoundChip(sound: s)]),
                    ],
                  ],
                ),
              ),
            ),
    );
  }
}

String _count(int n, String noun) => '$n $noun${n == 1 ? '' : 's'}';

/// A type of mistake: how often, where, and your own examples when opened.
class _TypeCard extends StatelessWidget {
  const _TypeCard({required this.type, required this.most, required this.skill, required this.onOpen});

  final MistakeType type;
  final int most; // the count of the most frequent type, for the bar
  final String Function(String module) skill;
  final ValueChanged<MistakeExample> onOpen;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final t = type;
    final where = [for (final e in t.byModule.entries) '${skill(e.key)} ${e.value}'].join(', ');
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      clipBehavior: Clip.antiAlias,
      child: ExpansionTile(
        shape: const Border(),
        title: Row(
          children: [
            Flexible(child: Text(t.title)),
            if (t.improving) ...[
              const SizedBox(width: 8),
              Chip(
                label: const Text('Improving'),
                avatar: Icon(Icons.trending_down, size: 16, color: Colors.green.shade700),
                visualDensity: VisualDensity.compact,
              ),
            ],
          ],
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${t.covers[0].toUpperCase()}${t.covers.substring(1)}'),
            const SizedBox(height: 6),
            ClipRRect(
              borderRadius: BorderRadius.circular(3),
              child: LinearProgressIndicator(value: t.count / most, minHeight: 6),
            ),
            const SizedBox(height: 4),
            Text(
              '$where · in ${_count(t.sessions, 'session')} · last ${formatWhen(t.lastSeen).split(' ').first}',
              style: theme.textTheme.bodySmall,
            ),
          ],
        ),
        trailing: Text('${t.count}×', style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700)),
        childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
        expandedCrossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Divider(),
          for (final e in t.examples) _Example(example: e, skill: skill(e.module), onOpen: () => onOpen(e)),
          if (t.count > t.examples.length)
            Text('The latest ${t.examples.length} of ${t.count}.', style: theme.textTheme.bodySmall),
          if (t.id != 'other')
            Align(
              alignment: Alignment.centerRight,
              child: FilledButton.tonalIcon(
                onPressed: () => openPracticeUnit(context, t.id, t.title),
                icon: const Icon(Icons.school_outlined),
                label: const Text('Practise this'),
              ),
            ),
        ],
      ),
    );
  }
}

/// What you said or wrote, the better words, and why.
class _Example extends StatelessWidget {
  const _Example({required this.example, required this.skill, required this.onOpen});

  final MistakeExample example;
  final String skill;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final e = example;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text.rich(
                  TextSpan(
                    children: [
                      TextSpan(
                        text: e.original,
                        style: TextStyle(color: theme.colorScheme.error, decoration: TextDecoration.lineThrough),
                      ),
                      const TextSpan(text: '  →  '),
                      TextSpan(
                        text: e.better,
                        style: TextStyle(color: Colors.green.shade700, fontWeight: FontWeight.w600),
                      ),
                    ],
                  ),
                ),
                Text(e.why, style: theme.textTheme.bodySmall),
                Text(
                  '$skill · ${formatWhen(e.date)}',
                  style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.outline),
                ),
              ],
            ),
          ),
          IconButton(tooltip: 'Open the session', onPressed: onOpen, icon: const Icon(Icons.open_in_new, size: 18)),
        ],
      ),
    );
  }
}

class _SpellingChip extends StatelessWidget {
  const _SpellingChip({required this.word});

  final Misspelling word;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Chip(
      label: Text.rich(
        TextSpan(
          children: [
            TextSpan(
              text: word.wrong.join(', '),
              style: TextStyle(color: theme.colorScheme.error, decoration: TextDecoration.lineThrough),
            ),
            const TextSpan(text: '  →  '),
            TextSpan(
              text: word.right,
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
            if (word.count > 1) TextSpan(text: '  ${word.count}×'),
          ],
        ),
      ),
    );
  }
}

class _SoundChip extends StatelessWidget {
  const _SoundChip({required this.sound});

  final MissedSound sound;

  @override
  Widget build(BuildContext context) {
    final heard = [for (final h in sound.heard) h.sound.isEmpty ? 'left out' : '/${h.sound}/'].join(', ');
    return Chip(
      label: Text.rich(
        TextSpan(
          children: [
            TextSpan(
              text: '/${sound.sound}/',
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
            TextSpan(text: '  ${sound.count}×  heard as $heard'),
          ],
        ),
      ),
    );
  }
}

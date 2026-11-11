import 'dart:math';

import 'package:flutter/material.dart';

import '../core/api.dart';
import '../core/dashboard.dart';
import '../core/history.dart';
import '../core/pages/history_page.dart';
import '../core/widgets/band.dart';
import '../core/widgets/progress_chart.dart';
import '../modules/registry.dart';

/// The home screen: your estimated bands, a card per skill to practise it, progress and
/// your latest sessions.
class DashboardPage extends StatefulWidget {
  const DashboardPage({super.key});

  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  static const recentCount = 5;

  Dashboard? _dashboard;
  List<StoredSession> _recent = [];
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final dashboard = await fetchDashboard();
      final sessions = await fetchSessions();
      setState(() {
        _dashboard = dashboard;
        _recent = sessions.take(recentCount).toList();
        _error = null;
      });
    } catch (_) {
      setState(() => _error = 'Cannot reach the backend at ${apiUri('/')}.\nStart it with `make start`.');
    }
  }

  /// Opens a page, and refreshes the numbers when you come back.
  Future<void> _visit(Future<void> Function() open) async {
    await open();
    _load();
  }

  void _practise(SkillModule module) => _visit(() => Navigator.push(context, MaterialPageRoute(builder: module.page!)));

  @override
  Widget build(BuildContext context) {
    final dashboard = _dashboard;
    if (dashboard == null) {
      return Scaffold(
        body: Center(
          child: _error == null
              ? const CircularProgressIndicator()
              : Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Padding(
                      padding: const EdgeInsets.all(16),
                      child: Text(_error!, textAlign: TextAlign.center),
                    ),
                    FilledButton(onPressed: _load, child: const Text('Try again')),
                  ],
                ),
        ),
      );
    }
    final theme = Theme.of(context);
    final muted = theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final practised = [
      for (final s in dashboard.skills)
        if (s.available) s,
    ];
    return Scaffold(
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _load,
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1100),
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  Text('IELTS Assistant', style: theme.textTheme.headlineSmall),
                  const SizedBox(height: 4),
                  Text('Practise each skill. Bands are practice estimates, not official IELTS scores.', style: muted),
                  const SizedBox(height: 16),
                  _OverallCard(dashboard: dashboard),
                  const SizedBox(height: 24),
                  Text('Skills', style: theme.textTheme.titleLarge),
                  const SizedBox(height: 8),
                  _Grid(
                    minWidth: 240,
                    children: [
                      for (final skill in dashboard.skills)
                        _SkillCard(
                          skill: skill,
                          module: skillModules[skill.id],
                          recent: dashboard.recent,
                          onPractise: _practise,
                          onHistory: (module) => _visit(() => module.openHistory!(context, skill.modeTitle)),
                        ),
                    ],
                  ),
                  const SizedBox(height: 24),
                  Text('Progress', style: theme.textTheme.titleLarge),
                  const SizedBox(height: 4),
                  Text('The overall band of each session, oldest first.', style: muted),
                  const SizedBox(height: 8),
                  _Grid(
                    minWidth: 320,
                    children: [
                      for (final skill in practised)
                        BandChart(title: skill.title, points: skill.progress, empty: 'No band yet: finish a session'),
                    ],
                  ),
                  const SizedBox(height: 24),
                  Text('Recent sessions', style: theme.textTheme.titleLarge),
                  const SizedBox(height: 8),
                  if (_recent.isEmpty) Text('No sessions yet. Choose a skill above to start.', style: muted),
                  for (final s in _recent) _recentTile(dashboard, s),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _recentTile(Dashboard dashboard, StoredSession s) {
    final skill = dashboard.skill(s.module);
    final module = skillModules[s.module];
    final modeTitle = skill?.modeTitle ?? (String mode) => mode;
    final open = module?.openSession;
    return SessionTile(
      session: s,
      leading: Icon(module?.icon ?? Icons.history),
      title: '${skill?.title ?? s.module} · ${s.title(modeTitle(s.mode))}',
      onTap: open == null ? () {} : () => _visit(() => open(context, s.id, modeTitle)),
    );
  }
}

/// The overall band: the average of the skills that have a band, rounded like IELTS.
class _OverallCard extends StatelessWidget {
  const _OverallCard({required this.dashboard});

  final Dashboard dashboard;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final counted = [
      for (final s in dashboard.skills)
        if (s.band != null) s.title,
    ];
    final String note;
    if (dashboard.overall == null) {
      note = 'Finish a practice session with a band estimate to see your first one.';
    } else if (dashboard.skillsCounted < dashboard.skillCount) {
      note =
          'From ${dashboard.skillsCounted} of ${dashboard.skillCount} skills (${counted.join(', ')}). '
          'The real overall band averages all four.';
    } else {
      note = 'The average of all four skills, rounded like IELTS.';
    }
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            BandBadge(band: dashboard.overall, large: true),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Estimated overall band', style: theme.textTheme.titleMedium),
                  const SizedBox(height: 2),
                  Text(note, style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SkillCard extends StatelessWidget {
  const _SkillCard({
    required this.skill,
    required this.module,
    required this.recent,
    required this.onPractise,
    required this.onHistory,
  });

  final Skill skill;
  final SkillModule? module; // null: the app does not know this skill yet
  final int recent;
  final ValueChanged<SkillModule> onPractise, onHistory;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final muted = theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final module = this.module;
    final ready = skill.available && module?.page != null;
    final String bandNote;
    if (skill.band == null) {
      bandNote = skill.sessions == 0 ? 'Not practised yet' : 'No band yet';
    } else {
      final n = skill.fromSessions;
      bandNote = n == 1 ? 'From your last session' : 'Average of your last $n sessions';
    }
    return Card(
      margin: EdgeInsets.zero,
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: ready ? () => onPractise(module!) : null,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(module?.icon ?? Icons.school_outlined, color: ready ? theme.colorScheme.primary : null),
                  const SizedBox(width: 8),
                  Expanded(child: Text(skill.title, style: theme.textTheme.titleMedium)),
                  if (!ready) Text('Coming soon', style: muted),
                ],
              ),
              const SizedBox(height: 4),
              Text(module?.blurb ?? '', style: muted),
              // A skill that is not ready yet stays a compact card: nothing to show or press.
              if (ready) ...[
                const SizedBox(height: 12),
                Row(
                  children: [
                    BandBadge(band: skill.band),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(bandNote, style: theme.textTheme.bodyMedium),
                          if (skill.sessions > 0)
                            Text(
                              '${skill.sessions} session${skill.sessions == 1 ? '' : 's'} · '
                              'last ${formatWhen(skill.lastPractised!).split(' ').first}',
                              style: muted,
                            ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 4,
                  children: [
                    FilledButton(onPressed: () => onPractise(module!), child: const Text('Practise')),
                    if (module!.openHistory != null)
                      OutlinedButton(onPressed: () => onHistory(module), child: const Text('History')),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// Equal-width columns that fit the width: as many as allow [minWidth] each.
class _Grid extends StatelessWidget {
  const _Grid({required this.minWidth, required this.children});

  final double minWidth;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      final columns = max(1, min(children.length, (constraints.maxWidth / minWidth).floor()));
      final width = (constraints.maxWidth - (columns - 1) * 12) / columns;
      return Wrap(
        spacing: 12,
        runSpacing: 12,
        children: [for (final child in children) SizedBox(width: width, child: child)],
      );
    },
  );
}

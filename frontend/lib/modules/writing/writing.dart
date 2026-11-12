import 'package:flutter/material.dart';

import '../../core/pages/history_page.dart';
import '../../core/widgets/progress_chart.dart';
import 'pages/writing_session_page.dart';

/// The Writing module's entry points for the rest of the app (the dashboard, the history).

/// The criteria of a Writing report, for the progress charts.
const writingCharts = <ChartSpec>[
  (id: 'overall', name: 'Overall'),
  (id: 'task_response', name: 'Task Achievement / Response'),
  (id: 'coherence_cohesion', name: 'Coherence and Cohesion'),
  (id: 'lexical_resource', name: 'Lexical Resource'),
  (id: 'grammar', name: 'Grammar'),
];

Future<void> openWritingSession(BuildContext context, String id, String Function(String mode) modeTitle) =>
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => WritingSessionPage(id: id, modeTitle: modeTitle),
      ),
    );

Future<void> openWritingHistory(BuildContext context, String Function(String mode) modeTitle) => Navigator.push(
  context,
  MaterialPageRoute(
    builder: (_) => HistoryPage(
      module: 'writing',
      title: 'Writing history',
      charts: writingCharts,
      modeTitle: modeTitle,
      openSession: (context, id) => openWritingSession(context, id, modeTitle),
    ),
  ),
);

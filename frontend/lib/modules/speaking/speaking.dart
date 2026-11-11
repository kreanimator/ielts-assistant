import 'package:flutter/material.dart';

import '../../core/pages/history_page.dart';
import '../../core/widgets/progress_chart.dart';
import 'pages/session_page.dart';

/// The Speaking module's entry points for the rest of the app (the dashboard, the history).

/// The criteria of a Speaking report, for the progress charts.
const speakingCharts = <ChartSpec>[
  (id: 'overall', name: 'Overall'),
  (id: 'fluency_coherence', name: 'Fluency and Coherence'),
  (id: 'lexical_resource', name: 'Lexical Resource'),
  (id: 'grammar', name: 'Grammar'),
  (id: 'pronunciation', name: 'Pronunciation'),
];

Future<void> openSpeakingSession(BuildContext context, String id, String Function(String mode) modeTitle) =>
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => SessionPage(id: id, modeTitle: modeTitle),
      ),
    );

Future<void> openSpeakingHistory(BuildContext context, String Function(String mode) modeTitle) => Navigator.push(
  context,
  MaterialPageRoute(
    builder: (_) => HistoryPage(
      module: 'speaking',
      title: 'Speaking history',
      charts: speakingCharts,
      modeTitle: modeTitle,
      openSession: (context, id) => openSpeakingSession(context, id, modeTitle),
    ),
  ),
);

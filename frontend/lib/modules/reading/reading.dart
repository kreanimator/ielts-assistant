import 'package:flutter/material.dart';

import '../../core/pages/history_page.dart';
import '../../core/widgets/progress_chart.dart';
import 'pages/reading_session_page.dart';

/// The Reading module's entry points for the rest of the app (the dashboard, the history).

const readingCharts = <ChartSpec>[(id: 'overall', name: 'Reading band')];

Future<void> openReadingSession(BuildContext context, String id, String Function(String mode) modeTitle) =>
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => ReadingSessionPage(id: id, modeTitle: modeTitle),
      ),
    );

Future<void> openReadingHistory(BuildContext context, String Function(String mode) modeTitle) => Navigator.push(
  context,
  MaterialPageRoute(
    builder: (_) => HistoryPage(
      module: 'reading',
      title: 'Reading history',
      charts: readingCharts,
      modeTitle: modeTitle,
      openSession: (context, id) => openReadingSession(context, id, modeTitle),
    ),
  ),
);

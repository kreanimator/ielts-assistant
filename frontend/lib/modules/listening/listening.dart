import 'package:flutter/material.dart';

import '../../core/pages/history_page.dart';
import '../../core/widgets/progress_chart.dart';
import 'pages/listening_session_page.dart';

/// The Listening module's entry points for the rest of the app (the dashboard, the history).

const listeningCharts = <ChartSpec>[(id: 'overall', name: 'Listening band')];

Future<void> openListeningSession(BuildContext context, String id, String Function(String mode) modeTitle) =>
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => ListeningSessionPage(id: id, modeTitle: modeTitle),
      ),
    );

Future<void> openListeningHistory(BuildContext context, String Function(String mode) modeTitle) => Navigator.push(
  context,
  MaterialPageRoute(
    builder: (_) => HistoryPage(
      module: 'listening',
      title: 'Listening history',
      charts: listeningCharts,
      modeTitle: modeTitle,
      openSession: (context, id) => openListeningSession(context, id, modeTitle),
    ),
  ),
);

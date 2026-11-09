import 'dart:math';

import 'package:flutter/material.dart';

import '../history.dart';

/// How your bands change over sessions: one small chart per criterion, on the same
/// band scale, so the lines never cross each other. Hover or tap for a session's band.
class ProgressCharts extends StatelessWidget {
  const ProgressCharts({super.key, required this.sessions});

  final List<StoredSession> sessions; // any order; only those with band estimates are drawn

  static const charts = [
    (id: 'overall', name: 'Overall'),
    (id: 'fluency_coherence', name: 'Fluency and Coherence'),
    (id: 'lexical_resource', name: 'Lexical Resource'),
    (id: 'grammar', name: 'Grammar'),
    (id: 'pronunciation', name: 'Pronunciation'),
  ];

  @override
  Widget build(BuildContext context) {
    final scored = [
      for (final s in sessions)
        if (s.report?.enough ?? false) s,
    ]..sort((a, b) => a.startedAt.compareTo(b.startedAt));
    if (scored.isEmpty) {
      return Text(
        'Your progress appears here once a session has band estimates.',
        style: Theme.of(context).textTheme.bodyMedium,
      );
    }
    return LayoutBuilder(
      builder: (context, constraints) {
        final columns = max(1, min(charts.length, (constraints.maxWidth / 200).floor()));
        final width = (constraints.maxWidth - (columns - 1) * 12) / columns;
        return Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            for (final c in charts)
              SizedBox(
                width: width,
                child: _BandChart(
                  title: c.name,
                  points: [
                    for (final s in scored)
                      if ((c.id == 'overall' ? s.report!.overall : s.report!.band(c.id)) case final band?)
                        (date: s.startedAt, band: band),
                  ],
                ),
              ),
          ],
        );
      },
    );
  }
}

typedef _Point = ({DateTime date, double band});

class _BandChart extends StatefulWidget {
  const _BandChart({required this.title, required this.points});

  final String title;
  final List<_Point> points;

  @override
  State<_BandChart> createState() => _BandChartState();
}

class _BandChartState extends State<_BandChart> {
  int? _hovered;

  void _pick(Offset position, double width) {
    final n = widget.points.length;
    final index = n == 1
        ? 0
        : ((position.dx - _Painter.left) / (width - _Painter.left - _Painter.right) * (n - 1)).round();
    setState(() => _hovered = index.clamp(0, n - 1));
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final dark = theme.brightness == Brightness.dark;
    final points = widget.points;
    final latest = points.isEmpty ? null : points.last.band;
    final hovered = _hovered == null || points.isEmpty ? null : points[_hovered!];
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 10, 12, 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(widget.title, style: theme.textTheme.labelLarge),
            Text(
              hovered != null
                  ? '${_date(hovered.date)}: band ${_band(hovered.band)}'
                  : latest == null
                  ? 'No estimate yet'
                  : 'Latest: band ${_band(latest)}',
              style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: 6),
            LayoutBuilder(
              builder: (context, constraints) => MouseRegion(
                onHover: (e) => _pick(e.localPosition, constraints.maxWidth),
                onExit: (_) => setState(() => _hovered = null),
                child: GestureDetector(
                  onTapDown: (e) => _pick(e.localPosition, constraints.maxWidth),
                  child: CustomPaint(
                    size: Size(constraints.maxWidth, 110),
                    painter: _Painter(
                      points: points,
                      hovered: _hovered,
                      line: dark ? const Color(0xFF3987E5) : const Color(0xFF2A78D6),
                      surface: theme.cardTheme.color ?? theme.colorScheme.surfaceContainerLow,
                      grid: theme.colorScheme.outlineVariant.withValues(alpha: 0.6),
                      text: theme.textTheme.labelSmall!.copyWith(color: theme.colorScheme.onSurfaceVariant),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

String _band(double b) => b == b.roundToDouble() ? b.toStringAsFixed(0) : b.toStringAsFixed(1);

String _date(DateTime d) => '${d.day}.${d.month.toString().padLeft(2, '0')}';

class _Painter extends CustomPainter {
  _Painter({
    required this.points,
    required this.hovered,
    required this.line,
    required this.surface,
    required this.grid,
    required this.text,
  });

  static const left = 22.0, right = 8.0, top = 6.0, bottom = 6.0;

  final List<_Point> points;
  final int? hovered;
  final Color line, surface, grid;
  final TextStyle text;

  @override
  void paint(Canvas canvas, Size size) {
    final low = min(4.0, points.map((p) => p.band).fold(9.0, min).floorToDouble());
    const high = 9.0;
    final plotWidth = size.width - left - right;
    double y(double band) => top + (high - band) / (high - low) * (size.height - top - bottom);
    double x(int i) => points.length == 1 ? left + plotWidth / 2 : left + i / (points.length - 1) * plotWidth;

    // Hairline grid at every whole band, labelled every other band.
    final gridPaint = Paint()
      ..color = grid
      ..strokeWidth = 1;
    for (var band = low; band <= high; band++) {
      canvas.drawLine(Offset(left, y(band)), Offset(size.width - right, y(band)), gridPaint);
      if ((high - band) % 2 == 0) {
        final label = TextPainter(
          text: TextSpan(text: _band(band), style: text),
          textDirection: TextDirection.ltr,
        )..layout();
        label.paint(canvas, Offset(0, y(band) - label.height / 2));
      }
    }
    if (points.isEmpty) return;

    if (hovered != null) {
      canvas.drawLine(Offset(x(hovered!), top), Offset(x(hovered!), size.height - bottom), gridPaint);
    }
    final path = Path()..moveTo(x(0), y(points[0].band));
    for (var i = 1; i < points.length; i++) {
      path.lineTo(x(i), y(points[i].band));
    }
    canvas.drawPath(
      path,
      Paint()
        ..color = line
        ..strokeWidth = 2
        ..style = PaintingStyle.stroke
        ..strokeJoin = StrokeJoin.round
        ..strokeCap = StrokeCap.round,
    );
    // Dots with a ring in the surface colour; the latest and the hovered one are larger.
    for (var i = 0; i < points.length; i++) {
      final big = i == hovered || i == points.length - 1;
      final center = Offset(x(i), y(points[i].band));
      canvas.drawCircle(center, big ? 6 : 4.5, Paint()..color = surface);
      canvas.drawCircle(center, big ? 4.5 : 3, Paint()..color = line);
    }
  }

  @override
  bool shouldRepaint(_Painter old) =>
      old.points != points || old.hovered != hovered || old.line != line || old.surface != surface;
}

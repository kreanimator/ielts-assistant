import 'package:flutter/material.dart';

/// 6.0 → "6", 6.5 → "6.5".
String formatBand(double band) => band == band.roundToDouble() ? band.toStringAsFixed(0) : band.toStringAsFixed(1);

/// A band in a rounded square, as in the reports and on the dashboard.
class BandBadge extends StatelessWidget {
  const BandBadge({super.key, required this.band, this.large = false});

  final double? band; // null: no estimate yet
  final bool large;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.colorScheme;
    final band = this.band;
    return Container(
      width: large ? 72 : 48,
      height: large ? 72 : 48,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: band == null ? colors.surfaceContainerHighest : colors.primaryContainer,
        borderRadius: BorderRadius.circular(large ? 20 : 14),
      ),
      child: Text(
        band == null ? '–' : formatBand(band),
        style: (large ? theme.textTheme.headlineMedium : theme.textTheme.titleLarge)?.copyWith(
          color: band == null ? colors.onSurfaceVariant : colors.onPrimaryContainer,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

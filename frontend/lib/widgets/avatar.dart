import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';

import '../audio.dart';
import '../session.dart';

/// A drawn examiner face. The mouth follows the loudness of the speech playing,
/// and the ring shows whose turn it is.
class Avatar extends StatefulWidget {
  const Avatar({super.key, required this.phase, required this.female, this.size = 140});

  final Phase phase;
  final bool female;
  final double size;

  @override
  State<Avatar> createState() => _AvatarState();
}

class _AvatarState extends State<Avatar> with SingleTickerProviderStateMixin {
  late final Ticker _ticker;
  double _mouth = 0; // 0 closed .. 1 wide open
  double _blink = 0; // 0 open .. 1 closed

  @override
  void initState() {
    super.initState();
    _ticker = createTicker(_tick)..start();
  }

  void _tick(Duration elapsed) {
    final speaking = widget.phase == Phase.examinerSpeaking;
    final target = speaking ? BrowserAudio.level : 0.0;
    final mouth = _mouth + (target - _mouth) * 0.35; // smooth, so it doesn't flicker
    // Blink for 150 ms every 4 seconds.
    final blink = elapsed.inMilliseconds % 4000 < 150 ? 1.0 : 0.0;
    if ((mouth - _mouth).abs() > 0.01 || blink != _blink) {
      setState(() {
        _mouth = mouth;
        _blink = blink;
      });
    }
  }

  @override
  void dispose() {
    _ticker.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final ring = switch (widget.phase) {
      Phase.examinerSpeaking => colors.primary,
      Phase.yourTurn || Phase.hearing => Colors.green.shade600,
      _ => colors.outlineVariant,
    };
    return SizedBox.square(
      dimension: widget.size,
      child: CustomPaint(
        painter: _FacePainter(
          mouth: _mouth,
          blink: _blink,
          female: widget.female,
          ring: ring,
          background: colors.primaryContainer,
        ),
      ),
    );
  }
}

class _FacePainter extends CustomPainter {
  _FacePainter({
    required this.mouth,
    required this.blink,
    required this.female,
    required this.ring,
    required this.background,
  });

  final double mouth, blink;
  final bool female;
  final Color ring, background;

  static const skin = Color(0xFFF1C7A1);
  static const hair = Color(0xFF4A3426);
  static const features = Color(0xFF3B2A22);

  @override
  void paint(Canvas canvas, Size size) {
    final r = size.width / 2;
    final c = Offset(r, r);
    canvas.drawCircle(c, r, Paint()..color = background);
    canvas.drawCircle(
      c,
      r - 3,
      Paint()
        ..color = ring
        ..style = PaintingStyle.stroke
        ..strokeWidth = 4 + mouth * 3,
    );

    final head = r * 0.55;
    final face = c.translate(0, r * 0.06);
    final hairPaint = Paint()..color = hair;
    if (female) {
      // Long hair behind the head.
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromCenter(center: face.translate(0, head * 0.25), width: head * 2.3, height: head * 2.5),
          Radius.circular(head),
        ),
        hairPaint,
      );
    }
    canvas.drawCircle(face, head, Paint()..color = skin);
    // Hair on top of the head.
    canvas.drawArc(
      Rect.fromCircle(center: face, radius: head * 1.04),
      pi * 1.05,
      pi * 0.9,
      false,
      Paint()
        ..color = hair
        ..style = PaintingStyle.stroke
        ..strokeWidth = head * (female ? 0.35 : 0.28),
    );

    final eye = Paint()..color = features;
    for (final side in [-1, 1]) {
      canvas.drawOval(
        Rect.fromCenter(
          center: face.translate(side * head * 0.38, -head * 0.05),
          width: head * 0.16,
          height: head * 0.2 * (1 - blink * 0.85),
        ),
        eye,
      );
    }

    final mouthCenter = face.translate(0, head * 0.45);
    if (mouth < 0.05) {
      // Resting: a small smile.
      canvas.drawArc(
        Rect.fromCenter(center: mouthCenter.translate(0, -head * 0.08), width: head * 0.5, height: head * 0.25),
        pi * 0.15,
        pi * 0.7,
        false,
        Paint()
          ..color = features
          ..style = PaintingStyle.stroke
          ..strokeWidth = head * 0.06
          ..strokeCap = StrokeCap.round,
      );
    } else {
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromCenter(center: mouthCenter, width: head * 0.42, height: head * (0.06 + mouth * 0.32)),
          Radius.circular(head * 0.2),
        ),
        Paint()..color = const Color(0xFF8E3B3B),
      );
    }
  }

  @override
  bool shouldRepaint(_FacePainter old) =>
      old.mouth != mouth ||
      old.blink != blink ||
      old.ring != ring ||
      old.female != female ||
      old.background != background;
}

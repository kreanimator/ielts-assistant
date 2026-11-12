import 'package:flutter/material.dart';

/// The frame of a computer-delivered test screen (Reading now, Listening later), modelled on the
/// official familiarisation tests: a white header, a grey box with the part's rubric, the work
/// area, and a bar at the bottom with each part, the current part's question numbers (a green
/// line over each answered one) and the button to hand in. Colours, sizes and the three contrast
/// modes are the ones measured in the official demo; see docs/CBT.md.

enum ExamContrast { normal, whiteOnBlack, yellowOnBlack }

const examContrastNames = {
  ExamContrast.normal: 'Black on white',
  ExamContrast.whiteOnBlack: 'White on black',
  ExamContrast.yellowOnBlack: 'Yellow on black',
};

/// Regular, Large, Extra large (the demo's text sizes; the exact factors are not published).
const examTextSizes = {'Regular': 1.0, 'Large': 1.25, 'Extra large': 1.5};

class ExamPalette {
  const ExamPalette({
    required this.background,
    required this.text,
    required this.muted,
    required this.rubric,
    required this.border,
    required this.control,
    required this.current,
    required this.answered,
    required this.unanswered,
    required this.chosen,
    required this.highlight,
    required this.highlightText,
    required this.arrow,
    required this.arrowDisabled,
  });

  final Color background, text, muted, rubric, border, control, current, answered, unanswered;
  final Color chosen; // the row of the chosen option
  final Color highlight, highlightText; // highlighted text in the passage
  final Color arrow, arrowDisabled;

  static const normal = ExamPalette(
    background: Colors.white,
    text: Colors.black,
    muted: Color(0xFF757575), // rgb(117,117,117)
    rubric: Color(0xFFF1F2EC), // rgb(241,242,236)
    border: Color(0xFFD5D5D5), // rgb(213,213,213)
    control: Color(0xFF535353), // rgb(83,83,83): input borders, icons
    current: Color(0xFF418EC8), // rgb(65,142,200): the current question's frame
    answered: Color(0xFF358E14), // rgb(53,142,20)
    unanswered: Color(0xFFD7D7D7), // rgb(215,215,215)
    chosen: Color(0xFFBDD7EE), // ≈ rgb(189,215,238)
    highlight: Color(0xFF7D4A5A), // rgb(125,74,90)
    highlightText: Colors.white,
    arrow: Color(0xFF333333),
    arrowDisabled: Color(0xFFDDDDDD),
  );

  static ExamPalette onBlack(Color text) => ExamPalette(
    background: Colors.black,
    text: text,
    muted: text.withValues(alpha: 0.7),
    rubric: const Color(0xFF1A1A1A),
    border: text.withValues(alpha: 0.5),
    control: text,
    current: const Color(0xFF6CB4F0),
    answered: const Color(0xFF5CC93A),
    unanswered: const Color(0xFF555555),
    chosen: const Color(0xFF1F4466),
    highlight: text,
    highlightText: Colors.black,
    arrow: const Color(0xFF444444),
    arrowDisabled: const Color(0xFF222222),
  );

  static ExamPalette of(ExamContrast c) => switch (c) {
    ExamContrast.normal => normal,
    ExamContrast.whiteOnBlack => onBlack(Colors.white),
    ExamContrast.yellowOnBlack => onBlack(const Color(0xFFFFFF00)),
  };
}

/// The palette for the widgets under it (the plain one when there is none, as on the review page).
class ExamStyle extends InheritedWidget {
  const ExamStyle({super.key, required this.palette, required super.child});

  final ExamPalette palette;

  static ExamPalette of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<ExamStyle>()?.palette ?? ExamPalette.normal;

  @override
  bool updateShouldNotify(ExamStyle old) => old.palette != palette;
}

/// Arial (here Liberation Sans, the same measures) 16 px on 24 px lines, black on white.
ThemeData examTheme(ExamPalette p) {
  final base = ThemeData(
    useMaterial3: true,
    fontFamily: 'LiberationSans',
    fontFamilyFallback: const ['NotoSans'],
    colorScheme:
        ColorScheme.fromSeed(
          seedColor: p.current,
          brightness: p.background == Colors.black ? Brightness.dark : Brightness.light,
        ).copyWith(
          surface: p.background,
          onSurface: p.text,
          primary: p.current,
          outline: p.control,
          error: const Color(0xFFC62828),
        ),
    scaffoldBackgroundColor: p.background,
  );
  const body = TextStyle(fontSize: 16, height: 1.5, letterSpacing: 0);
  return base.copyWith(
    textTheme: base.textTheme
        .apply(bodyColor: p.text, displayColor: p.text)
        .copyWith(
          bodyLarge: body.copyWith(color: p.text),
          bodyMedium: body.copyWith(color: p.text),
          bodySmall: TextStyle(fontSize: 14, height: 1.4, color: p.muted),
          titleMedium: TextStyle(fontSize: 16, height: 1.5, fontWeight: FontWeight.w700, color: p.text),
          titleLarge: TextStyle(fontSize: 17.6, height: 1.2, fontWeight: FontWeight.w700, color: p.text),
        )
        .apply(fontFamily: 'LiberationSans', letterSpacingFactor: 0),
    textSelectionTheme: TextSelectionThemeData(selectionColor: p.current.withValues(alpha: 0.35), cursorColor: p.text),
    scrollbarTheme: ScrollbarThemeData(
      thumbVisibility: const WidgetStatePropertyAll(true),
      thickness: const WidgetStatePropertyAll(12),
      radius: Radius.zero,
      thumbColor: WidgetStatePropertyAll(p.text.withValues(alpha: 0.35)),
    ),
  );
}

/// The header: on the left the test and a line of status ("Audio is playing" in Listening),
/// the time left in the middle, the tools on the right.
class ExamHeader extends StatelessWidget implements PreferredSizeWidget {
  const ExamHeader({
    super.key,
    required this.title,
    this.status,
    required this.secondsLeft,
    this.leading,
    this.actions = const [],
  });

  final String title;
  final Widget? status, leading;
  final int secondsLeft;
  final List<Widget> actions;

  @override
  Size get preferredSize => const Size.fromHeight(56);

  @override
  Widget build(BuildContext context) {
    final p = ExamStyle.of(context);
    final low = secondsLeft <= 5 * 60;
    final narrow = MediaQuery.sizeOf(context).width < 600;
    return Material(
      color: p.background,
      child: Container(
        height: 56,
        padding: EdgeInsets.symmetric(horizontal: narrow ? 4 : 16),
        decoration: BoxDecoration(
          border: Border(bottom: BorderSide(color: p.border)),
        ),
        child: Row(
          children: [
            ?leading,
            Expanded(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: p.text),
                  ),
                  ?status,
                ],
              ),
            ),
            Semantics(
              liveRegion: low,
              child: Text(
                narrow && secondsLeft >= 60 ? '${(secondsLeft / 60).ceil()} min left' : timeLeftText(secondsLeft),
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: low ? const Color(0xFFC62828) : p.text,
                ),
              ),
            ),
            // the tools: a third of the header, or on a narrow screen only the room they need
            Flexible(
              flex: narrow ? 0 : 1,
              fit: narrow ? FlexFit.loose : FlexFit.tight,
              child: IconTheme(
                data: IconThemeData(color: p.text.withValues(alpha: 0.8), size: 24),
                child: Row(
                  mainAxisSize: narrow ? MainAxisSize.min : MainAxisSize.max,
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: actions,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// "59 minutes left", and the seconds in the last minute.
String timeLeftText(int seconds) =>
    seconds >= 60 ? '${(seconds / 60).ceil()} minutes left' : '$seconds second${seconds == 1 ? '' : 's'} left';

/// The grey box above the work area: "Part 1" and what to do.
class RubricBox extends StatelessWidget {
  const RubricBox({super.key, required this.title, required this.text});

  final String title, text;

  @override
  Widget build(BuildContext context) {
    final p = ExamStyle.of(context);
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.fromLTRB(16, 16, 16, 12),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: p.rubric,
        border: Border.all(color: p.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: TextStyle(fontSize: 16, height: 1.5, fontWeight: FontWeight.w700, color: p.text),
          ),
          Text(text, style: TextStyle(fontSize: 16, height: 1.5, color: p.text)),
        ],
      ),
    );
  }
}

/// Two panes side by side; the line between them, with its ↔ handle, can be dragged.
class SplitPane extends StatefulWidget {
  const SplitPane({super.key, required this.left, required this.right});

  final Widget left, right;

  @override
  State<SplitPane> createState() => _SplitPaneState();
}

class _SplitPaneState extends State<SplitPane> {
  double _at = 0.5;

  @override
  Widget build(BuildContext context) {
    final p = ExamStyle.of(context);
    return LayoutBuilder(
      builder: (context, c) {
        const handle = 32.0;
        final left = (c.maxWidth * _at).clamp(240.0, c.maxWidth - 280.0);
        void drag(DragUpdateDetails d) => setState(() => _at = ((left + d.delta.dx) / c.maxWidth).clamp(0.2, 0.8));
        return Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SizedBox(width: left - handle / 2, child: widget.left),
            MouseRegion(
              cursor: SystemMouseCursors.resizeColumn,
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onHorizontalDragUpdate: drag,
                child: SizedBox(
                  width: handle,
                  child: Stack(
                    alignment: Alignment.center,
                    children: [
                      Center(child: Container(width: 1.5, color: p.control)),
                      Semantics(
                        label: 'Drag to resize the panes',
                        child: Container(
                          width: 30,
                          height: 30,
                          decoration: BoxDecoration(
                            color: p.background,
                            border: Border.all(color: p.control),
                            borderRadius: BorderRadius.circular(2),
                          ),
                          child: Icon(Icons.swap_horiz, size: 16, color: p.control),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            Expanded(child: widget.right),
          ],
        );
      },
    );
  }
}

/// A part in the bottom bar.
typedef ExamPart = ({String label, int first, int last});

/// The bar at the bottom: a column per part. The current part lists its question numbers, each
/// under a line (grey, green once answered), the current question framed in blue; the others say
/// how many of their questions are answered. A tap on a number goes to it; on a part, to its
/// first question. The ✓ at the right hands the test in.
class ExamFooter extends StatelessWidget {
  const ExamFooter({
    super.key,
    required this.parts,
    required this.currentPart,
    required this.currentQuestion,
    required this.answered,
    required this.onQuestion,
    required this.onHandIn,
    this.status,
  });

  final List<ExamPart> parts;
  final int currentPart;
  final int? currentQuestion;
  final bool Function(int q) answered;
  final void Function(int q) onQuestion;
  final VoidCallback? onHandIn;
  final String? status;

  static const height = 53.0;
  static const _number = 24.0;

  @override
  Widget build(BuildContext context) {
    final p = ExamStyle.of(context);
    final label = TextStyle(fontSize: 16, color: p.text);
    return Material(
      color: p.background,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (status != null)
            Container(
              color: const Color(0xFFFFF3CD),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
              child: Text(status!, style: const TextStyle(fontSize: 14, color: Color(0xFF6B4E00))),
            ),
          SizedBox(
            height: height,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(
                  child: LayoutBuilder(
                    builder: (context, c) {
                      final current = parts[currentPart];
                      final needed = 90 + (current.last - current.first + 1) * _number;
                      final share = c.maxWidth / parts.length;
                      final wide = needed <= share;
                      final rest = parts.length > 1 ? (c.maxWidth - needed) / (parts.length - 1) : 0.0;
                      final squeezed = !wide && rest < 90;
                      final row = Row(
                        children: [
                          for (final (i, part) in parts.indexed)
                            SizedBox(
                              width: wide ? share : (i == currentPart ? needed : (squeezed ? 90 : rest)),
                              child: i == currentPart
                                  ? _currentPart(part, p, label)
                                  : _otherPart(part, p, label, squeezed),
                            ),
                        ],
                      );
                      return squeezed ? SingleChildScrollView(scrollDirection: Axis.horizontal, child: row) : row;
                    },
                  ),
                ),
                Tooltip(
                  message: 'Hand in your answers',
                  child: Material(
                    color: onHandIn == null ? p.rubric : p.border.withValues(alpha: 0.6),
                    child: InkWell(
                      onTap: onHandIn,
                      child: SizedBox(width: 63, child: Icon(Icons.check, color: p.control)),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _otherPart(ExamPart part, ExamPalette p, TextStyle label, bool short) {
    final count = [for (var q = part.first; q <= part.last; q++) q].where(answered).length;
    return InkWell(
      onTap: () => onQuestion(part.first),
      child: Center(
        child: Text.rich(
          TextSpan(
            children: [
              TextSpan(text: part.label),
              TextSpan(
                text: short ? '  $count/${part.last - part.first + 1}' : '   $count of ${part.last - part.first + 1}',
                style: TextStyle(color: p.muted),
              ),
            ],
          ),
          style: label,
          maxLines: 1,
        ),
      ),
    );
  }

  Widget _currentPart(ExamPart part, ExamPalette p, TextStyle label) {
    return Center(
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: Text(part.label, style: label.copyWith(fontWeight: FontWeight.w700)),
          ),
          for (var q = part.first; q <= part.last; q++)
            Semantics(
              button: true,
              label: 'Question $q, ${answered(q) ? 'answered' : 'not answered'}',
              child: InkWell(
                onTap: () => onQuestion(q),
                child: SizedBox(
                  width: _number,
                  height: height,
                  child: Column(
                    children: [
                      Container(
                        height: 3,
                        margin: const EdgeInsets.symmetric(horizontal: 1),
                        color: answered(q) ? p.answered : p.unanswered,
                      ),
                      const Spacer(),
                      Container(
                        height: 27,
                        alignment: Alignment.center,
                        decoration: q == currentQuestion
                            ? BoxDecoration(
                                border: Border.all(color: p.current, width: 2),
                                borderRadius: BorderRadius.circular(3),
                              )
                            : null,
                        child: Text('$q', style: label.copyWith(fontSize: 15)),
                      ),
                      const Spacer(),
                    ],
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// The previous and next question buttons, at the bottom right above the bar.
class ExamArrows extends StatelessWidget {
  const ExamArrows({super.key, required this.onPrevious, required this.onNext});

  final VoidCallback? onPrevious, onNext;

  @override
  Widget build(BuildContext context) {
    final p = ExamStyle.of(context);
    Widget button(IconData icon, String tip, VoidCallback? onTap, Color color) => Tooltip(
      message: tip,
      child: Material(
        color: onTap == null ? p.arrowDisabled : color,
        child: InkWell(
          onTap: onTap,
          child: SizedBox.square(dimension: 46, child: Icon(icon, color: Colors.white, size: 26)),
        ),
      ),
    );
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        button(Icons.arrow_back, 'Previous question', onPrevious, p.arrow.withValues(alpha: 0.85)),
        const SizedBox(width: 2),
        button(Icons.arrow_forward, 'Next question', onNext, p.background == Colors.black ? p.arrow : Colors.black),
      ],
    );
  }
}

/// The Options screen (the ≡ in the header): go to the submission page, contrast, text size.
class ExamOptionsPage extends StatefulWidget {
  const ExamOptionsPage({super.key, required this.contrast, required this.textSize, required this.onSubmit});

  final ValueNotifier<ExamContrast> contrast;
  final ValueNotifier<String> textSize;
  final VoidCallback onSubmit;

  @override
  State<ExamOptionsPage> createState() => _ExamOptionsPageState();
}

class _ExamOptionsPageState extends State<ExamOptionsPage> {
  String? _open; // 'contrast' or 'size'

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder(
      valueListenable: widget.contrast,
      builder: (context, contrast, _) {
        final p = ExamPalette.of(contrast);
        return Theme(
          data: examTheme(p),
          child: ExamStyle(
            palette: p,
            child: Scaffold(
              backgroundColor: p.background,
              body: SafeArea(
                child: Stack(
                  children: [
                    Align(
                      alignment: Alignment.topCenter,
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 572),
                        child: ListView(
                          padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
                          children: [
                            Center(
                              child: Text(_title, style: TextStyle(fontSize: 22, color: p.text)),
                            ),
                            const SizedBox(height: 20),
                            ..._items(p, contrast),
                          ],
                        ),
                      ),
                    ),
                    Positioned(
                      top: 4,
                      right: 8,
                      child: IconButton(
                        tooltip: _open == null ? 'Close' : 'Back',
                        icon: Icon(_open == null ? Icons.close : Icons.arrow_back, color: p.text),
                        onPressed: () => _open == null ? Navigator.pop(context) : setState(() => _open = null),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  String get _title => switch (_open) {
    'contrast' => 'Contrast',
    'size' => 'Text size',
    _ => 'Options',
  };

  List<Widget> _items(ExamPalette p, ExamContrast contrast) {
    Widget row(IconData icon, String text, VoidCallback onTap, {bool selected = false}) => Container(
      decoration: BoxDecoration(border: Border.all(color: p.border)),
      margin: const EdgeInsets.only(bottom: 0),
      child: ListTile(
        leading: Icon(icon, color: p.muted),
        title: Text(text, style: TextStyle(fontSize: 16, color: p.text)),
        trailing: selected ? Icon(Icons.check, color: p.text) : Icon(Icons.chevron_right, color: p.text),
        onTap: onTap,
      ),
    );
    switch (_open) {
      case 'contrast':
        return [
          for (final c in ExamContrast.values)
            row(Icons.contrast, examContrastNames[c]!, () => widget.contrast.value = c, selected: c == contrast),
        ];
      case 'size':
        return [
          for (final s in examTextSizes.keys)
            ValueListenableBuilder(
              valueListenable: widget.textSize,
              builder: (context, size, _) =>
                  row(Icons.zoom_in, s, () => widget.textSize.value = s, selected: s == size),
            ),
        ];
    }
    return [
      Material(
        color: const Color(0xFFE31837),
        borderRadius: BorderRadius.circular(3),
        child: ListTile(
          leading: const Icon(Icons.send_outlined, color: Colors.white),
          title: const Text('Go to submission page', style: TextStyle(fontSize: 16, color: Colors.white)),
          trailing: const Icon(Icons.chevron_right, color: Colors.white),
          onTap: () {
            Navigator.pop(context);
            widget.onSubmit();
          },
        ),
      ),
      const SizedBox(height: 14),
      row(Icons.contrast, 'Contrast', () => setState(() => _open = 'contrast')),
      row(Icons.zoom_in, 'Text size', () => setState(() => _open = 'size')),
    ];
  }
}

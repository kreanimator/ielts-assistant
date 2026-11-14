import 'package:flutter/material.dart';

import '../../../core/widgets/exam_shell.dart';
import '../api.dart';
import '../widgets/passage_view.dart';
import '../widgets/question_panel.dart';

/// A finished test, as it was taken: each passage beside its questions with your answers, each
/// question marked (its number green or red) and the key's answer under a wrong one.
class ReadingReviewPage extends StatefulWidget {
  const ReadingReviewPage({super.key, required this.state, required this.marks, required this.title});

  final ReadingTestState state;
  final Map<int, ({bool right, String key})> marks;
  final String title;

  @override
  State<ReadingReviewPage> createState() => _ReadingReviewPageState();
}

class _ReadingReviewPageState extends State<ReadingReviewPage> {
  final Map<int, TextEditingController> _controllers = {};
  final Map<int, GlobalKey> _keys = {};
  int _part = 0;
  late bool _printed = !widget.state.content!.web;
  bool _showQuestions = false;

  @override
  void dispose() {
    for (final c in _controllers.values) {
      c.dispose();
    }
    super.dispose();
  }

  String _value(int q) => widget.state.answers['$q'] ?? '';

  late final _access = AnswerAccess(
    value: _value,
    set: (_, _) {},
    controller: (q) => _controllers.putIfAbsent(q, () => TextEditingController(text: _value(q))),
    keyOf: (q) => _keys.putIfAbsent(q, GlobalKey.new),
    readOnly: true,
    marks: widget.marks,
  );

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final state = widget.state;
    final parts = state.content!.parts;
    final part = parts[_part];
    int right(ReadingPartText p) =>
        [for (var q = p.first; q <= p.last; q++) q].where((q) => widget.marks[q]?.right == true).length;
    final passage = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (part.pages.isNotEmpty)
          Padding(
            padding: const EdgeInsets.fromLTRB(8, 4, 8, 0),
            child: Align(
              alignment: Alignment.centerLeft,
              child: SegmentedButton<bool>(
                showSelectedIcon: false,
                style: const ButtonStyle(visualDensity: VisualDensity.compact),
                segments: const [
                  ButtonSegment(value: false, label: Text('Text')),
                  ButtonSegment(value: true, label: Text('As printed')),
                ],
                selected: {_printed},
                onSelectionChanged: (s) => setState(() => _printed = s.first),
              ),
            ),
          ),
        Expanded(
          child: PassageView(
            key: PageStorageKey('review-passage-$_part-$_printed'),
            book: state.book,
            part: part,
            printed: _printed && part.pages.isNotEmpty,
            textScale: 1,
          ),
        ),
      ],
    );
    final questions = QuestionPanel(
      key: PageStorageKey('review-questions-$_part'),
      book: state.book,
      part: part,
      access: _access,
    );
    return Theme(
      data: examTheme(ExamPalette.normal),
      child: Scaffold(
        appBar: AppBar(title: Text(widget.title)),
        body: LayoutBuilder(
          builder: (context, constraints) {
            final wide = constraints.maxWidth >= 900;
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
                  child: Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      for (final (i, p) in parts.indexed)
                        ChoiceChip(
                          label: Text('${state.partName} ${p.part}: ${right(p)} of ${p.last - p.first + 1}'),
                          selected: i == _part,
                          onSelected: (_) => setState(() => _part = i),
                        ),
                      if (!wide)
                        ActionChip(
                          avatar: Icon(_showQuestions ? Icons.article_outlined : Icons.checklist, size: 18),
                          label: Text(_showQuestions ? 'The passage' : 'The questions'),
                          onPressed: () => setState(() => _showQuestions = !_showQuestions),
                        ),
                    ],
                  ),
                ),
                Divider(height: 1, color: theme.colorScheme.outlineVariant),
                Expanded(
                  child: wide
                      ? Row(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Expanded(child: passage),
                            VerticalDivider(width: 1, color: theme.colorScheme.outlineVariant),
                            Expanded(child: questions),
                          ],
                        )
                      : IndexedStack(index: _showQuestions ? 1 : 0, children: [passage, questions]),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

import 'package:flutter/material.dart';

import '../../../core/widgets/exam_shell.dart';
import '../api.dart';

/// How the questions read and change the answers (kept by the test page).
class AnswerAccess {
  const AnswerAccess({
    required this.value,
    required this.set,
    required this.controller,
    required this.keyOf,
    this.readOnly = false,
    this.marks,
    this.current,
    this.onFocus,
  });

  final String Function(int q) value;
  final void Function(int q, String answer) set;
  final TextEditingController Function(int q) controller; // for the gaps
  final GlobalKey Function(int q) keyOf; // to scroll to a question
  final bool readOnly;

  /// After the test: each question's mark and the key's answer, shown beside it.
  final Map<int, ({bool right, String key})>? marks;

  /// The question being worked on (framed in blue), and how a control says it is now.
  final int? current;
  final void Function(int q)? onFocus;

  /// Sets an answer and makes its question the current one.
  void choose(int q, String answer) {
    set(q, answer);
    onFocus?.call(q);
  }
}

/// Instructions, with their key words in bold as on screen ("TRUE", "NO MORE THAN TWO WORDS").
final _keyWords = RegExp(r"\b[A-Z]{2,}(?:[ /]+(?:[A-Z]{2,}|A|OR))*\b");

TextSpan _instruction(String line) {
  final spans = <TextSpan>[];
  var at = 0;
  for (final m in _keyWords.allMatches(line)) {
    if (m.start > at) spans.add(TextSpan(text: line.substring(at, m.start)));
    spans.add(
      TextSpan(
        text: m[0],
        style: const TextStyle(fontWeight: FontWeight.w700),
      ),
    );
    at = m.end;
  }
  if (at < line.length) spans.add(TextSpan(text: line.substring(at)));
  return TextSpan(children: spans);
}

/// One part's questions, group by group, each question with its control, like the
/// computer-delivered test.
class QuestionPanel extends StatelessWidget {
  const QuestionPanel({super.key, required this.book, required this.part, required this.access, this.controller});

  final String book;
  final ReadingPartText part;
  final AnswerAccess access;
  final ScrollController? controller;

  @override
  Widget build(BuildContext context) {
    // all built (a part has a dozen questions or so), so the bar can scroll to any of them
    return SingleChildScrollView(
      controller: controller,
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [for (final g in part.groups) _Group(book: book, group: g, access: access)],
      ),
    );
  }
}

class _Group extends StatelessWidget {
  const _Group({required this.book, required this.group, required this.access});

  final String book;
  final QuestionGroup group;
  final AnswerAccess access;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final g = group;
    final listed = g.options.where((o) => o.text.isNotEmpty).toList();
    return Padding(
      padding: const EdgeInsets.only(bottom: 36),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            g.first == g.last ? 'Question ${g.first}' : 'Questions ${g.first}–${g.last}',
            style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
          ),
          for (final line in g.instructions) Text.rich(_instruction(line), style: theme.textTheme.bodyMedium),
          if (g.printed) ...[
            const SizedBox(height: 8),
            for (final p in g.pictures) _Printed(book: book, page: p.page, box: p.box),
          ],
          const SizedBox(height: 8),
          if (listed.isNotEmpty && g.type == 'match') _OptionList(listed),
          ...switch (g.type) {
            'tfng' ||
            'ynng' => [for (final q in g.questions) _Statement(group: g, q: q.q, text: q.text, access: access)],
            'choice' => [
              for (final q in g.questions) _Choice(q: q.q, text: q.text, options: q.options, access: access),
            ],
            'multi' => [_Multi(group: g, access: access)],
            'match' => [for (final q in g.questions) _Match(group: g, q: q.q, text: q.text, access: access)],
            'notes' when !g.printed => [_Notes(group: g, access: access)],
            _ => [for (final q in g.questions) _GapLine(q: q.q, text: q.text, access: access)],
          },
        ],
      ),
    );
  }
}

/// A group as the book prints it (a table, a diagram, or text that could not be read for sure).
class _Printed extends StatelessWidget {
  const _Printed({required this.book, required this.page, required this.box});

  final String book;
  final int page;
  final List<double> box;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(border: Border.all(color: theme.colorScheme.outlineVariant)),
      child: Image.network(
        cropPicture(book, page, box),
        width: double.infinity,
        fit: BoxFit.fitWidth,
        filterQuality: FilterQuality.medium,
        errorBuilder: (context, error, stack) =>
            const Padding(padding: EdgeInsets.all(12), child: Text('This part of the page could not be loaded.')),
      ),
    );
  }
}

/// The number of a question, as a small box, with its mark after the test.
class _Number extends StatelessWidget {
  const _Number(this.q, this.access);

  final int q;
  final AnswerAccess access;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final mark = access.marks?[q];
    final p = ExamStyle.of(context);
    final color = mark == null
        ? p.text
        : mark.right
        ? Colors.green.shade700
        : theme.colorScheme.error;
    final frame = mark != null ? color : (access.current == q ? p.current : null);
    return Container(
      key: access.keyOf(q),
      padding: const EdgeInsets.fromLTRB(2, 0, 2, 0),
      margin: const EdgeInsets.only(right: 6),
      decoration: BoxDecoration(
        border: Border.all(color: frame ?? Colors.transparent, width: 2),
        borderRadius: BorderRadius.circular(3),
      ),
      child: Text(
        '$q',
        style: TextStyle(fontSize: 16, height: 1.5, fontWeight: FontWeight.w700, color: color),
      ),
    );
  }
}

/// After the test: the key's answer under a wrong one.
class _KeyNote extends StatelessWidget {
  const _KeyNote(this.q, this.access);

  final int q;
  final AnswerAccess access;

  @override
  Widget build(BuildContext context) {
    final mark = access.marks?[q];
    if (mark == null || mark.right) return const SizedBox.shrink();
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(left: 40, top: 2),
      child: Text(
        '$q: the answer is ${mark.key.split(RegExp(r'\s*//+\s*')).join(' or ')}',
        style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.error),
      ),
    );
  }
}

/// TRUE / FALSE / NOT GIVEN (or YES / NO / NOT GIVEN) for a statement.
class _Statement extends StatelessWidget {
  const _Statement({required this.group, required this.q, required this.text, required this.access});

  final QuestionGroup group;
  final int q;
  final String text;
  final AnswerAccess access;

  @override
  Widget build(BuildContext context) {
    final choices = group.type == 'ynng' ? const ['YES', 'NO', 'NOT GIVEN'] : const ['TRUE', 'FALSE', 'NOT GIVEN'];
    final value = access.value(q);
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _Number(q, access),
              Expanded(child: Text(text.isEmpty ? 'Statement $q (see above)' : text)),
            ],
          ),
          const SizedBox(height: 4),
          for (final c in choices)
            _OptionTile(
              option: (letter: '', text: c),
              selected: value == c,
              onTap: access.readOnly ? null : () => access.choose(q, c),
            ),
          _KeyNote(q, access),
        ],
      ),
    );
  }
}

/// A round button and its text: one of a question's options.
class _OptionTile extends StatelessWidget {
  const _OptionTile({required this.option, required this.selected, required this.onTap, this.square = false});

  final ReadingOption option;
  final bool selected, square;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final p = ExamStyle.of(context);
    final icon = square
        ? (selected ? Icons.check_box : Icons.check_box_outline_blank)
        : (selected ? Icons.radio_button_checked : Icons.radio_button_unchecked);
    return Material(
      color: selected ? p.chosen : Colors.transparent,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 8),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Icon(icon, size: 16, color: p.control),
              ),
              const SizedBox(width: 8),
              if (option.letter.isNotEmpty)
                SizedBox(
                  width: 22,
                  child: Text(option.letter, style: const TextStyle(fontWeight: FontWeight.w700)),
                ),
              Expanded(child: Text(option.text)),
            ],
          ),
        ),
      ),
    );
  }
}

/// A multiple-choice question: one of its options.
class _Choice extends StatelessWidget {
  const _Choice({required this.q, required this.text, required this.options, required this.access});

  final int q;
  final String text;
  final List<ReadingOption> options;
  final AnswerAccess access;

  @override
  Widget build(BuildContext context) {
    final value = access.value(q);
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _Number(q, access),
              Expanded(child: Text(text)),
            ],
          ),
          const SizedBox(height: 4),
          Padding(
            padding: EdgeInsets.zero,
            child: Column(
              children: [
                for (final o in options)
                  _OptionTile(
                    option: o,
                    selected: value == o.letter,
                    onTap: access.readOnly ? null : () => access.choose(q, value == o.letter ? '' : o.letter),
                  ),
              ],
            ),
          ),
          _KeyNote(q, access),
        ],
      ),
    );
  }
}

/// "Choose TWO letters": the chosen letters, in order, answer the group's questions.
class _Multi extends StatelessWidget {
  const _Multi({required this.group, required this.access});

  final QuestionGroup group;
  final AnswerAccess access;

  @override
  Widget build(BuildContext context) {
    final numbers = group.numbers.toList();
    final chosen = [for (final q in numbers) access.value(q)].where((a) => a.isNotEmpty).toSet();

    void toggle(String letter) {
      final next = {...chosen};
      if (!next.remove(letter)) {
        if (next.length >= numbers.length) return; // as many as there are questions
        next.add(letter);
      }
      final sorted = next.toList()..sort();
      for (final (i, q) in numbers.indexed) {
        access.set(q, i < sorted.length ? sorted[i] : '');
      }
      access.onFocus?.call(numbers.first);
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final q in numbers) _Number(q, access),
            Expanded(
              child: Text(group.stem, style: const TextStyle(fontWeight: FontWeight.w500)),
            ),
          ],
        ),
        const SizedBox(height: 4),
        Text('Choose ${numbers.length}: ${chosen.length} chosen.', style: Theme.of(context).textTheme.bodySmall),
        for (final o in group.options)
          _OptionTile(
            option: o,
            square: true,
            selected: chosen.contains(o.letter),
            onTap: access.readOnly ? null : () => toggle(o.letter),
          ),
        for (final q in numbers) _KeyNote(q, access),
      ],
    );
  }
}

/// The options of a matching group (people, endings, headings), listed once above its questions.
class _OptionList extends StatelessWidget {
  const _OptionList(this.options);

  final List<ReadingOption> options;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(border: Border.all(color: ExamStyle.of(context).border)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final o in options)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    width: 36,
                    child: Text(o.letter, style: const TextStyle(fontWeight: FontWeight.w700)),
                  ),
                  Expanded(child: Text(o.text)),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

/// A question answered with a letter (or a numeral) from a list.
class _Match extends StatelessWidget {
  const _Match({required this.group, required this.q, required this.text, required this.access});

  final QuestionGroup group;
  final int q;
  final String text;
  final AnswerAccess access;

  @override
  Widget build(BuildContext context) {
    final p = ExamStyle.of(context);
    final value = access.value(q);
    final letters = [for (final o in group.options) o.letter];
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              _Number(q, access),
              if (text.isNotEmpty) Flexible(child: Text(text)),
              const SizedBox(width: 10),
              // the choice sits beside its question, in a box like a gap's
              Container(
                width: 76,
                height: 28,
                padding: const EdgeInsets.only(left: 8),
                decoration: BoxDecoration(
                  color: letters.contains(value) ? p.chosen : null,
                  border: Border.all(color: access.current == q ? p.current : p.control, width: access.current == q ? 2 : 1),
                  borderRadius: BorderRadius.circular(3),
                ),
                child: DropdownButton<String>(
                  value: letters.contains(value) ? value : null,
                  isExpanded: true,
                  isDense: true,
                  underline: const SizedBox.shrink(),
                  iconSize: 20,
                  dropdownColor: p.background,
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: p.text, fontFamily: 'LiberationSans'),
                  onTap: () => access.onFocus?.call(q),
                  onChanged: access.readOnly ? null : (v) => access.choose(q, v ?? ''),
                  items: [
                    const DropdownMenuItem(value: '', child: Text('—')),
                    for (final l in letters) DropdownMenuItem(value: l, child: Text(l)),
                  ],
                ),
              ),
            ],
          ),
          _KeyNote(q, access),
        ],
      ),
    );
  }
}

/// A box to type a word or two in.
class _Gap extends StatelessWidget {
  const _Gap(this.q, this.access);

  final int q;
  final AnswerAccess access;

  @override
  Widget build(BuildContext context) {
    final mark = access.marks?[q];
    final theme = Theme.of(context);
    final color = mark == null ? null : (mark.right ? Colors.green.shade700 : theme.colorScheme.error);
    final p = ExamStyle.of(context);
    final controller = access.controller(q);
    OutlineInputBorder edge(Color c, double w) => OutlineInputBorder(
      borderRadius: BorderRadius.circular(3),
      borderSide: BorderSide(color: c, width: w),
    );
    return SizedBox(
      key: access.keyOf(q),
      width: 150,
      child: Stack(
        alignment: Alignment.center,
        children: [
          TextField(
            controller: controller,
            readOnly: access.readOnly,
            onTap: () => access.onFocus?.call(q),
            style: theme.textTheme.bodyMedium?.copyWith(height: 1.2),
            decoration: InputDecoration(
              isDense: true,
              contentPadding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
              enabledBorder: edge(color ?? (access.current == q ? p.current : p.control), color == null ? 1 : 2),
              focusedBorder: edge(p.current, 2),
              border: edge(p.control, 1),
            ),
          ),
          // the number shows in the box until something is typed
          IgnorePointer(
            child: ValueListenableBuilder(
              valueListenable: controller,
              builder: (context, v, _) => v.text.isEmpty
                  ? Text(
                      '$q',
                      style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: p.text),
                    )
                  : const SizedBox.shrink(),
            ),
          ),
        ],
      ),
    );
  }
}

/// A sentence or question with its gap: in place of its dots, or after it.
class _GapLine extends StatelessWidget {
  const _GapLine({required this.q, required this.text, required this.access});

  final int q;
  final String text;
  final AnswerAccess access;

  @override
  Widget build(BuildContext context) {
    final at = text.indexOf('…');
    final gap = WidgetSpan(alignment: PlaceholderAlignment.middle, child: _Gap(q, access));
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text.rich(
            TextSpan(
              children: [
                if (text.isEmpty)
                  gap
                else if (at < 0) ...[
                  TextSpan(text: '$text  '),
                  gap,
                ] else ...[
                  TextSpan(text: text.substring(0, at)),
                  gap,
                  TextSpan(text: text.substring(at + 1)),
                ],
              ],
            ),
            style: const TextStyle(height: 2.2),
          ),
          _KeyNote(q, access),
        ],
      ),
    );
  }
}

/// Notes or a summary, with their gaps where the book prints them.
class _Notes extends StatelessWidget {
  const _Notes({required this.group, required this.access});

  final QuestionGroup group;
  final AnswerAccess access;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final line in group.notes)
            Text.rich(
              TextSpan(
                children: [
                  for (final piece in line)
                    if (piece is int)
                      WidgetSpan(alignment: PlaceholderAlignment.middle, child: _Gap(piece, access))
                    else
                      TextSpan(text: piece as String),
                ],
              ),
              style: const TextStyle(height: 2.2),
            ),
          for (final q in group.numbers) _KeyNote(q, access),
        ],
      ),
    );
  }
}

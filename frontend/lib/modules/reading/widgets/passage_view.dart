import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:web/web.dart' as web;

import '../../../core/widgets/exam_shell.dart';
import '../api.dart';

/// A stretch of a passage the test taker highlighted, with a note if they wrote one.
class PassageMark {
  PassageMark({
    required this.part,
    required this.block,
    required this.start,
    required this.end,
    required this.text,
    this.note,
  });

  PassageMark.fromJson(Map<String, dynamic> j)
    : part = j['part'],
      block = j['block'],
      start = j['start'],
      end = j['end'],
      text = j['text'],
      note = j['note'];

  final int part, block, start, end; // the part's number, the passage block, the characters
  final String text;
  String? note; // null: a highlight only

  Map<String, dynamic> toJson() => {
    'part': part,
    'block': block,
    'start': start,
    'end': end,
    'text': text,
    'note': note,
  };
}

/// The highlights and notes of one test, kept in the browser (they are the test taker's
/// scribbles, not answers: the server does not need them).
class PassageMarks extends ChangeNotifier {
  PassageMarks(this.session) {
    try {
      final saved = web.window.localStorage.getItem(_key);
      if (saved != null) all.addAll([for (final m in jsonDecode(saved)) PassageMark.fromJson(m)]);
    } catch (_) {}
  }

  final String session;
  final List<PassageMark> all = [];

  String get _key => 'reading-marks-$session';

  List<PassageMark> get notes => [
    for (final m in all)
      if (m.note != null) m,
  ];

  List<PassageMark> of(int part, int block) => [
    for (final m in all)
      if (m.part == part && m.block == block) m,
  ]..sort((a, b) => a.start.compareTo(b.start));

  /// Highlights the stretch (what it overlaps is replaced).
  PassageMark add(int part, int block, int start, int end, String text, {String? note}) {
    all.removeWhere((m) => m.part == part && m.block == block && m.start < end && start < m.end);
    final mark = PassageMark(part: part, block: block, start: start, end: end, text: text, note: note);
    all.add(mark);
    changed();
    return mark;
  }

  void remove(PassageMark mark) {
    all.remove(mark);
    changed();
  }

  void changed() {
    notifyListeners();
    try {
      web.window.localStorage.setItem(_key, jsonEncode([for (final m in all) m.toJson()]));
    } catch (_) {}
  }

  /// When the test is handed in.
  void forget() {
    try {
      web.window.localStorage.removeItem(_key);
    } catch (_) {}
  }
}

/// A part's passage as text: its titles, and its paragraphs with their letters (A, B, ...).
/// It can also be shown as the book prints it (its pages), to check a word the text got wrong
/// or to see a picture. With [marks], a right click on selected text offers Highlight and Note,
/// as in the computer-delivered test.
class PassageView extends StatelessWidget {
  const PassageView({
    super.key,
    required this.book,
    required this.part,
    required this.printed,
    required this.textScale,
    this.marks,
    this.onNote,
    this.controller,
  });

  final String book;
  final ReadingPartText part;
  final bool printed;
  final double textScale;
  final PassageMarks? marks;
  final void Function(PassageMark mark)? onNote; // a note was started: show the notes
  final ScrollController? controller;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (printed) {
      return ListView(
        controller: controller,
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        children: [
          for (final page in part.pages)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Image.network(
                pagePicture(book, page),
                fit: BoxFit.fitWidth,
                filterQuality: FilterQuality.medium,
                errorBuilder: (context, error, stack) =>
                    SizedBox(height: 120, child: Center(child: Text('Page $page could not be loaded.'))),
              ),
            ),
        ],
      );
    }
    final body = theme.textTheme.bodyLarge!;
    final lettered = part.passage.any((b) => b.letter != null);
    Widget text(int i, TextStyle style, {TextAlign? align}) => marks == null
        ? SelectableText(part.passage[i].text, style: style, textAlign: align)
        : _Marked(part: part.part, block: i, text: part.passage[i].text, style: style, marks: marks!, onNote: onNote);
    return MediaQuery(
      data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(textScale)),
      child: ListenableBuilder(
        listenable: marks ?? const AlwaysStoppedAnimation(0),
        builder: (context, _) => ListView(
          controller: controller,
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 72),
          children: [
            for (final (i, block) in part.passage.indexed)
              if (block.note)
                Padding(
                  padding: const EdgeInsets.only(top: 8, bottom: 8),
                  child: text(i, body.copyWith(fontStyle: FontStyle.italic)),
                )
              else if (block.title)
                Padding(
                  padding: const EdgeInsets.only(top: 12, bottom: 10),
                  child: text(i, theme.textTheme.titleLarge!),
                )
              else
                Padding(
                  padding: const EdgeInsets.only(bottom: 16),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (lettered)
                        SizedBox(
                          width: 26,
                          child: Text(block.letter ?? '', style: body.copyWith(fontWeight: FontWeight.w700)),
                        ),
                      Expanded(child: text(i, body)),
                    ],
                  ),
                ),
          ],
        ),
      ),
    );
  }
}

/// A block of the passage with its highlights; a right click on a selection offers Note and
/// Highlight, on a highlight Clear.
class _Marked extends StatelessWidget {
  const _Marked({
    required this.part,
    required this.block,
    required this.text,
    required this.style,
    required this.marks,
    this.onNote,
  });

  final int part, block;
  final String text;
  final TextStyle style;
  final PassageMarks marks;
  final void Function(PassageMark mark)? onNote;

  @override
  Widget build(BuildContext context) {
    final p = ExamStyle.of(context);
    final mine = marks.of(part, block);
    final spans = <TextSpan>[];
    var at = 0;
    for (final m in mine) {
      if (m.start < at || m.end > text.length) continue; // the text changed since (a new import)
      if (m.start > at) spans.add(TextSpan(text: text.substring(at, m.start)));
      spans.add(
        TextSpan(
          text: text.substring(m.start, m.end),
          style: TextStyle(backgroundColor: p.highlight, color: p.highlightText),
        ),
      );
      at = m.end;
    }
    if (at < text.length) spans.add(TextSpan(text: text.substring(at)));
    return SelectableText.rich(
      TextSpan(children: spans),
      style: style,
      contextMenuBuilder: (context, editable) {
        final s = editable.textEditingValue.selection;
        final over = [
          for (final m in mine)
            if (m.start <= s.end && s.start <= m.end) m,
        ];
        void done() => ContextMenuController.removeAny();
        Widget item(IconData icon, String label, VoidCallback onTap) => InkWell(
          onTap: () {
            done();
            onTap();
          },
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(icon, size: 18, color: p.control),
                const SizedBox(width: 6),
                Text(label, style: TextStyle(fontSize: 14, color: p.text)),
              ],
            ),
          ),
        );
        final chosen = s.isValid && !s.isCollapsed;
        final items = [
          if (chosen)
            item(Icons.edit_note, 'Note', () {
              final mark = marks.add(part, block, s.start, s.end, s.textInside(text), note: '');
              onNote?.call(mark);
            }),
          if (chosen)
            item(Icons.border_color, 'Highlight', () => marks.add(part, block, s.start, s.end, s.textInside(text))),
          if (over.isNotEmpty) item(Icons.format_color_reset, 'Clear', () => over.forEach(marks.remove)),
        ];
        if (items.isEmpty) return const SizedBox.shrink();
        final anchor = editable.contextMenuAnchors.primaryAnchor;
        return Stack(
          children: [
            Positioned(
              left: anchor.dx,
              top: anchor.dy,
              child: Material(
                elevation: 3,
                color: p.background,
                shape: RoundedRectangleBorder(
                  side: BorderSide(color: p.border),
                  borderRadius: BorderRadius.circular(3),
                ),
                child: Row(mainAxisSize: MainAxisSize.min, children: items),
              ),
            ),
          ],
        );
      },
    );
  }
}

/// The notes, in a panel at the right: each with the text it is about, and Delete.
class NotesPanel extends StatelessWidget {
  const NotesPanel({super.key, required this.marks, required this.onClose, this.focus, this.width = 300});

  final PassageMarks marks;
  final VoidCallback onClose;
  final PassageMark? focus; // the note just started
  final double? width; // null: as wide as there is room (a narrow screen)

  @override
  Widget build(BuildContext context) {
    final p = ExamStyle.of(context);
    return Container(
      width: width,
      decoration: BoxDecoration(
        color: p.background,
        border: Border(left: BorderSide(color: p.border)),
      ),
      child: ListenableBuilder(
        listenable: marks,
        builder: (context, _) => Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 4, 4),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      'Notes',
                      style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700, color: p.text),
                    ),
                  ),
                  IconButton(
                    tooltip: 'Close',
                    onPressed: onClose,
                    icon: Icon(Icons.close, color: p.text),
                  ),
                ],
              ),
            ),
            Expanded(
              child: marks.notes.isEmpty
                  ? Padding(
                      padding: const EdgeInsets.all(16),
                      child: Text(
                        'No notes yet. Select text in the passage, right-click it and choose Note.',
                        style: TextStyle(fontSize: 14, color: p.muted),
                      ),
                    )
                  : ListView(
                      padding: const EdgeInsets.fromLTRB(12, 4, 12, 80),
                      children: [
                        for (final m in marks.notes)
                          Container(
                            key: ObjectKey(m),
                            margin: const EdgeInsets.only(bottom: 10),
                            padding: const EdgeInsets.all(10),
                            decoration: BoxDecoration(color: p.chosen, borderRadius: BorderRadius.circular(3)),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Part ${m.part}  ${m.text}',
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                  style: TextStyle(fontSize: 14, fontStyle: FontStyle.italic, color: p.text),
                                ),
                                const SizedBox(height: 6),
                                _NoteField(mark: m, marks: marks, focus: identical(m, focus)),
                                Align(
                                  alignment: Alignment.centerRight,
                                  child: TextButton(onPressed: () => marks.remove(m), child: const Text('Delete')),
                                ),
                              ],
                            ),
                          ),
                      ],
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

/// A note's text; a note just started takes the keyboard (the passage had it).
class _NoteField extends StatefulWidget {
  const _NoteField({required this.mark, required this.marks, required this.focus});

  final PassageMark mark;
  final PassageMarks marks;
  final bool focus;

  @override
  State<_NoteField> createState() => _NoteFieldState();
}

class _NoteFieldState extends State<_NoteField> {
  final _node = FocusNode();

  @override
  void initState() {
    super.initState();
    if (widget.focus && (widget.mark.note ?? '').isEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _node.requestFocus();
      });
    }
  }

  @override
  void dispose() {
    _node.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final p = ExamStyle.of(context);
    return TextFormField(
      initialValue: widget.mark.note,
      focusNode: _node,
      minLines: 2,
      maxLines: 6,
      style: TextStyle(fontSize: 14, color: p.text),
      decoration: InputDecoration(
        isDense: true,
        filled: true,
        fillColor: p.background,
        hintText: 'Start typing your note',
        border: const OutlineInputBorder(),
      ),
      onChanged: (v) {
        widget.mark.note = v;
        widget.marks.changed();
      },
    );
  }
}

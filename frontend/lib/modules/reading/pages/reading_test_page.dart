import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:web/web.dart' as web;

import '../../../core/widgets/exam_shell.dart';
import '../api.dart';
import '../widgets/answer_sheet.dart';
import '../widgets/book_pages.dart';
import '../widgets/passage_view.dart';
import '../widgets/question_panel.dart';
import 'reading_session_page.dart';

/// The browser remembers the test in progress, so the Reading page can offer to continue it.
const activeReadingTestKey = 'reading-test';

void rememberReadingTest(String? id) {
  try {
    if (id == null) {
      web.window.localStorage.removeItem(activeReadingTestKey);
    } else {
      web.window.localStorage.setItem(activeReadingTestKey, id);
    }
  } catch (_) {}
}

String? rememberedReadingTest() {
  try {
    return web.window.localStorage.getItem(activeReadingTestKey);
  } catch (_) {
    return null;
  }
}

/// The Reading test, like the computer-delivered one (core/widgets/exam_shell.dart): the passage
/// on the left, its questions on the right with their controls, and a bar of the parts and
/// question numbers at the bottom. Text in the passage can be highlighted and given notes. A
/// test whose text could not be read is shown as its printed pages beside an answer sheet.
///
/// Your answers are saved on the server every few seconds. When the time is up, the server stops
/// accepting them, the controls lock, and the test ends with what was saved.
class ReadingTestPage extends StatefulWidget {
  const ReadingTestPage({super.key, required this.state});

  final ReadingTestState state;

  @override
  State<ReadingTestPage> createState() => _ReadingTestPageState();
}

class _ReadingTestPageState extends State<ReadingTestPage> {
  static const saveEvery = Duration(seconds: 5);

  late final Map<int, String> _values = {
    for (var q = 1; q <= widget.state.questions; q++) q: widget.state.answers['$q'] ?? '',
  };
  late final Map<int, String> _saved = {..._values};
  final Map<int, TextEditingController> _controllers = {};
  final Map<int, GlobalKey> _keys = {};
  late int _secondsLeft = widget.state.secondsLeft;
  late final _deadline = DateTime.now().add(Duration(seconds: widget.state.secondsLeft));
  Timer? _tick, _autosave;
  bool _ending = false;
  bool _showQuestions = false; // on a narrow screen: the questions instead of the passage
  bool _printed = true; // the passage as the book prints it (the text is still rough: an option)
  int _part = 0;
  int? _current; // the question being worked on (framed in blue)
  bool _notesOpen = false;
  PassageMark? _newNote;
  final _contrast = ValueNotifier(ExamContrast.normal);
  final _textSize = ValueNotifier(examTextSizes.keys.first);
  late final _marks = PassageMarks(widget.state.session);
  String? _saveProblem; // the last save failed (the server is unreachable)

  @override
  void initState() {
    super.initState();
    rememberReadingTest(widget.state.session);
    _current = widget.state.content?.parts.first.first;
    // a right click on the passage offers Highlight and Note, not the browser's menu
    if (widget.state.content != null) BrowserContextMenu.disableContextMenu();
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      final left = _deadline.difference(DateTime.now()).inSeconds;
      setState(() => _secondsLeft = left < 0 ? 0 : left);
      if (left <= 0) _end(timeUp: true);
    });
    _autosave = Timer.periodic(saveEvery, (_) => _save());
  }

  @override
  void dispose() {
    _tick?.cancel();
    _autosave?.cancel();
    if (widget.state.content != null) BrowserContextMenu.enableContextMenu();
    _contrast.dispose();
    _textSize.dispose();
    _marks.dispose();
    // Leaving the page (the test goes on): send what was not saved yet.
    if (!_ending && _changed.isNotEmpty) saveReadingAnswers(widget.state.session, _changed).ignore();
    for (final c in _controllers.values) {
      c.dispose();
    }
    super.dispose();
  }

  TextEditingController _controller(int q) => _controllers.putIfAbsent(q, () {
    final c = TextEditingController(text: _values[q]);
    c.addListener(() {
      if (c.text != _values[q]) setState(() => _values[q] = c.text);
    });
    return c;
  });

  void _set(int q, String answer) {
    setState(() => _values[q] = answer);
    final c = _controllers[q];
    if (c != null && c.text != answer) c.text = answer;
  }

  late final _access = AnswerAccess(
    value: (q) => _values[q] ?? '',
    set: _set,
    controller: _controller,
    keyOf: (q) => _keys.putIfAbsent(q, GlobalKey.new),
  );

  /// The answers that changed since the last save.
  Map<String, String> get _changed => {
    for (final e in _values.entries)
      if (e.value != _saved[e.key]) '${e.key}': e.value,
  };

  Map<String, String> get _all => {for (final e in _values.entries) '${e.key}': e.value};

  bool _answered(int q) => (_values[q] ?? '').trim().isNotEmpty;

  int get _answeredCount => _values.keys.where(_answered).length;

  Future<void> _save() async {
    if (_ending) return;
    final changed = _changed;
    if (changed.isEmpty) return;
    try {
      final left = await saveReadingAnswers(widget.state.session, changed);
      if (left == null) {
        _end(timeUp: true);
        return;
      }
      _saved.addAll({for (final e in changed.entries) int.parse(e.key): e.value});
      if (mounted) setState(() => _saveProblem = null);
    } catch (e) {
      if (mounted) setState(() => _saveProblem = 'Not saved: the backend cannot be reached. Keep going; it retries.');
    }
  }

  Future<void> _end({required bool timeUp}) async {
    if (_ending) return;
    setState(() => _ending = true);
    _tick?.cancel();
    _autosave?.cancel();
    try {
      // The last answers go with it; the server keeps what was saved in time if they are late.
      await finishReadingTest(widget.state.session, _all);
      rememberReadingTest(null);
      _marks.forget();
      if (!mounted) return;
      if (timeUp) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Time is up. Your answers were handed in.')));
      }
      await Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (_) => ReadingSessionPage(id: widget.state.session, modeTitle: readingModeTitle),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() => _ending = false);
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('Could not hand in the test ($e). Try again.')));
    }
  }

  Future<void> _finish() async {
    final empty = widget.state.questions - _answeredCount;
    final sure = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Hand in the test?'),
        content: Text(
          [
            if (empty > 0) '$empty question${empty == 1 ? ' has' : 's have'} no answer. A guess costs nothing.',
            'You cannot change your answers afterwards. ${_clockText(_secondsLeft)} is left.',
          ].join('\n\n'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Keep going')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Hand in')),
        ],
      ),
    );
    if (sure == true) _end(timeUp: false);
  }

  /// Makes the question the current one: opens its part and scrolls to it.
  void _goTo(int q) {
    final parts = widget.state.content!.parts;
    final part = parts.indexWhere((p) => p.first <= q && q <= p.last);
    if (part < 0) return;
    setState(() {
      _part = part;
      _current = q;
      _showQuestions = true;
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final target = _keys[q]?.currentContext;
      if (target != null) {
        Scrollable.ensureVisible(target, alignment: 0.2, duration: const Duration(milliseconds: 250));
      }
    });
  }

  void _options() => Navigator.push(
    context,
    MaterialPageRoute(
      fullscreenDialog: true,
      builder: (_) => ExamOptionsPage(contrast: _contrast, textSize: _textSize, onSubmit: _finish),
    ),
  );

  @override
  Widget build(BuildContext context) {
    final state = widget.state;
    return ListenableBuilder(
      listenable: Listenable.merge([_contrast, _textSize]),
      builder: (context, _) {
        final palette = ExamPalette.of(_contrast.value);
        return Theme(
          data: examTheme(palette),
          child: ExamStyle(
            palette: palette,
            child: Scaffold(
              appBar: ExamHeader(
                title: '${readingKinds[state.kind]} Reading',
                secondsLeft: _secondsLeft,
                leading: IconButton(
                  tooltip: 'Leave (the test and its clock go on)',
                  icon: Icon(Icons.arrow_back, color: palette.text),
                  onPressed: () => Navigator.maybePop(context),
                ),
                actions: [
                  IconButton(tooltip: 'Options', icon: const Icon(Icons.menu), onPressed: _options),
                  if (state.content != null)
                    IconButton(
                      tooltip: 'Notes',
                      icon: const Icon(Icons.edit_note),
                      onPressed: () => setState(() => _notesOpen = !_notesOpen),
                    ),
                ],
              ),
              body: Builder(
                builder: (context) =>
                    state.content == null ? _printedTest(context) : _textTest(context, state.content!),
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _textTest(BuildContext context, ReadingContent content) {
    final state = widget.state;
    final part = content.parts[_part];
    final scale = examTextSizes[_textSize.value]!;
    final access = AnswerAccess(
      value: _access.value,
      set: _access.set,
      controller: _access.controller,
      keyOf: _access.keyOf,
      readOnly: _ending,
      current: _current,
      onFocus: (q) {
        if (q != _current) setState(() => _current = q);
      },
    );
    final palette = ExamStyle.of(context);
    final passage = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Align(
          alignment: Alignment.centerRight,
          child: Padding(
            padding: const EdgeInsets.only(right: 12),
            child: TextButton(
              style: TextButton.styleFrom(
                foregroundColor: palette.muted,
                visualDensity: VisualDensity.compact,
                textStyle: const TextStyle(fontSize: 13),
              ),
              onPressed: () => setState(() => _printed = !_printed),
              child: Text(_printed ? 'Show as text' : 'Show the printed page'),
            ),
          ),
        ),
        Expanded(
          child: PassageView(
            key: PageStorageKey('passage-$_part-$_printed'),
            book: state.book,
            part: part,
            printed: _printed,
            textScale: scale,
            marks: _marks,
            onNote: (mark) => setState(() {
              _notesOpen = true;
              _newNote = mark;
            }),
          ),
        ),
      ],
    );
    final questions = MediaQuery(
      data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(scale)),
      child: QuestionPanel(key: PageStorageKey('questions-$_part'), book: state.book, part: part, access: access),
    );
    final first = content.parts.first.first, last = content.parts.last.last;
    final at = _current ?? part.first;
    return LayoutBuilder(
      builder: (context, constraints) {
        final wide = constraints.maxWidth >= 900;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            RubricBox(
              title: 'Part ${part.part}',
              text: 'Read the text and answer questions ${part.first}–${part.last}.',
            ),
            if (!wide)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 4),
                child: SegmentedButton<bool>(
                  showSelectedIcon: false,
                  segments: [
                    const ButtonSegment(value: false, label: Text('Text'), icon: Icon(Icons.article_outlined)),
                    ButtonSegment(
                      value: true,
                      label: Text('Questions ${part.first}–${part.last}'),
                      icon: const Icon(Icons.edit_outlined),
                    ),
                  ],
                  selected: {_showQuestions},
                  onSelectionChanged: (s) => setState(() => _showQuestions = s.first),
                ),
              ),
            Expanded(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Expanded(
                    child: Stack(
                      children: [
                        Positioned.fill(
                          child: wide
                              ? SplitPane(left: passage, right: questions)
                              // both stay built, so each keeps its place; the notes cover them
                              : IndexedStack(
                                  index: _notesOpen ? 2 : (_showQuestions ? 1 : 0),
                                  children: [
                                    passage,
                                    questions,
                                    NotesPanel(
                                      marks: _marks,
                                      focus: _newNote,
                                      width: null,
                                      onClose: () => setState(() => _notesOpen = false),
                                    ),
                                  ],
                                ),
                        ),
                        Positioned(
                          right: 26,
                          bottom: 14,
                          child: ExamArrows(
                            onPrevious: at > first ? () => _goTo(at - 1) : null,
                            onNext: at < last ? () => _goTo(at + 1) : null,
                          ),
                        ),
                      ],
                    ),
                  ),
                  if (_notesOpen && wide)
                    NotesPanel(marks: _marks, focus: _newNote, onClose: () => setState(() => _notesOpen = false)),
                ],
              ),
            ),
            Divider(height: 1, color: palette.border),
            ExamFooter(
              parts: [for (final p in content.parts) (label: 'Part ${p.part}', first: p.first, last: p.last)],
              currentPart: _part,
              currentQuestion: _current,
              answered: _answered,
              onQuestion: _goTo,
              onHandIn: _ending ? null : _finish,
              status: _saveProblem,
            ),
          ],
        );
      },
    );
  }

  /// A test whose text could not be read: its pages beside an answer sheet.
  Widget _printedTest(BuildContext context) {
    final theme = Theme.of(context);
    final state = widget.state;
    final controllers = {for (var q = 1; q <= state.questions; q++) q: _controller(q)};
    final pages = BookPages(book: state.book, pages: state.pages, parts: state.parts, partName: state.partName);
    final sheet = AnswerSheet(
      controllers: controllers,
      groups: state.sections,
      partName: state.partName,
      readOnly: _ending,
    );
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final wide = constraints.maxWidth >= 900;
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (!wide) ...[
                SegmentedButton<bool>(
                  showSelectedIcon: false,
                  segments: [
                    const ButtonSegment(value: false, label: Text('The test'), icon: Icon(Icons.menu_book_outlined)),
                    ButtonSegment(
                      value: true,
                      label: Text('Answers $_answeredCount/${state.questions}'),
                      icon: const Icon(Icons.edit_outlined),
                    ),
                  ],
                  selected: {_showQuestions},
                  onSelectionChanged: (s) => setState(() => _showQuestions = s.first),
                ),
                const SizedBox(height: 8),
              ],
              Expanded(
                child: wide
                    ? Row(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Expanded(child: pages),
                          const SizedBox(width: 16),
                          SizedBox(
                            width: 320,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: [
                                Text(
                                  'Answer sheet · $_answeredCount/${state.questions}',
                                  style: theme.textTheme.titleMedium,
                                ),
                                const SizedBox(height: 4),
                                Expanded(child: sheet),
                              ],
                            ),
                          ),
                        ],
                      )
                    // both stay built, so the pages keep their place
                    : IndexedStack(index: _showQuestions ? 1 : 0, children: [pages, sheet]),
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      _saveProblem ?? 'Saved every few seconds. About 20 minutes per ${state.partName.toLowerCase()}.',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: _saveProblem == null ? theme.colorScheme.onSurfaceVariant : theme.colorScheme.error,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  _HandIn(ending: _ending, onPressed: _finish),
                ],
              ),
            ],
          );
        },
      ),
    );
  }
}

class _HandIn extends StatelessWidget {
  const _HandIn({required this.ending, required this.onPressed});

  final bool ending;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) => FilledButton.icon(
    onPressed: ending ? null : onPressed,
    icon: ending
        ? const SizedBox.square(dimension: 18, child: CircularProgressIndicator(strokeWidth: 2))
        : const Icon(Icons.assignment_turned_in_outlined),
    label: const Text('Hand in'),
  );
}

/// 3540 → "59:00".
String _clockText(int seconds) => '${seconds ~/ 60}:${(seconds % 60).toString().padLeft(2, '0')}';

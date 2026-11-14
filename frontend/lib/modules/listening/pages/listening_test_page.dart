import 'dart:async';
import 'dart:js_interop';

import 'package:flutter/material.dart';
import 'package:web/web.dart' as web;

import '../../../core/widgets/exam_shell.dart';
import '../../reading/api.dart' show ReadingContent;
import '../../reading/widgets/question_panel.dart';
import '../api.dart';
import 'listening_session_page.dart';

/// The browser remembers the test in progress, so the Listening page can offer to continue it.
const activeListeningTestKey = 'listening-test';

void rememberListeningTest(String? id) {
  try {
    if (id == null) {
      web.window.localStorage.removeItem(activeListeningTestKey);
    } else {
      web.window.localStorage.setItem(activeListeningTestKey, id);
    }
  } catch (_) {}
}

String? rememberedListeningTest() {
  try {
    return web.window.localStorage.getItem(activeListeningTestKey);
  } catch (_) {
    return null;
  }
}

/// The recordings of a test played one after the other from a place in time: there is no
/// pause and no going back. [at] seconds from the start of the first recording is where it
/// plays; past the end of the last one (or [stopAt]) it is silent.
class RecordingPlayer {
  RecordingPlayer({required this.book, required this.audio, required this.stopAt, this.onPart});

  final String book;
  final List<Recording> audio;
  final double stopAt;
  final void Function(int index)? onPart; // a recording started
  final web.HTMLAudioElement _element = web.HTMLAudioElement();
  int _index = -1;
  double _volume = 1;
  bool _stopped = false;

  /// Plays from [at] seconds. Must be called from a click, or the browser refuses to play;
  /// returns false when it refused.
  Future<bool> play(double at) async {
    var start = 0.0;
    for (final (i, a) in audio.indexed) {
      if (at < start + a.seconds) return _playTrack(i, at - start);
      start += a.seconds;
    }
    return true; // the recordings are over
  }

  Future<bool> _playTrack(int index, double offset) async {
    if (_stopped || index >= audio.length) return true;
    _index = index;
    onPart?.call(index);
    _element
      ..src = recordingUrl(book, audio[index].file)
      ..volume = _volume
      ..currentTime = offset
      ..onended = ((web.Event _) {
        _playTrack(index + 1, 0);
      }).toJS;
    try {
      await _element.play().toDart;
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Called every second with the time since the start: stops at [stopAt].
  void check(double at) {
    if (at >= stopAt) stop();
  }

  int get index => _index;

  set volume(double v) {
    _volume = v;
    _element.volume = v;
  }

  void stop() {
    _stopped = true;
    _element.pause();
    _element.removeAttribute('src');
    _element.load();
  }
}

/// The Listening test, like the computer-delivered one (core/widgets/exam_shell.dart): "Play"
/// first, then the recordings play once, without pause, while the questions of each part are
/// answered across the full width; a bar of the four parts and their question numbers at the
/// bottom. When the recordings end there are two minutes to check the answers.
///
/// The clock is the recording's and runs on the server: leaving the page or reloading it does
/// not stop it, and what played meanwhile is not played again.
class ListeningTestPage extends StatefulWidget {
  const ListeningTestPage({super.key, required this.state});

  final ListeningTestState state;

  @override
  State<ListeningTestPage> createState() => _ListeningTestPageState();
}

class _ListeningTestPageState extends State<ListeningTestPage> {
  static const saveEvery = Duration(seconds: 5);

  late final Map<int, String> _values = {
    for (var q = 1; q <= widget.state.questions; q++) q: widget.state.answers['$q'] ?? '',
  };
  late final Map<int, String> _saved = {..._values};
  final Map<int, TextEditingController> _controllers = {};
  final Map<int, GlobalKey> _keys = {};
  late final double _total = widget.state.recordingSeconds + widget.state.checkSeconds;
  late int _secondsLeft = widget.state.secondsLeft;
  DateTime? _startedAt; // when the recording's clock started, on this computer's clock
  Timer? _tick, _autosave;
  bool _playing = false; // the Play overlay is gone
  bool _starting = false;
  bool _ending = false;
  int _part = 0;
  int? _current;
  double _volume = 1;
  final _contrast = ValueNotifier(ExamContrast.normal);
  final _textSize = ValueNotifier(examTextSizes.keys.first);
  String? _saveProblem;
  late final _player = RecordingPlayer(
    book: widget.state.book,
    audio: widget.state.audio,
    stopAt: widget.state.recordingSeconds,
    onPart: _recordingStarted,
  );

  ReadingContent get _content => widget.state.content!;

  double get _elapsed => _startedAt == null ? 0 : DateTime.now().difference(_startedAt!).inMilliseconds / 1000;

  bool get _checking => _startedAt != null && _elapsed >= widget.state.recordingSeconds;

  @override
  void initState() {
    super.initState();
    rememberListeningTest(widget.state.session);
    _current = _content.parts.first.first;
    _autosave = Timer.periodic(saveEvery, (_) => _save());
  }

  @override
  void dispose() {
    _tick?.cancel();
    _autosave?.cancel();
    _player.stop();
    _contrast.dispose();
    _textSize.dispose();
    // Leaving the page (the test goes on): send what was not saved yet.
    if (!_ending && _changed.isNotEmpty) saveListeningAnswers(widget.state.session, _changed).ignore();
    for (final c in _controllers.values) {
      c.dispose();
    }
    super.dispose();
  }

  /// "Play": starts the clock on the server (the first time) and the recording where it is now.
  Future<void> _play() async {
    setState(() => _starting = true);
    try {
      final state = await playListeningTest(widget.state.session);
      if (!mounted) return;
      if (state.finished) {
        _end(timeUp: true);
        return;
      }
      _startedAt = DateTime.now().subtract(Duration(milliseconds: (state.elapsed * 1000).round()));
      final allowed = await _player.play(state.elapsed);
      if (!mounted) return;
      if (!allowed) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('The browser did not let the recording play. Press Play again.')));
        setState(() => _starting = false);
        return;
      }
      setState(() {
        _playing = true;
        _starting = false;
        _secondsLeft = state.secondsLeft;
      });
      _tick = Timer.periodic(const Duration(seconds: 1), (_) {
        final left = (_total - _elapsed).ceil();
        _player.check(_elapsed);
        setState(() => _secondsLeft = left < 0 ? 0 : left);
        if (left <= 0) _end(timeUp: true);
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _starting = false);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not start the recording ($e).')));
    }
  }

  /// A part's recording started: show its questions (a test in one recording has no such sign).
  void _recordingStarted(int index) {
    final part = widget.state.audio[index].part;
    if (part < 1 || part > _content.parts.length || !mounted) return;
    final shown = _content.parts[part - 1];
    setState(() {
      _part = part - 1;
      if (_current == null || _current! < shown.first || _current! > shown.last) _current = shown.first;
    });
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
      final left = await saveListeningAnswers(widget.state.session, changed);
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
    _player.stop();
    try {
      await finishListeningTest(widget.state.session, _all);
      rememberListeningTest(null);
      if (!mounted) return;
      if (timeUp) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Time is up. Your answers were handed in.')));
      }
      await Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (_) => ListeningSessionPage(id: widget.state.session, modeTitle: listeningModeTitle),
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
            if (_playing && !_checking) 'The recording is still playing: handing in now ends it.',
            if (empty > 0) '$empty question${empty == 1 ? ' has' : 's have'} no answer. A guess costs nothing.',
            'You cannot change your answers afterwards.',
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
    final part = _content.parts.indexWhere((p) => p.first <= q && q <= p.last);
    if (part < 0) return;
    setState(() {
      _part = part;
      _current = q;
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
                title: 'Listening',
                status: !_playing
                    ? null
                    : Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(_checking ? Icons.checklist : Icons.volume_up, size: 15, color: palette.muted),
                          const SizedBox(width: 4),
                          Text(
                            _checking ? 'Check your answers' : 'Audio is playing',
                            style: TextStyle(fontSize: 13, color: palette.muted),
                          ),
                        ],
                      ),
                secondsLeft: _secondsLeft,
                leading: IconButton(
                  tooltip: 'Leave (the recording and its clock go on)',
                  icon: Icon(Icons.arrow_back, color: palette.text),
                  onPressed: () => Navigator.maybePop(context),
                ),
                actions: [
                  if (_playing && !_checking && MediaQuery.sizeOf(context).width >= 600)
                    SizedBox(
                      width: 130,
                      child: Slider(
                        value: _volume,
                        onChanged: (v) => setState(() {
                          _volume = v;
                          _player.volume = v;
                        }),
                      ),
                    ),
                  IconButton(tooltip: 'Options', icon: const Icon(Icons.menu), onPressed: _options),
                ],
              ),
              body: Builder(builder: (context) => _playing ? _test(context) : _playFirst(context)),
            ),
          ),
        );
      },
    );
  }

  /// Before the recording: what will happen, and "Play".
  Widget _playFirst(BuildContext context) {
    final p = ExamStyle.of(context);
    final resumed = widget.state.started;
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 520),
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.headphones, size: 72, color: p.text),
              const SizedBox(height: 16),
              Text(
                resumed
                    ? 'The recording kept running while you were away. Press Play to listen from where it is '
                          'now; what has played is not played again.'
                    : 'You will be listening to an audio clip during this test. You will not be permitted to '
                          'pause or rewind the audio while answering the questions.',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 16, height: 1.5, color: p.text),
              ),
              const SizedBox(height: 8),
              Text(
                'To continue, click Play.',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 16, color: p.text),
              ),
              const SizedBox(height: 20),
              FilledButton.icon(
                style: FilledButton.styleFrom(
                  backgroundColor: p.arrow,
                  foregroundColor: p.background,
                  padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 16),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
                ),
                onPressed: _starting ? null : _play,
                icon: _starting
                    ? const SizedBox.square(dimension: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.play_arrow),
                label: const Text('Play', style: TextStyle(fontSize: 16)),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _test(BuildContext context) {
    final part = _content.parts[_part];
    final scale = examTextSizes[_textSize.value]!;
    final palette = ExamStyle.of(context);
    final access = AnswerAccess(
      value: (q) => _values[q] ?? '',
      set: _set,
      controller: _controller,
      keyOf: (q) => _keys.putIfAbsent(q, GlobalKey.new),
      readOnly: _ending,
      current: _current,
      onFocus: (q) {
        if (q != _current) setState(() => _current = q);
      },
    );
    final first = _content.parts.first.first, last = _content.parts.last.last;
    final at = _current ?? part.first;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        RubricBox(title: 'Part ${part.part}', text: 'Listen and answer questions ${part.first}–${part.last}.'),
        Expanded(
          child: Stack(
            children: [
              Positioned.fill(
                child: MediaQuery(
                  data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(scale)),
                  // the questions across the full width, as in the test (a readable line's width)
                  child: Align(
                    alignment: Alignment.topLeft,
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 1000),
                      child: QuestionPanel(
                        key: PageStorageKey('listening-questions-$_part'),
                        book: widget.state.book,
                        part: part,
                        access: access,
                      ),
                    ),
                  ),
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
        Divider(height: 1, color: palette.border),
        ExamFooter(
          parts: [for (final p in _content.parts) (label: 'Part ${p.part}', first: p.first, last: p.last)],
          currentPart: _part,
          currentQuestion: _current,
          answered: _answered,
          onQuestion: _goTo,
          onHandIn: _ending ? null : _finish,
          status: _saveProblem,
        ),
      ],
    );
  }
}

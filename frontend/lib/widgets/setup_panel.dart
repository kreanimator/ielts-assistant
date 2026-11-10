import 'dart:math';

import 'package:flutter/material.dart';

import '../api.dart';

/// Choose the training mode, topic and examiner voice before a session.
class SetupPanel extends StatelessWidget {
  const SetupPanel({
    super.key,
    required this.options,
    required this.mode,
    required this.voice,
    required this.topic,
    required this.tests,
    required this.topics,
    required this.test,
    required this.onTest,
    required this.enabled,
    required this.onMode,
    required this.onVoice,
    required this.liveCorrections,
    required this.onLiveCorrections,
    required this.onHistory,
  });

  final Options options;
  final String mode, voice;
  final TextEditingController topic;
  final List<BookTest> tests; // imported from your books
  final List<Topic> topics; // suggestions for the topic field
  final BookTest? test; // the chosen one, if any
  final ValueChanged<String?> onTest;
  final bool enabled;
  final ValueChanged<String> onMode, onVoice;
  final bool liveCorrections; // can be changed during a session too
  final ValueChanged<bool> onLiveCorrections;
  final VoidCallback onHistory;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('IELTS Speaking', style: text.titleLarge),
        Text('Practice session', style: text.bodyMedium),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: enabled ? onHistory : null,
          icon: const Icon(Icons.history),
          label: const Text('History and progress'),
        ),
        const SizedBox(height: 24),
        Text('Training', style: text.titleSmall),
        const SizedBox(height: 8),
        for (final m in options.modes)
          Card(
            margin: const EdgeInsets.only(bottom: 8),
            child: ListTile(
              enabled: enabled,
              selected: m.id == mode,
              leading: Icon(m.id == mode ? Icons.radio_button_checked : Icons.radio_button_unchecked),
              title: Text(m.title),
              subtitle: Text(m.description),
              onTap: () => onMode(m.id),
            ),
          ),
        if (mode != 'free') ...[
          const SizedBox(height: 16),
          _QuestionsPicker(tests: tests, test: test, mode: mode, enabled: enabled, onTest: onTest),
        ],
        const SizedBox(height: 16),
        _TopicField(
          controller: topic,
          topics: topics,
          enabled: enabled && test == null,
          label: mode == 'part2' || mode == 'exam' ? 'Cue card topic (optional)' : 'Topic (optional)',
        ),
        const SizedBox(height: 16),
        DropdownMenu<String>(
          key: ValueKey(voice),
          enabled: enabled,
          expandedInsets: EdgeInsets.zero,
          label: const Text('Examiner voice'),
          initialSelection: voice,
          dropdownMenuEntries: [for (final v in options.voices) DropdownMenuEntry(value: v.id, label: v.label)],
          onSelected: (id) => id == null ? null : onVoice(id),
        ),
        const SizedBox(height: 8),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Live corrections'),
          subtitle: Text(
            mode == 'exam'
                ? 'Always off in the full exam: you see them when it ends.'
                : 'Off: see them only when the session ends, like in the real test.',
          ),
          value: liveCorrections && mode != 'exam',
          onChanged: mode == 'exam' ? null : onLiveCorrections,
        ),
        ListTile(
          contentPadding: EdgeInsets.zero,
          leading: const Icon(Icons.memory),
          title: const Text('Language model'),
          subtitle: Text(options.model),
        ),
      ],
    );
  }
}

/// Where the questions come from: the examiner, or a real test from your books.
class _QuestionsPicker extends StatelessWidget {
  const _QuestionsPicker({
    required this.tests,
    required this.test,
    required this.mode,
    required this.enabled,
    required this.onTest,
  });

  final List<BookTest> tests;
  final BookTest? test;
  final String mode;
  final bool enabled;
  final ValueChanged<String?> onTest;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    if (tests.isEmpty) {
      return Text(
        'To practise with real test questions, import your IELTS books: make books BOOKS=\'path/*.pdf\'',
        style: text.bodySmall,
      );
    }
    final chosen = test;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        DropdownMenu<String>(
          key: ValueKey(chosen?.key),
          enabled: enabled,
          expandedInsets: EdgeInsets.zero,
          menuHeight: 400,
          requestFocusOnTap: false, // a list to pick from, not a text field
          label: const Text('Questions'),
          initialSelection: chosen?.key ?? '',
          dropdownMenuEntries: [
            const DropdownMenuEntry(value: '', label: 'Made up by the examiner'),
            for (final t in tests) DropdownMenuEntry(value: t.key, label: t.label),
          ],
          onSelected: (key) => onTest(key == null || key.isEmpty ? null : key),
        ),
        if (chosen != null)
          Padding(
            padding: const EdgeInsets.only(top: 6, left: 4),
            child: Text(chosen.outline(mode), style: text.bodySmall),
          ),
      ],
    );
  }
}

/// The topic: typed, picked from the suggestions, or rolled by letter.
class _TopicField extends StatefulWidget {
  const _TopicField({required this.controller, required this.topics, required this.enabled, required this.label});

  final TextEditingController controller;
  final List<Topic> topics;
  final bool enabled;
  final String label;

  @override
  State<_TopicField> createState() => _TopicFieldState();
}

class _TopicFieldState extends State<_TopicField> {
  final _focus = FocusNode();

  @override
  void dispose() {
    _focus.dispose();
    super.dispose();
  }

  Future<void> _pickByLetter() async {
    final name = await showDialog<String>(
      context: context,
      builder: (_) => _LetterDialog(topics: widget.topics),
    );
    if (name != null) widget.controller.text = name;
  }

  @override
  Widget build(BuildContext context) => RawAutocomplete<String>(
    textEditingController: widget.controller,
    focusNode: _focus,
    optionsBuilder: (value) {
      final typed = value.text.trim().toLowerCase();
      if (typed.isEmpty) return const [];
      return widget.topics.map((t) => t.name).where((n) => n.toLowerCase().contains(typed)).take(30);
    },
    fieldViewBuilder: (context, controller, focus, onSubmitted) => TextField(
      controller: controller,
      focusNode: focus,
      enabled: widget.enabled,
      onSubmitted: (_) => onSubmitted(),
      decoration: InputDecoration(
        labelText: widget.label,
        hintText: 'Type, or pick by letter',
        border: const OutlineInputBorder(),
        suffixIcon: IconButton(
          tooltip: 'Pick a topic by letter',
          onPressed: widget.enabled && widget.topics.isNotEmpty ? _pickByLetter : null,
          icon: const Icon(Icons.sort_by_alpha),
        ),
      ),
    ),
    optionsViewBuilder: (context, onSelected, options) => Align(
      alignment: Alignment.topLeft,
      child: Material(
        elevation: 4,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxHeight: 260, maxWidth: 288),
          child: ListView(
            padding: EdgeInsets.zero,
            shrinkWrap: true,
            children: [
              for (final o in options) ListTile(dense: true, title: Text(o), onTap: () => onSelected(o)),
            ],
          ),
        ),
      ),
    ),
  );
}

/// A-Z: choose a letter, or roll one, and get a random topic starting with it.
class _LetterDialog extends StatefulWidget {
  const _LetterDialog({required this.topics});

  final List<Topic> topics;

  @override
  State<_LetterDialog> createState() => _LetterDialogState();
}

class _LetterDialogState extends State<_LetterDialog> {
  final _random = Random();
  String? _letter;
  Topic? _topic;

  Map<String, List<Topic>> get _byLetter {
    final map = <String, List<Topic>>{};
    for (final t in widget.topics) {
      map.putIfAbsent(t.letter, () => []).add(t);
    }
    return map;
  }

  void _choose(String letter) {
    final options = _byLetter[letter]!;
    setState(() {
      _letter = letter;
      _topic = options[_random.nextInt(options.length)];
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final byLetter = _byLetter;
    final letters = byLetter.keys.toList();
    return AlertDialog(
      title: const Text('Pick a topic by letter'),
      content: SizedBox(
        width: 360,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: 4,
              runSpacing: 4,
              children: [
                for (final code in List.generate(26, (i) => String.fromCharCode(65 + i)))
                  ChoiceChip(
                    label: Text(code),
                    selected: code == _letter,
                    onSelected: byLetter.containsKey(code) ? (_) => _choose(code) : null,
                  ),
              ],
            ),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: () => _choose(letters[_random.nextInt(letters.length)]),
              icon: const Icon(Icons.casino_outlined),
              label: const Text('Random letter'),
            ),
            const SizedBox(height: 16),
            if (_topic != null) ...[
              Text('$_letter: ${_topic!.name}', style: theme.textTheme.titleLarge),
              Text(
                '${byLetter[_letter]!.length} topics start with $_letter${_topic!.fromBooks ? ' · from your books' : ''}',
                style: theme.textTheme.bodySmall,
              ),
            ] else
              Text('Choose a letter, or roll one.', style: theme.textTheme.bodyMedium),
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        if (_topic != null) ...[
          TextButton(onPressed: () => _choose(_letter!), child: const Text('Another')),
          FilledButton(onPressed: () => Navigator.pop(context, _topic!.name), child: const Text('Use this topic')),
        ],
      ],
    );
  }
}

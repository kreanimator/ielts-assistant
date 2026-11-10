import 'dart:math';

import 'package:flutter/material.dart';
import 'package:web/web.dart' as web;

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
    required this.drills,
    required this.drill,
    required this.onDrill,
    required this.cards,
    required this.card,
    required this.onCard,
    required this.level,
    required this.onLevel,
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
  final List<Drill> drills;
  final Drill? drill; // the chosen drill, in drill mode
  final ValueChanged<String> onDrill;
  final List<EslTopic> cards; // the "By letter" topic cards
  final EslTopic? card; // the one dealt for the chosen letter
  final ValueChanged<String> onCard;
  final String level; // mixed, or one of the site's levels
  final ValueChanged<String> onLevel;
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
        if (mode == 'drill' && drills.isNotEmpty) ...[
          const SizedBox(height: 16),
          _DrillPicker(drills: drills, drill: drill, enabled: enabled, onDrill: onDrill),
        ],
        if (mode == 'letter') ...[
          const SizedBox(height: 16),
          _CardPicker(cards: cards, card: card, onCard: onCard, level: level, onLevel: onLevel, enabled: enabled),
        ],
        if (mode != 'free' && mode != 'drill' && mode != 'letter') ...[
          const SizedBox(height: 16),
          _QuestionsPicker(tests: tests, test: test, mode: mode, enabled: enabled, onTest: onTest),
        ],
        if (mode != 'letter' && !(mode == 'drill' && (drill?.isSound ?? false))) const SizedBox(height: 16),
        if (mode != 'letter' && !(mode == 'drill' && (drill?.isSound ?? false)))
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

/// The topic: typed, or picked from the suggestions.
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
        hintText: 'Type a topic, or leave it to the examiner',
        border: const OutlineInputBorder(),
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

/// By letter: choose a letter, or roll one, and get a random topic card that starts with it.
class _CardPicker extends StatelessWidget {
  const _CardPicker({
    required this.cards,
    required this.card,
    required this.onCard,
    required this.level,
    required this.onLevel,
    required this.enabled,
  });

  static final _random = Random();
  static const _levels = {
    'mixed': 'Mixed, easy to hard',
    'A2': 'Elementary (A2)',
    'B1': 'Intermediate (B1)',
    'B2': 'Upper-intermediate (B2)',
    'C1': 'Advanced (C1)',
  };

  final List<EslTopic> cards;
  final EslTopic? card;
  final ValueChanged<String> onCard;
  final String level;
  final ValueChanged<String> onLevel;
  final bool enabled;

  void _deal(String letter) {
    final options = cards.where((c) => c.letter == letter && c.slug != card?.slug).toList();
    if (options.isEmpty) options.addAll(cards.where((c) => c.letter == letter));
    onCard(options[_random.nextInt(options.length)].slug);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (cards.isEmpty) {
      return Text(
        'Download the topic cards once (about 2.5 minutes): make esl-topics',
        style: theme.textTheme.bodySmall,
      );
    }
    final letters = {for (final c in cards) c.letter};
    final chosen = card;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 4,
          runSpacing: 4,
          children: [
            for (final code in List.generate(26, (i) => String.fromCharCode(65 + i)))
              ChoiceChip(
                label: Text(code),
                selected: code == chosen?.letter,
                onSelected: enabled && letters.contains(code) ? (_) => _deal(code) : null,
              ),
          ],
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            OutlinedButton.icon(
              onPressed: enabled ? () => _deal(letters.elementAt(_random.nextInt(letters.length))) : null,
              icon: const Icon(Icons.casino_outlined),
              label: const Text('Random letter'),
            ),
            const SizedBox(width: 8),
            if (chosen != null)
              TextButton(onPressed: enabled ? () => _deal(chosen.letter) : null, child: const Text('Another card')),
          ],
        ),
        const SizedBox(height: 8),
        Card(
          margin: EdgeInsets.zero,
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: chosen == null
                ? Text('Choose a letter, or roll one. Without a card, Start deals a random one.',
                    style: theme.textTheme.bodyMedium)
                : Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(chosen.name, style: theme.textTheme.titleLarge),
                      Text('8 of its ${chosen.questions} questions, asked by the examiner',
                          style: theme.textTheme.bodySmall),
                      TextButton.icon(
                        style: TextButton.styleFrom(padding: EdgeInsets.zero),
                        onPressed: () => web.window.open(chosen.url, '_blank'),
                        icon: const Icon(Icons.open_in_new, size: 16),
                        label: const Text('Source: eslconversationquestions.com'),
                      ),
                    ],
                  ),
          ),
        ),
        const SizedBox(height: 12),
        DropdownMenu<String>(
          key: ValueKey(level),
          enabled: enabled,
          expandedInsets: EdgeInsets.zero,
          requestFocusOnTap: false,
          label: const Text('Question level'),
          initialSelection: level,
          dropdownMenuEntries: [for (final e in _levels.entries) DropdownMenuEntry(value: e.key, label: e.value)],
          onSelected: (value) => value == null ? null : onLevel(value),
        ),
      ],
    );
  }
}

/// Which drill: the sounds your past sessions suggest come first.
class _DrillPicker extends StatelessWidget {
  const _DrillPicker({required this.drills, required this.drill, required this.enabled, required this.onDrill});

  final List<Drill> drills;
  final Drill? drill;
  final bool enabled;
  final ValueChanged<String> onDrill;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final chosen = drill;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        DropdownMenu<String>(
          key: ValueKey(chosen?.id),
          enabled: enabled,
          expandedInsets: EdgeInsets.zero,
          menuHeight: 400,
          requestFocusOnTap: false,
          label: const Text('Practise'),
          initialSelection: chosen?.id,
          dropdownMenuEntries: [
            for (final d in drills)
              DropdownMenuEntry(
                value: d.id,
                label: d.title,
                trailingIcon: d.reason == null ? null : const Icon(Icons.star_outline, size: 18),
              ),
          ],
          onSelected: (id) => id == null ? null : onDrill(id),
        ),
        if (chosen != null)
          Padding(
            padding: const EdgeInsets.only(top: 6, left: 4),
            child: Text(
              chosen.reason == null ? chosen.description : '${chosen.description} Suggested: ${chosen.reason}.',
              style: text.bodySmall,
            ),
          ),
      ],
    );
  }
}

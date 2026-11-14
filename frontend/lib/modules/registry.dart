import 'package:flutter/material.dart';

import 'listening/listening.dart';
import 'listening/listening_page.dart';
import 'reading/reading.dart';
import 'reading/reading_page.dart';
import 'speaking/speaking.dart';
import 'speaking/speaking_page.dart';
import 'writing/writing.dart';
import 'writing/writing_page.dart';

/// What the dashboard needs from each module. A skill without [page] is "coming soon".
class SkillModule {
  const SkillModule({
    required this.id,
    required this.icon,
    required this.blurb,
    this.page,
    this.openSession,
    this.openHistory,
  });

  final String id;
  final IconData icon;
  final String blurb; // one line on the skill's card
  final WidgetBuilder? page;
  final Future<void> Function(BuildContext context, String id, String Function(String mode) modeTitle)? openSession;
  final Future<void> Function(BuildContext context, String Function(String mode) modeTitle)? openHistory;
}

const skillModules = {
  'listening': SkillModule(
    id: 'listening',
    icon: Icons.headphones_outlined,
    blurb: 'Four recordings played once, 40 questions, marked with the key',
    page: _listeningPage,
    openSession: openListeningSession,
    openHistory: openListeningHistory,
  ),
  'reading': SkillModule(
    id: 'reading',
    icon: Icons.menu_book_outlined,
    blurb: 'Three passages, 40 questions, marked with the key',
    page: _readingPage,
    openSession: openReadingSession,
    openHistory: openReadingHistory,
  ),
  'writing': SkillModule(
    id: 'writing',
    icon: Icons.edit_note,
    blurb: 'Task 1 letter and Task 2 essay, with corrections',
    page: _writingPage,
    openSession: openWritingSession,
    openHistory: openWritingHistory,
  ),
  'speaking': SkillModule(
    id: 'speaking',
    icon: Icons.record_voice_over_outlined,
    blurb: 'Talk with an AI examiner',
    page: _speakingPage,
    openSession: openSpeakingSession,
    openHistory: openSpeakingHistory,
  ),
};

Widget _speakingPage(BuildContext context) => const SpeakingPage();

Widget _writingPage(BuildContext context) => const WritingPage();

Widget _readingPage(BuildContext context) => const ReadingPage();

Widget _listeningPage(BuildContext context) => const ListeningPage();

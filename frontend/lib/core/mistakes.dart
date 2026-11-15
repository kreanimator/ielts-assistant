import 'package:http/http.dart' as http;

import 'api.dart';

/// Your mistakes from every session, by type (backend/app/core/mistakes.py).

/// One of your mistakes, with the session it is from.
class MistakeExample {
  MistakeExample.fromJson(Map<String, dynamic> json)
    : session = json['session'],
      module = json['module'],
      mode = json['mode'],
      topic = json['topic'],
      date = DateTime.parse(json['date']).toLocal(),
      original = json['original'],
      better = json['better'],
      why = json['why'];

  final String session, module, mode, original, better, why;
  final String? topic;
  final DateTime date;
}

/// A type of mistake ("Articles") and how often you make it.
class MistakeType {
  MistakeType.fromJson(Map<String, dynamic> json)
    : id = json['id'],
      title = json['title'],
      covers = json['covers'],
      count = json['count'],
      sessions = json['sessions'],
      lastSeen = DateTime.parse(json['last_seen']).toLocal(),
      byModule = Map<String, int>.from(json['by_module']),
      improving = json['improving'],
      examples = [for (final e in json['examples']) MistakeExample.fromJson(e)];

  final String id, title, covers;
  final int count, sessions;
  final DateTime lastSeen;
  final Map<String, int> byModule; // module id → mistakes
  final bool improving; // not seen in your latest sessions
  final List<MistakeExample> examples; // newest first
}

/// A word you misspelled.
class Misspelling {
  Misspelling.fromJson(Map<String, dynamic> json)
    : right = json['right'],
      wrong = List<String>.from(json['wrong']),
      count = json['count'];

  final String right;
  final List<String> wrong; // how you wrote it
  final int count;
}

/// A sound the pronunciation check heard as another sound.
class MissedSound {
  MissedSound.fromJson(Map<String, dynamic> json)
    : sound = json['sound'],
      count = json['count'],
      heard = [for (final h in json['heard']) (sound: h['sound'] as String, count: h['count'] as int)];

  final String sound;
  final int count;
  final List<({String sound, int count})> heard; // what was heard instead, '' = left out
}

class Mistakes {
  Mistakes.fromJson(Map<String, dynamic> json)
    : pending = json['pending'],
      total = json['total'],
      sessions = json['sessions'],
      types = [for (final t in json['types']) MistakeType.fromJson(t)],
      spelling = [for (final w in json['spelling']) Misspelling.fromJson(w)],
      sounds = [for (final s in json['sounds']) MissedSound.fromJson(s)];

  final int pending; // mistakes whose type is still being worked out
  final int total, sessions;
  final List<MistakeType> types; // the most frequent first
  final List<Misspelling> spelling;
  final List<MissedSound> sounds;

  bool get isEmpty => total == 0 && sounds.isEmpty;
}

Future<Mistakes> fetchMistakes() async => Mistakes.fromJson(await getJson(http.get(apiUri('/api/mistakes'))));

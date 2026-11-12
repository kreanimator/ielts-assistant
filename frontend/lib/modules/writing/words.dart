/// A word as IELTS counts it: anything between spaces that has a letter or a digit. The same
/// count as the backend's (backend/app/core/text.py), so the counter matches the report.
final _word = RegExp(r'\S*[A-Za-z0-9]\S*');

int wordCount(String text) => _word.allMatches(text).length;

import 'package:flutter/material.dart';

import '../history.dart';

/// "Discard the test" for a test in progress: asks first, then deletes the test with what was
/// answered so far (nothing is marked and nothing goes to the history). True when it was
/// deleted; the page then forgets the test, and another can be opened.
Future<bool> discardTest(BuildContext context, String session) async {
  final sure = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      title: const Text('Discard this test?'),
      content: const SizedBox(
        width: 420,
        child: Text(
          'The test is closed without a result: what you answered so far is deleted, and it does not '
          'appear in your history. You can then open another test, or this one again from the start.',
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Keep the test')),
        FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Discard')),
      ],
    ),
  );
  if (sure != true) return false;
  try {
    await deleteSession(session);
  } catch (e) {
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not discard the test ($e).')));
    }
    return false;
  }
  return true;
}

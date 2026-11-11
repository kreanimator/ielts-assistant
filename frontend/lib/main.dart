import 'package:flutter/material.dart';

import 'home/dashboard_page.dart';

void main() => runApp(const App());

class App extends StatelessWidget {
  const App({super.key});

  ThemeData _theme(Brightness brightness) => ThemeData(
    fontFamily: 'Roboto',
    fontFamilyFallback: const ['NotoSans'], // phonetic symbols
    colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF3F51B5), brightness: brightness),
  );

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'IELTS Assistant',
    debugShowCheckedModeBanner: false,
    theme: _theme(Brightness.light),
    darkTheme: _theme(Brightness.dark),
    home: const DashboardPage(),
  );
}

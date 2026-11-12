import 'package:flutter/material.dart';

import '../api.dart';

/// A test's pages as the book prints them, one under the other, with buttons to jump to each
/// passage (or section) and to zoom.
class BookPages extends StatefulWidget {
  const BookPages({super.key, required this.book, required this.pages, required this.parts, required this.partName});

  final String book;
  final List<int> pages;
  final List<ReadingPart> parts;
  final String partName; // "Passage" or "Section"

  @override
  State<BookPages> createState() => _BookPagesState();
}

class _BookPagesState extends State<BookPages> {
  static const _zooms = [1.0, 1.25, 1.5, 2.0];
  final _scroll = ScrollController();
  late final _keys = {for (final p in widget.pages) p: GlobalKey()};
  int _zoom = 0;

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  void _jump(int page) {
    final target = _keys[page]?.currentContext;
    if (target != null) {
      Scrollable.ensureVisible(target, duration: const Duration(milliseconds: 300), curve: Curves.easeOut);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Expanded(
              child: SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(
                  children: [
                    for (final p in widget.parts)
                      Padding(
                        padding: const EdgeInsets.only(right: 8),
                        child: ActionChip(label: Text('${widget.partName} ${p.part}'), onPressed: () => _jump(p.page)),
                      ),
                  ],
                ),
              ),
            ),
            IconButton(
              tooltip: 'Smaller',
              onPressed: _zoom > 0 ? () => setState(() => _zoom--) : null,
              icon: const Icon(Icons.zoom_out),
            ),
            IconButton(
              tooltip: 'Larger',
              onPressed: _zoom < _zooms.length - 1 ? () => setState(() => _zoom++) : null,
              icon: const Icon(Icons.zoom_in),
            ),
          ],
        ),
        const SizedBox(height: 4),
        Expanded(
          child: DecoratedBox(
            decoration: BoxDecoration(
              color: theme.colorScheme.surfaceContainerHighest,
              borderRadius: BorderRadius.circular(8),
            ),
            child: LayoutBuilder(
              builder: (context, constraints) {
                final width = constraints.maxWidth * _zooms[_zoom];
                final column = SingleChildScrollView(
                  controller: _scroll,
                  padding: const EdgeInsets.all(8),
                  child: Column(
                    children: [
                      for (final page in widget.pages)
                        Padding(
                          key: _keys[page],
                          padding: const EdgeInsets.only(bottom: 8),
                          child: Image.network(
                            pagePicture(widget.book, page),
                            width: width - 16,
                            fit: BoxFit.fitWidth,
                            filterQuality: FilterQuality.medium,
                            frameBuilder: (context, child, frame, _) => frame == null
                                // the size of a page until it arrives, so the jumps land right
                                ? SizedBox(
                                    width: width - 16,
                                    height: (width - 16) * 1.41,
                                    child: const Center(child: CircularProgressIndicator()),
                                  )
                                : child,
                            errorBuilder: (context, error, stack) =>
                                SizedBox(height: 200, child: Center(child: Text('Page $page could not be loaded.'))),
                          ),
                        ),
                    ],
                  ),
                );
                return Scrollbar(
                  controller: _scroll,
                  notificationPredicate: (n) => n.metrics.axis == Axis.vertical,
                  child: _zoom == 0
                      ? column
                      : SingleChildScrollView(
                          scrollDirection: Axis.horizontal,
                          child: SizedBox(width: width, child: column),
                        ),
                );
              },
            ),
          ),
        ),
      ],
    );
  }
}

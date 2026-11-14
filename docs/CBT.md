# The computer-delivered test screen: what was measured, what was not

The Reading test screen (and the Listening one to come) follows the official familiarisation
tests published by IDP (`ielts.idp.com/about/ielts-familiarisation-tests`, an Inspera player).
The values below were read from that demo's page in a 1920-pixel-wide window, November 2026.
The frame is `frontend/lib/core/widgets/exam_shell.dart`.

## Measured in the demo

| Element | Value |
|---|---|
| Typeface | Arial 16 px on 24 px lines, black on white (here Liberation Sans, the same measures) |
| Header | 56 px high, white; "Test taker ID" 16 px semi-bold; icons 24 px, rgb(51,51,51) |
| Part box | background rgb(241,242,236), border 1 px rgb(213,213,213), padding 12/16 px; "Part 1" bold, then "Read the text and answer questions 1–13." |
| Passage title | 17.6 px bold |
| Panes | passage left, questions right, a line between them with a ↔ handle that drags |
| Group heading | "Questions 1–6", 16 px bold; key words of the instructions in bold |
| Current question | its number in a 2 px rgb(65,142,200) frame, radius 3 |
| TRUE / FALSE / NOT GIVEN, multiple choice | radio buttons in a column; the chosen row light blue (about rgb(189,215,238)) |
| Choose TWO | checkboxes |
| Gap | a box in the sentence, 1 px rgb(83,83,83), radius 3, the question number bold in it until typed in |
| Bottom bar | 53 px; a third per part; the current part lists its numbers, each under a 3 px line, grey rgb(215,215,215) or green rgb(53,142,20) once answered; the current number framed in blue; other parts "Part 2  0 of 13" (the count rgb(117,117,117)); ✓ at the right |
| Arrows | previous / next question, dark squares above the bar at the right |
| Highlight | select, right click, "Note" or "Highlight"; highlighted text white on rgb(125,74,90) |
| Notes | a 300 px panel at the right, a card per note with the text it is about and Delete |
| Options (≡) | Go to submission page; Contrast (black on white, white on black, yellow on black); Text size (Regular, Large, Extra large) |
| Listening | a "Play" overlay first ("You will not be permitted to pause or rewind the audio"); then "Audio is Playing" under the name in the header; questions across the full width; four parts in the bar |

## Not shown by the demo (our own choices)

- The clock: the demo is not timed. Ours shows "N minutes left" in the middle of the header,
  red in the last five minutes, seconds in the last one. The real test's warnings are not verified.
- The text-size factors (1, 1.25, 1.5) and the colours of the two dark contrast modes.
- A volume control: the demo's speaker icon does nothing.
- What a click on a highlight offers: ours offers "Clear" on a right click.

## Known differences

- Listening: the real test plays an introduction and gives time to read each part's questions
  inside the recording; ours plays the book's CD recordings, which include those pauses. The
  real test has no "Check your answers" label; its two minutes at the end are the same. The
  clock runs on the server from Play, so a reload continues the recording where it is by then.

- Matching headings: the demo drags headings into boxes in the passage; here each question has
  a small list to choose from beside it.
- A selection to highlight stays inside one paragraph; the questions cannot be highlighted.
- "Show the printed page" above the passage, and a back arrow in the header, are ours: the text
  comes from scanned books and a word may be read wrongly.
- A table, a diagram or a group that could not be read is shown as its printed picture.

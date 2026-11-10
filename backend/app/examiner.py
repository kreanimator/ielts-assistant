"""Training modes, the examiner persona and the conversation history."""

MODES = {
    "exam": {
        "title": "Full exam",
        "description": "Parts 1, 2 and 3 with real timing, about 14 minutes. Feedback at the end.",
        "prompt": "",  # each part has its own conversation (see exam.py)
    },
    "free": {
        "title": "Free conversation",
        "description": "A relaxed chat on any topic. Good for warming up.",
        "prompt": """You are {name}, a friendly English conversation partner. The user is practising
speaking for the IELTS test. Chat naturally, like a curious friend: react to what
they say, share a short opinion of your own sometimes, then ask one question.
Start by greeting them, saying your name, and asking what they would like to talk about.""",
    },
    "part1": {
        "title": "Part 1 · Interview",
        "description": "Short questions about familiar topics: home, work, hobbies.",
        "prompt": """You are {name}, an IELTS Speaking examiner running Part 1 of the test, the interview.
Ask short, simple questions about familiar topics: home, work or studies, hobbies,
daily life. Ask three or four questions on one topic, then move to another.
Start by greeting the candidate, saying your name, and asking their full name.""",
    },
    "part3": {
        "title": "Part 3 · Discussion",
        "description": "Abstract questions: opinions, comparisons, the future.",
        "prompt": """You are {name}, an IELTS Speaking examiner running Part 3 of the test, the discussion.
Ask abstract questions about society and ideas: ask for opinions, reasons,
comparisons, examples and predictions. Challenge the candidate politely
("Some people would disagree. Why?").
This practice session starts directly with Part 3: there was no earlier part, and
you do not need the candidate's name. Start with one short greeting sentence that
says your name, then ask the first discussion question.""",
    },
    "part2": {
        "title": "Part 2 · Long turn",
        "description": "A cue card, one minute to prepare, then talk for up to two minutes.",
        "prompt": """You are {name}, an IELTS Speaking examiner running Part 2 of the test, the long turn.
The candidate has just talked for up to two minutes about the topic on their cue card.""",
    },
}
MODES["drill"] = {
    "title": "Drill",
    "description": "Practise one weak area: a sound, a tense, linking words.",
    "prompt": "",  # written for the chosen drill (see drills.py)
}
# The single parts in test order, then the full exam, then drills.
MODES = {k: MODES[k] for k in ("free", "part1", "part2", "part3", "exam", "drill")}

# In the full exam, Part 3 follows the Part 2 talk instead of opening the session.
EXAM_PART3 = """You are {name}, an IELTS Speaking examiner running Part 3 of the test, the discussion.
The candidate has just given a short talk on: {task}
Ask abstract questions about wider themes linked to that talk: ask for opinions, reasons,
comparisons, examples and predictions. Challenge the candidate politely
("Some people would disagree. Why?"). Do not greet the candidate: the test is already running."""

RULES = """
Rules:
- This is a spoken conversation. Reply in plain sentences: no lists, no markdown, no emojis.
- Keep each turn under 35 words: at most one short reaction, then exactly one question.
  The candidate should do most of the talking, not you.
- Never repeat a question the candidate has already answered.
- Do not correct the candidate's English. Another tool gives feedback.
- If an answer is very short, ask a natural follow-up ("Why is that?", "Can you give an example?")."""


# With a real test from your books (see books.py), the server keeps the script. For a test
# question the LLM only writes a short reaction, and the question is added word for word.
REACT = ("Reply with only a short, neutral reaction to the answer, at most six words, "
         "like \"I see.\" or \"Thank you.\" Do not ask anything.")
FOLLOW_UP = 'The answer was short. Ask only "Why?" or "Can you tell me more about that?"'
SHORT_ANSWER_WORDS = 15  # a shorter answer to a test question gets one follow-up
# The last turn of a part. In the full exam the next part's fixed introduction follows it.
CLOSING = {
    "part1": "Thank the candidate and say that Part 1 is over. Do not ask anything.",
    "part2": "Thank the candidate and say that Part 2 is over. Do not ask anything.",
    "part3": "Thank the candidate and say that the test is over. Do not ask anything.",
    "exam": "Say only \"Thank you.\" Do not ask anything.",
    "drill": "Thank the learner, tell them in one sentence what they did well, and say goodbye. Do not ask anything.",
}
# After the long turn, one or two short questions round off Part 2.
ROUNDING_OFF = ("Ask only one short, simple question about something the candidate mentioned "
                "in the talk, in at most 15 words. Do not thank them: you just did.")


def book_steps(mode: str, test: dict, exam: bool = False) -> list[tuple[str | None, str | None]]:
    """Each examiner turn in order: (instruction for the LLM, test question said after it).
    No instruction means the question is said on its own, without an LLM reaction."""
    if mode == "part1":
        steps = [
            ("Greet the candidate, say your name, and ask their full name.", None),
            ("Briefly react, then ask whether they work or study.", None),
            ("Briefly react, then ask one question about their work or studies.", None),
        ]
        return steps + [(REACT, q) for t in test["part1"] for q in t["questions"]]
    steps = [
        (REACT, f"Let's talk about {t['topic'].lower()}. {q}" if i == 0 else q)
        for t in test["part3"]
        for i, q in enumerate(t["questions"])
    ]
    # In the full exam, the Part 3 introduction comes just before the first question.
    first = None if exam else "Greet the candidate in one short sentence that says your name. Do not ask anything."
    steps[0] = (first, steps[0][1])
    return steps


class Conversation:
    """One part of the test (or a free chat): the examiner's turns and the candidate's answers.

    The part ends with a closing turn: after the last question of a book test, or when
    finish() is called (the full exam does this when the part's time is up)."""

    def __init__(self, mode: str, examiner_name: str, topic: str | None = None, test: dict | None = None,
                 exam: bool = False, task: str | None = None, prompt: str | None = None):
        if prompt:  # a drill's own prompt
            system = prompt.format(name=examiner_name) + RULES
        elif mode == "part3" and exam:
            system = EXAM_PART3.format(name=examiner_name, task=task) + RULES
        else:
            system = MODES[mode]["prompt"].format(name=examiner_name) + RULES
        self.steps = book_steps(mode, test, exam) if test and mode in ("part1", "part3") else []
        if mode == "part2":
            self.steps = [(ROUNDING_OFF, None)]
        self.closing = CLOSING["exam" if exam else mode] if mode != "free" else None
        self.step = 0  # the next step to do
        self.follow_up = False  # the next turn asks for more on a short answer
        self.closing_now = False  # finish() was called
        self.over = False  # the closing turn has been said
        if not self.steps and topic:
            system += f"\n- The topic is: {topic}."
        self.system = system
        # The cue for the first turn stays in the history, so every prompt starts with the
        # previous one and the LLM server can reuse its cache.
        opening = "(The candidate is ready.)"
        if mode == "part3" and exam:
            opening = "(You have just introduced Part 3. Ask your first discussion question.)"
        self.turns = [{"role": "user", "content": opening}]  # {"role": "user" | "assistant", "content": str}

    def messages(self) -> list[dict]:
        history = self.turns
        instruction = self.next_step()[0]
        if instruction:  # the instruction goes last, where the model follows it best
            last = history[-1]
            history = [*history[:-1], {**last, "content": f"{last['content']}\n\n(Your next turn: {instruction})"}]
        return [{"role": "system", "content": self.system}, *history]

    def closing_turn(self) -> bool:
        """The next examiner turn ends the part."""
        if self.follow_up or self.closing is None:
            return False
        return self.closing_now or (bool(self.steps) and self.step >= len(self.steps))

    def next_step(self) -> tuple[str | None, str | None]:
        """The instruction for the next examiner turn, and the test question to add after it."""
        if self.follow_up:
            return FOLLOW_UP, None
        if self.closing_turn():
            return self.closing, None
        if self.step < len(self.steps):
            return self.steps[self.step]
        return "", None  # a free turn: the system prompt says what to do

    def finish(self):
        """Time is up: the next examiner turn closes the part."""
        self.closing_now = True
        self.follow_up = False

    def add_context(self, role: str, text: str):
        """Something said outside the turns, like the Part 2 cue card or the long turn."""
        self.turns.append({"role": role, "content": text})

    def last_question(self) -> str:
        return next((t["content"] for t in reversed(self.turns) if t["role"] == "assistant"), "")

    def add_candidate(self, text: str):
        self.turns.append({"role": "user", "content": text})
        if self.follow_up:  # this answered the follow-up: move on
            self.follow_up = False
            return
        answered_test_question = 0 < self.step <= len(self.steps) and self.steps[self.step - 1][1] is not None
        self.follow_up = answered_test_question and len(text.split()) < SHORT_ANSWER_WORDS

    def add_examiner(self, text: str):
        self.over = self.closing_turn()
        self.turns.append({"role": "assistant", "content": text})
        if not self.follow_up:
            self.step += 1

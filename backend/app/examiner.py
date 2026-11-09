"""Training modes, the examiner persona and the conversation history."""

MODES = {
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
}

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


def book_steps(mode: str, test: dict) -> list[tuple[str, str | None]]:
    """Each examiner turn in order: (instruction for the LLM, test question said after it)."""
    if mode == "part1":
        steps = [
            ("Greet the candidate, say your name, and ask their full name.", None),
            ("Briefly react, then ask whether they work or study.", None),
            ("Briefly react, then ask one question about their work or studies.", None),
        ]
        steps += [(REACT, q) for t in test["part1"] for q in t["questions"]]
        return steps + [("Thank the candidate and say that Part 1 is over.", None)]
    steps = [
        (REACT, f"Let's talk about {t['topic'].lower()}. {q}" if i == 0 else q)
        for t in test["part3"]
        for i, q in enumerate(t["questions"])
    ]
    steps[0] = ("Greet the candidate in one short sentence that says your name. Do not ask anything.", steps[0][1])
    return steps + [("Thank the candidate and say that the test is over.", None)]


class Conversation:
    def __init__(self, mode: str, examiner_name: str, topic: str | None = None, test: dict | None = None):
        system = MODES[mode]["prompt"].format(name=examiner_name) + RULES
        self.steps = book_steps(mode, test) if test and mode in ("part1", "part3") else []
        self.step = 0  # the next step to do
        self.follow_up = False  # the next turn asks for more on a short answer
        if not self.steps and topic:
            system += f"\n- The topic is: {topic}."
        self.system = system
        self.turns = []  # {"role": "user" | "assistant", "content": str}

    def messages(self) -> list[dict]:
        history = self.turns or [{"role": "user", "content": "(The candidate is ready.)"}]
        if self.steps:  # the instruction goes last, where the model follows it best
            last = history[-1]
            history = [*history[:-1], {**last, "content": f"{last['content']}\n\n(Your next turn: {self.next_step()[0]})"}]
        return [{"role": "system", "content": self.system}, *history]

    def next_step(self) -> tuple[str, str | None]:
        """The instruction for the next examiner turn, and the test question to add after it."""
        if self.follow_up:
            return FOLLOW_UP, None
        if self.step < len(self.steps):
            return self.steps[self.step]
        return "The test is over. Say goodbye in one short sentence.", None

    def last_question(self) -> str:
        return next((t["content"] for t in reversed(self.turns) if t["role"] == "assistant"), "")

    def answer_count(self) -> int:
        return sum(t["role"] == "user" for t in self.turns)

    def add_candidate(self, text: str):
        self.turns.append({"role": "user", "content": text})
        if self.follow_up:  # this answered the follow-up: move on
            self.follow_up = False
            return
        answered_test_question = 0 < self.step <= len(self.steps) and self.steps[self.step - 1][1] is not None
        self.follow_up = answered_test_question and len(text.split()) < SHORT_ANSWER_WORDS

    def add_examiner(self, text: str):
        self.turns.append({"role": "assistant", "content": text})
        if not self.follow_up:
            self.step += 1

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


class Conversation:
    def __init__(self, mode: str, examiner_name: str, topic: str | None = None):
        system = MODES[mode]["prompt"].format(name=examiner_name) + RULES
        if topic:
            system += f"\n- The topic is: {topic}."
        self.system = system
        self.turns = []  # {"role": "user" | "assistant", "content": str}

    def messages(self) -> list[dict]:
        history = self.turns or [{"role": "user", "content": "(The candidate is ready.)"}]
        return [{"role": "system", "content": self.system}, *history]

    def add_candidate(self, text: str):
        self.turns.append({"role": "user", "content": text})

    def add_examiner(self, text: str):
        self.turns.append({"role": "assistant", "content": text})

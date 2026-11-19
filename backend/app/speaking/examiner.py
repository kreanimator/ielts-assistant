"""Training modes, the examiner persona and the conversation history.

How the examiner talks follows what examiners do in recorded mock tests (counted in the 123
mock tests of the Ross IELTS Academy channel, see videos.py), in our own words: most questions come
with no reaction at all, about one in four starts with "And", and a reaction is nearly
always "Okay." or "All right."; three questions on a Part 1 topic, then "Now let's move on
to talk about ..."; a question the candidate did not catch is repeated word for word.
"""
import random
import re
import time

from ..core import llm

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
    "letter": {
        "title": "By letter",
        "description": "Pick a letter and get a random topic card from eslconversationquestions.com.",
        "prompt": """You are {name}, a friendly English conversation partner. The user is practising
speaking for the IELTS test with questions from a topic card. Listen to the answers and
react like an interested friend; the questions themselves are given to you.""",
    },
    "part1": {
        "title": "Part 1 · Interview",
        "description": "Short questions about familiar topics: home, work, hobbies.",
        "prompt": """You are {name}, an IELTS Speaking examiner running Part 1 of the test, the interview.
You have greeted the candidate and asked their name. Ask short, simple questions about
familiar topics: home, work or studies, hobbies, daily life. Ask three questions on one
topic, then move to another with "Now let's move on to talk about ..." or "Let's talk about ...".""" + "{style}",
    },
    "part3": {
        "title": "Part 3 · Discussion",
        "description": "Abstract questions: opinions, comparisons, the future.",
        "prompt": """You are {name}, an IELTS Speaking examiner running Part 3 of the test, the discussion.
Ask abstract questions about society and ideas: ask for opinions, reasons,
comparisons, examples and predictions. Challenge the candidate politely
("Some people would disagree. Why?").{style}
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
MODES = {k: MODES[k] for k in ("free", "letter", "part1", "part2", "part3", "exam", "drill")}

# In the full exam, Part 3 follows the Part 2 talk instead of opening the session.
EXAM_PART3 = """You are {name}, an IELTS Speaking examiner running Part 3 of the test, the discussion.
The candidate has just given a short talk on: {task}
Ask abstract questions about wider themes linked to that talk: ask for opinions, reasons,
comparisons, examples and predictions. Challenge the candidate politely
("Some people would disagree. Why?"). Do not greet the candidate: the test is already running.{style}"""
# Examiners do not comment on answers: a word like "Okay." at most, often nothing.
STYLE = """
Like a real examiner, never praise or comment on an answer: at most say "Okay." or
"All right." before your question, and often nothing at all."""

RULES = """
Rules:
- This is a spoken conversation. Reply in plain sentences: no lists, no markdown, no emojis.
- Keep each turn under 35 words: at most one short reaction, then exactly one question.
  The candidate should do most of the talking, not you.
- Never repeat a question the candidate has already answered.
- Do not correct the candidate's English. Another tool gives feedback.
- If an answer is very short, ask a natural follow-up ("Why is that?", "Can you give an example?")."""


# With a real test (from your books, see books.py, or a mock-test video, see videos.py) the
# server keeps the script: the questions are said word for word, with the examiner's
# reaction chosen here, without the LLM.
REACTIONS = ["Okay."] * 6 + ["All right."] * 2 + ["Right.", "Thank you."]
REACTION_SHARE = 0.3  # of the questions that get a reaction first
AND_SHARE = 0.3  # of the questions that start with "And"
FOLLOW_UPS = {"part1": ["Why?", "Why is that?", "Can you tell me a bit more about that?"],
              "part3": ["Why do you think so?", "Why is that?", "Can you give me an example?", "Why?"]}
SHORT_ANSWER_WORDS = 15  # a shorter answer to a test question gets one follow-up
PART3_QUESTIONS = 4  # fewer, and the full exam's Part 3 goes on with the LLM's questions
# The last turn of a part: a fixed line, or an instruction for the LLM. In the full exam the
# next part's fixed introduction follows it.
CLOSING = {
    "part1": "Thank you. That's the end of Part 1.",
    "part2": "Thank you. That's the end of Part 2.",
    "part3": "Thank you. That's the end of the speaking test.",
    "exam": "Thank you.",
}
CLOSING_LLM = {
    "letter": "Thank the learner for the chat, and say goodbye. Do not ask anything.",
    "drill": "Thank the learner, tell them in one sentence what they did well, and say goodbye. Do not ask anything.",
}
# Topics said with "your": "Let's talk about your hometown."
YOUR = {"hometown", "home", "family", "job", "work", "studies", "work or studies", "neighbourhood",
        "neighborhood", "daily routine", "free time", "friends", "childhood", "name", "house",
        "accommodation", "home town", "studies or work", "weekends", "hobbies"}
YES_NO = re.compile(r"^(do|does|did|is|are|was|were|should|can|could|will|would|have|has)\b", re.I)
# "Could you repeat the question?", "Sorry, I didn't catch that.", "Pardon?"
REPEAT = re.compile(r"\b(repeat|say (that|it) again|pardon|once more|one more time|"
                    r"didn'?t (catch|hear|get|understand)|don'?t understand|"
                    r"(what|which) do you mean|what was the question|sorry\?)", re.I)


def asks_repeat(text: str) -> bool:
    """The candidate asks to hear the question again (a short request, not an answer)."""
    return len(text.split()) <= 15 and bool(REPEAT.search(text))


def daypart() -> str:
    hour = time.localtime().tm_hour
    return "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"


def topic_name(topic: str) -> str:
    name = topic.strip().rstrip(".").lower()
    return f"your {name}" if name in YOUR else name


def lead_in(question: str, rng: random.Random) -> str:
    """Now and then "Okay." first, or "And ..." as examiners say it."""
    reaction = rng.choice(REACTIONS) + " " if rng.random() < REACTION_SHARE else ""
    if rng.random() < AND_SHARE and question[:1].isupper() and not question.startswith(("I ", "I'")):
        question = "And " + question[0].lower() + question[1:]
    return reaction + question


def spoken(question: str) -> str:
    """As an examiner says it: "programmes/shows" → "programmes or shows"."""
    return re.sub(r"(?<=\w)/(?=\w)", " or ", question)


def why_or_why_not(question: str) -> str:
    """Part 3 yes/no questions ask for reasons too, as examiners add (not "Could you ...?")."""
    request = re.match(r"^(can|could|would|will) you\b", question, re.I)
    if YES_NO.match(question) and not request and "why" not in question.lower() and question.endswith("?"):
        return question + " Why or why not?"
    return question


def opening(name: str) -> list[tuple[str | None, str | None]]:
    """The start of Part 1: the candidate's name. (A real examiner also checks the ID.)"""
    return [(None, f"Good {daypart()}. My name is {name}. Could you tell me your full name, please?"),
            (None, "Thank you. And what can I call you?")]
OPENING_ANSWERS = 2  # the answers to the opening are not test answers
# After the long turn, one or two short questions round off Part 2.
ROUNDING_OFF = ("Ask only one short, simple question about something the candidate mentioned "
                "in the talk, in at most 15 words. Do not thank them: you just did. Do not comment on the talk.")


# On a topic card (see esl.py) the questions are the card's, word for word.
REACT_FRIENDLY = ("Reply with only a short, friendly reaction to the answer, at most twelve words, "
                  "that shows you listened. Do not ask anything.")


def card_steps(card: dict) -> list[tuple[str | None, str | None]]:
    first, *rest = card["questions"]
    return [("Greet the learner in one short sentence that says your name. Do not ask anything.",
             f"Today's topic is {card['name'].lower()}. {first}"),
            *[(REACT_FRIENDLY, q) for q in rest]]


WORK_OR_HOME = re.compile(r"work|stud|job|home|live|accommodation|house|flat", re.I)
FIRST_PART1 = "In this first part, I'd like to ask you some questions about yourself."


def book_steps(mode: str, test: dict, name: str, exam: bool = False,
               rng: random.Random | None = None) -> list[tuple[str | None, str | None]]:
    """Each examiner turn in order: (instruction for the LLM, test question said after it).
    No instruction means the question is said on its own, without the LLM."""
    rng = rng or random.Random()
    steps = []
    if mode == "part1":
        steps = opening(name)
        topics = test["part1"]
        # The interview starts with work or studies, or the candidate's home.
        if not WORK_OR_HOME.search(topics[0]["topic"]):
            steps.append((None, f"Thank you. {FIRST_PART1} Let's start with what you do. "
                                "Do you work or are you a student?"))
            steps.append(("Ask one short question about the candidate's work or studies.", None))
        for n, t in enumerate(topics):
            for i, q in enumerate(map(spoken, t["questions"])):
                if i:
                    steps.append((None, lead_in(q, rng)))
                elif n == 0 and len(steps) == OPENING_ANSWERS:
                    steps.append((None, f"Thank you. {FIRST_PART1} First, I'd like to ask you about "
                                        f"{topic_name(t['topic'])}. {q}"))
                else:
                    move = rng.choice(["Now let's move on to talk about", "Let's talk about", "Now let's talk about"])
                    steps.append((None, f"{move} {topic_name(t['topic'])}. {q}"))
        return steps
    for n, t in enumerate(test["part3"]):
        for i, q in enumerate(t["questions"]):
            q = why_or_why_not(spoken(q))
            if i:
                steps.append((None, lead_in(q, rng)))
            elif n == 0 and exam:  # the Part 3 introduction has just been said
                steps.append((None, q))
            elif n == 0:
                steps.append((None, f"Good {daypart()}. My name is {name}. In this part, I'd like to "
                                    f"discuss {topic_name(t['topic'])} with you. {q}"))
            elif len(t["questions"]) > 1:
                steps.append((None, f"Now let's talk about {topic_name(t['topic'])}. {q}"))
            else:  # a theme of one question goes on without an announcement
                steps.append((None, lead_in(q, rng)))
    return steps


class Conversation:
    """One part of the test (or a free chat): the examiner's turns and the candidate's answers.

    The part ends with a closing turn: after the last question of a real test, or when
    finish() is called (the full exam does this when the part's time is up). Part 1 without
    a test starts with the fixed opening, and the LLM goes on from there."""

    def __init__(self, mode: str, examiner_name: str, topic: str | None = None, test: dict | None = None,
                 exam: bool = False, task: str | None = None, prompt: str | None = None,
                 card: dict | None = None):
        if prompt:  # a drill's own prompt
            system = prompt.format(name=examiner_name) + RULES
        elif mode == "part3" and exam:
            system = EXAM_PART3.format(name=examiner_name, task=task, style=STYLE) + RULES
        else:
            system = MODES[mode]["prompt"].format(name=examiner_name, style=STYLE) + RULES
        self.mode = mode
        self.open_ended = False  # after the steps, the LLM goes on until the part is closed
        self.procedural = 0  # the first answers of the steps are not test answers (the name)
        self.steps = []
        if test and mode in ("part1", "part3"):
            self.steps = book_steps(mode, test, examiner_name, exam)
            self.procedural = OPENING_ANSWERS if mode == "part1" else 0
            # In the timed exam, a short Part 3 goes on with the LLM's questions until the time is up.
            self.open_ended = exam and mode == "part3" and len(self.steps) < PART3_QUESTIONS
        elif mode == "part1" and not prompt:
            self.steps, self.open_ended, self.procedural = opening(examiner_name), True, OPENING_ANSWERS
        if mode == "part2":
            self.steps = [(ROUNDING_OFF, None)]
        if card:
            self.steps = card_steps(card)
        key = "exam" if exam else mode
        self.closing = CLOSING.get(key) or CLOSING_LLM.get(key)
        self.closing_fixed = key in CLOSING
        self.step = 0  # the next step to do
        self.follow_up = False  # the next turn asks for more on a short answer
        self.closing_now = False  # finish() was called
        self.over = False  # the closing turn has been said
        if (not self.steps or self.open_ended) and topic:
            system += f"\n- The topic is: {topic}."
        self.system = system
        # The cue for the first turn stays in the history, so every prompt starts with the
        # previous one and the LLM server can reuse its cache.
        opening_cue = "(The candidate is ready.)"
        if mode == "part3" and exam:
            opening_cue = "(You have just introduced Part 3. Ask your first discussion question.)"
        self.turns = [{"role": "user", "content": opening_cue}]  # {"role": "user" | "assistant", "content": str}

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
        return self.closing_now or (bool(self.steps) and not self.open_ended and self.step >= len(self.steps))

    def next_step(self) -> tuple[str | None, str | None]:
        """The instruction for the next examiner turn, and the line to say after it (word for word).
        No instruction: the line is said without the LLM."""
        if self.follow_up:
            return None, random.choice(FOLLOW_UPS["part3" if self.mode == "part3" else "part1"])
        if self.closing_turn():
            return (None, self.closing) if self.closing_fixed else (self.closing, None)
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

    def answer_counts(self) -> bool:
        """The coming answer is a test answer (not the candidate's name). It answers step self.step - 1."""
        return self.step > self.procedural

    def repeat_line(self) -> str:
        """The last question again, word for word, as examiners do: "Sure. Do you ...?"."""
        sentences = llm.SENTENCE_END.split(self.last_question().strip())
        while len(sentences) > 1 and not sentences[0].endswith("?"):
            sentences = sentences[1:]  # the reaction or the topic's introduction
        question = " ".join(sentences)
        question = re.sub(r"^(okay|all right|right|thank you)[.,]\s*", "", question, flags=re.I)
        if question.lower().startswith("and "):
            question = question[4].upper() + question[5:]
        return f"Sure. {question}"

    def add_repeat(self, request: str, line: str):
        """The candidate asked to hear the question again: the history keeps it, the steps stay."""
        self.turns += [{"role": "user", "content": request}, {"role": "assistant", "content": line}]

    def add_candidate(self, text: str):
        self.turns.append({"role": "user", "content": text})
        if self.follow_up:  # this answered the follow-up: move on
            self.follow_up = False
            return
        answered_test_question = self.procedural < self.step <= len(self.steps) and self.steps[self.step - 1][1] is not None
        # No follow-up when the next turn is the LLM's own question on this answer.
        llm_next = self.step < len(self.steps) and self.steps[self.step][1] is None
        self.follow_up = answered_test_question and not llm_next and len(text.split()) < SHORT_ANSWER_WORDS

    def add_examiner(self, text: str):
        self.over = self.closing_turn()
        self.turns.append({"role": "assistant", "content": text})
        if not self.follow_up:
            self.step += 1

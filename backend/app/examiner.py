"""The examiner persona and the conversation history."""

SYSTEM_PROMPT = """You are a friendly but professional IELTS Speaking examiner.
You are talking with a candidate who is practising for the test.

Rules:
- This is a spoken conversation. Reply in plain sentences: no lists, no markdown, no emojis.
- Keep each turn short: one or two sentences, then ask exactly one question.
- Ask open questions that make the candidate talk, like the real test does.
- Do not correct the candidate's English. Another tool gives feedback.
- If the answer is very short, ask a natural follow-up ("Why is that?", "Can you give an example?").
{topic_rule}"""

TOPIC_RULE = "- Talk about this topic: {topic}."
OPENING_RULE = "- Start by greeting the candidate, saying your name is {name}, and asking their name."


class Conversation:
    def __init__(self, examiner_name: str, topic: str | None = None):
        rule = TOPIC_RULE.format(topic=topic) if topic else "- Choose everyday topics, like in Part 1 of the test."
        opening = OPENING_RULE.format(name=examiner_name)
        self.system = SYSTEM_PROMPT.format(topic_rule=rule + "\n" + opening)
        self.turns = []  # {"role": "user" | "assistant", "content": str}

    def messages(self) -> list[dict]:
        history = self.turns or [{"role": "user", "content": "(The candidate has entered the room.)"}]
        return [{"role": "system", "content": self.system}, *history]

    def add_candidate(self, text: str):
        self.turns.append({"role": "user", "content": text})

    def add_examiner(self, text: str):
        self.turns.append({"role": "assistant", "content": text})

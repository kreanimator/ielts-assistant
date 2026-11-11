"""The order and timing of a session: single parts, and the full exam with strict timing.

Full exam (times from config.py):
  Part 1  interview, about 5 minutes. After PART1_SECONDS - WRAP_UP_SECONDS no new question
          is asked; at PART1_SECONDS an answer still going on is cut off.
  Part 2  long turn: the cue card, one minute to prepare (no skipping), up to two minutes
          of talk, cut off at the limit, then one rounding-off question.
  Part 3  discussion linked to the Part 2 topic, timed like Part 1.
No corrections are shown during the exam; the report comes at the end.

The examiner's fixed lines below are our own wording, not the official examiner script.
"""
import random
import time

from ..core import llm
from . import config, drills
from .examiner import Conversation

PART2_INTRO = ("Now I'm going to give you a topic, and I'd like you to talk about it for one to two "
               "minutes. You have one minute to prepare first, and you can make some notes if you wish. "
               "Here is your topic.")
PART2_START = ("All right, your preparation time is over. Remember, you have one to two minutes. "
               "I'll stop you when the time is up. Please start speaking now.")
PART2_THANKS = "Thank you."
PART2_TIME_UP = "Thank you, that's the time."
EXAM_END = "That is the end of the speaking test. Thank you, and goodbye."

# Original cue cards, used when no book test is chosen.
CUE_CARDS = [
    {"task": "Describe a skill you learned outside school.",
     "points": ["what the skill is", "who you learned it from", "how long it took to learn",
                "and explain how this skill has helped you."]},
    {"task": "Describe a journey you remember well.",
     "points": ["where you went", "who you travelled with", "what happened on the way",
                "and explain why you remember this journey."]},
    {"task": "Describe a person who has influenced the way you think.",
     "points": ["who this person is", "how you know them", "what they taught you",
                "and explain why their influence matters to you."]},
    {"task": "Describe a place in your town where you like to spend time.",
     "points": ["where it is", "what it looks like", "what you do there",
                "and explain why you enjoy being there."]},
    {"task": "Describe a piece of technology you use every day.",
     "points": ["what it is", "when you started using it", "what you use it for",
                "and explain how your life would change without it."]},
    {"task": "Describe a time when you helped someone.",
     "points": ["who you helped", "what the problem was", "what you did",
                "and explain how you felt afterwards."]},
    {"task": "Describe a book, film or series that made you think.",
     "points": ["what it was", "when you read or watched it", "what it was about",
                "and explain why it made you think."]},
    {"task": "Describe a celebration you enjoyed.",
     "points": ["what was celebrated", "where it took place", "who was there",
                "and explain why you enjoyed it."]},
    {"task": "Describe a change you would like to make in your daily routine.",
     "points": ["what the change is", "why you have not made it yet", "how you could make it",
                "and explain how it would improve your life."]},
    {"task": "Describe a goal you hope to achieve in the next few years.",
     "points": ["what the goal is", "why you chose it", "what you are doing to reach it",
                "and explain how you will feel when you achieve it."]},
]
CUE_CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "task": {"type": "string"},
        "points": {"type": "array", "minItems": 4, "maxItems": 4, "items": {"type": "string"}},
    },
    "required": ["task", "points"],
}
CUE_CARD_PROMPT = """Write one original IELTS Speaking Part 2 cue card on the user's topic.
- task: one line starting "Describe", about a personal experience, person, place or thing.
- points: four short prompts; the last one starts "and explain"."""


async def cue_card(test: dict | None, topic: str | None) -> dict:
    """The book test's cue card, one written by the LLM for your topic, or one of ours."""
    if test:
        return test["part2"]
    if topic:
        try:
            return await llm.complete_json(
                [{"role": "system", "content": CUE_CARD_PROMPT}, {"role": "user", "content": topic}],
                CUE_CARD_SCHEMA,
            )
        except Exception:
            pass  # the shipped cards always work
    return random.choice(CUE_CARDS)


def card_text(card: dict) -> str:
    return f"{card['task']} You should say: " + "; ".join(card["points"])


def subject(card: dict) -> str:
    """"Describe a journey you remember well." → "a journey you remember well"."""
    task = card["task"].strip().rstrip(".")
    return task[len("describe "):] if task.lower().startswith("describe ") else task


async def run(talk, mode: str, name: str, topic: str | None, test: dict | None,
              drill: tuple[str, str] | None = None, card: dict | None = None):
    """Runs one session's examiner side. Returns when the session is over by itself;
    free conversation and Part 1/3 without a book test go on until you end them."""
    if mode == "drill":
        await run_drill(talk, name, topic, drill or ("language", "past"))
    elif mode == "exam":
        await exam(talk, name, topic, test)
    elif mode == "letter" and card:
        await talk.part(f"By letter · {card['name']}")
        await interview(talk, Conversation(mode, name, card=card))
    elif mode == "part2":
        card = await cue_card(test, topic)
        if not test:
            talk.set_topic(card["task"])
        await part2(talk, name, card, exam_mode=False)
    else:
        await interview(talk, Conversation(mode, name, topic, test))


async def exam(talk, name: str, topic: str | None, test: dict | None):
    card = await cue_card(test, topic)  # before Part 1, so the wait is not mid-test
    if not test:
        talk.set_topic(card["task"])

    await talk.part("Part 1 · Interview")
    start = time.monotonic()
    await interview(talk, Conversation("part1", name, test=test, exam=True),
                    wrap_up_at=start + config.PART1_SECONDS - config.WRAP_UP_SECONDS,
                    cut_at=start + config.PART1_SECONDS)

    await talk.part("Part 2 · Long turn")
    await part2(talk, name, card, exam_mode=True)

    await talk.part("Part 3 · Discussion")
    start = time.monotonic()
    await talk.say(f"We've been talking about {subject(card)}. Now I'd like to ask you "
                   "some more general questions related to this.", done=False)
    await interview(talk, Conversation("part3", name, test=test, exam=True, task=card["task"]),
                    wrap_up_at=start + config.PART3_SECONDS - config.WRAP_UP_SECONDS,
                    cut_at=start + config.PART3_SECONDS)
    await talk.say(EXAM_END, done=False)


async def run_drill(talk, name: str, topic: str | None, drill: tuple[str, str]):
    kind, key = drill
    await talk.part(f"Drill · {drills.title(kind, key)}")
    talk.set_topic(drills.title(kind, key))
    if kind == "language":
        talk.focus = drills.analyst_focus(key)
        await interview(talk, Conversation("drill", name, topic, prompt=drills.language_prompt(key)),
                        max_answers=drills.QUESTIONS)
        return
    # A sound: repeat sentences after the examiner. Reading aloud needs no grammar feedback.
    talk.target, talk.analyse_answers = key, False
    sentences = await drills.sentences(key, talk.count_sound)
    for i, sentence in enumerate(sentences):
        lead = "Please repeat after me." if i == 0 else "Next one."
        await talk.say(f"{lead} {sentence}")
        await talk.answer(sentence)
    await talk.say("Well done. That's the end of this drill.", done=False)


async def interview(talk, conversation: Conversation, wrap_up_at: float | None = None, cut_at: float | None = None,
                    max_answers: int | None = None):
    """Question, answer, question... At wrap_up_at (or after max_answers) the part closes
    after the current answer; at cut_at an answer still going on is cut off."""
    answers = 0
    while True:
        await talk.examiner_turn(conversation)
        if conversation.over:
            return
        heard = await talk.answer(conversation.last_question(), cut_at=cut_at)
        if heard:
            conversation.add_candidate(heard)
            answers += 1
        if heard is None or (wrap_up_at and time.monotonic() >= wrap_up_at) or (max_answers and answers >= max_answers):
            conversation.finish()


async def part2(talk, name: str, card: dict, exam_mode: bool):
    if not exam_mode:
        await talk.part("Part 2 · Long turn")
    await talk.say(PART2_INTRO, done=False)
    await talk.cue_card(card, config.PREP_SECONDS, skippable=not exam_mode)
    await talk.say(PART2_START)
    heard = await talk.answer(card_text(card), limit=config.LONG_TURN_SECONDS,
                              silence_ms=config.LONG_TURN_SILENCE_MS)
    await talk.clock(None)
    await talk.say(PART2_TIME_UP if heard is None or talk.was_cut else PART2_THANKS, done=False)

    conversation = Conversation("part2", name, exam=exam_mode)
    conversation.add_context("assistant", f"Here is your topic. {card_text(card)}")
    conversation.add_context("user", heard or "(The candidate said nothing.)")
    await interview(talk, conversation)

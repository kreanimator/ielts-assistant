"""The Writing report: an estimated band for each criterion of each task, corrections, and the
writing band.

- Task Achievement (Task 1) or Task Response (Task 2), Coherence and Cohesion, Lexical Resource,
  Grammatical Range and Accuracy: the LLM judges the answer against the band descriptors, given
  the measured numbers, and must quote evidence before it gives each band.
- Correction: the LLM judges too harshly, so SHIFT is added to each of its bands (fitted on the
  sample answers in your books with scripts/calibrate_writing.py, see SHIFT).
- Length: the words are counted here, not by the LLM. An answer under the minimum loses
  Task Achievement / Response (see length_penalty); one under MIN_WORDS gets no band.
- Register (Task 1): before it grades a letter, the LLM says who the reader is and which register
  that calls for (informal, semi-formal or formal), so a letter to a friend is not marked down, or
  "corrected", for sounding like one.
- Corrections: the LLM's, each of one kind (KINDS), kept only when the words it corrects are
  really in the answer. They are shown apart (see sort_out): real errors (grammar, spelling,
  precision) are marked in the answer; style suggestions, which are correct English that could
  be more natural, are listed as optional and never marked as errors; task notes say what the
  task asked for and the answer lacks.
- A task's band is the average of its four criteria; with both tasks, the writing band counts
  Task 2 twice, as IELTS does: (Task 1 + 2 × Task 2) / 3, rounded like IELTS.

These are practice estimates, not official scores. make calibrate-writing checks them against
the examiners' bands of the sample answers in your books.
"""
import re

from ..core import llm
from ..core.bands import round_band
from ..core.text import moving_type_token_ratio, unknown_words, word_count
from . import test
from .tasks import as_text

MIN_WORDS = 50  # shorter answers get corrections but no band (in practice)
UNANSWERED_WORDS = 20  # in the full test, this many words or fewer is band 1 (none: band 0)
MAX_CORRECTED = 12  # words in one correction: longer is a rewrite, not a correction
BANDS = [b / 2 for b in range(2, 19)]  # 1.0 .. 9.0
# Added to each of the LLM's bands. Fitted with scripts/calibrate_writing.py on 36 sample answers
# in the Cambridge books (one examiner band per answer, so one shift for all four criteria; shift
# only, as in Speaking: a slope would stretch the bands beyond what the samples cover).
# Uncorrected, the LLM was 0.86 bands too low; with the shift fitted without each answer, the
# bias is +0.04 and the average error 0.62 bands (see the README).
SHIFT = 0.9
CRITERIA = ("task_response", "coherence_cohesion", "lexical_resource", "grammar")
# What a correction is about. Only the first three are errors.
KINDS = {
    "G": "grammar",      # a rule of English grammar or punctuation is broken
    "T": "spelling",     # a spelling or typing mistake
    "P": "precision",    # the words say something unclear, exaggerated, inconsistent or not meant
    "S": "style",        # correct English that could be more natural or effective: optional
    "TA": "task",        # something the task asks for is missing, thin or answered wrongly
}
ERRORS = ("G", "T", "P")
MAX_SUGGESTIONS = 3  # style suggestions shown: more would bury the errors
# A "grammar error" whose own reason says the words are fine: a preference, so a suggestion.
PREFERENCE = re.compile(
    r"\bmore\s+(natural|formal|informal|appropriate|polite|common|idiomatic|polished|elegant|sophisticated|concise|"
    r"academic|professional|fluent)\b|\bsounds?\b|\b(is|are|while)\s+(\w+\s+)?(understandable|acceptable|"
    r"grammatically\s+correct|not\s+wrong|correct)\b|\bpreferred\b|\bpreferable\b|\bslightly\b|\bstylistic", re.I)
REGISTERS = ["informal", "semi-formal", "formal"]
REGISTER = {
    "type": "object",
    "properties": {  # the reader first, so the register follows from it
        "reader": {"type": "string"},
        "required": {"type": "string", "enum": REGISTERS},
        "used": {"type": "string", "enum": REGISTERS},
    },
    "required": ["reader", "required", "used"],
}

CRITERION = {
    "type": "object",
    "properties": {  # evidence first, so the band follows from it
        "evidence": {"type": "array", "maxItems": 3, "items": {"type": "string"}},
        "summary": {"type": "string"},
        "band": {"type": "number", "enum": BANDS},
    },
    "required": ["evidence", "summary", "band"],
}
SCHEMA = {
    "type": "object",
    "properties": {
        "task_response": CRITERION,
        "coherence_cohesion": CRITERION,
        "lexical_resource": CRITERION,
        "grammar": CRITERION,
        "corrections": {
            "type": "array",
            "maxItems": 15,
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": list(KINDS)},
                    "original": {"type": "string"},
                    "better": {"type": "string"},
                    "why": {"type": "string"},
                },
                "required": ["kind", "original", "better", "why"],
            },
        },
        "strengths": {"type": "array", "maxItems": 3, "items": {"type": "string"}},
        "priorities": {"type": "array", "maxItems": 3, "items": {"type": "string"}},
    },
    "required": ["task_response", "coherence_cohesion", "lexical_resource", "grammar", "corrections",
                 "strengths", "priorities"],
}

# A letter's schema: the register is decided before anything is graded.
LETTER_SCHEMA = {**SCHEMA, "properties": {"register": REGISTER, **SCHEMA["properties"]},
                 "required": ["register", *SCHEMA["required"]]}

# The band descriptors in brief, in our own words.
LETTER_TASK = """Task Achievement (Task 1, a letter): call it task_response
- 9: covers every bullet point fully and appropriately; purpose and tone exactly right.
- 8: covers every bullet point, each well extended; tone consistent and appropriate.
- 7: covers every bullet point and highlights or extends them clearly; purpose clear; tone
  consistent, with only occasional slips.
- 6: covers every bullet point, though some more fully than others or with irrelevant detail;
  purpose generally clear; tone may vary.
- 5: covers the task only in part, or misses or barely touches one bullet point; purpose may be
  unclear at times; tone may be wrong for the reader; details may be irrelevant or wrong.
- 4: tries to cover the task but misses bullet points or confuses them; purpose unclear; tone
  wrong for the reader.
- 3: does not cover the task; ideas few, largely irrelevant or repeated."""
ESSAY_TASK = """Task Response (Task 2, an essay): call it task_response
- 9: answers every part of the question fully; a fully developed position with relevant,
  well-supported ideas.
- 8: answers every part of the question well; a well-developed answer with relevant, extended,
  supported ideas.
- 7: answers every part of the question; a clear position throughout; main ideas extended and
  supported, though some may be over-generalised or lack focus.
- 6: answers every part of the question, though some more fully than others; a relevant position,
  though the conclusion may be unclear or repeat itself; main ideas relevant but some not
  developed enough or unclear.
- 5: answers the question only in part; a position, but not always clear, and maybe no
  conclusion; main ideas limited, not developed enough, or partly irrelevant.
- 4: answers the question only minimally or off the point; the position is unclear; few main ideas,
  hard to identify, repeated or not supported.
- 3: does not answer the question; no clear position; few ideas, largely undeveloped or
  irrelevant."""
COMMON = """Coherence and Cohesion: call it coherence_cohesion
- 9: cohesion is so natural it attracts no attention; paragraphs managed skilfully.
- 8: information and ideas sequenced logically; all aspects of cohesion well managed; paragraphs
  used well.
- 7: information and ideas organised logically with clear progression; a range of linking words
  used appropriately, with some under- or over-use; a clear central topic in each paragraph.
- 6: information arranged coherently with an overall progression; linking words used effectively
  but some cohesion within or between sentences is faulty or mechanical; paragraphs not always
  logical.
- 5: some organisation but not always logical; linking words inadequate, inaccurate or overused;
  repetitive because references and substitution are lacking; paragraphs may be missing or
  inadequate.
- 4: information and ideas not arranged coherently; basic linking words, often inaccurate or
  repeated; may not write in paragraphs.
- 3: no logical organisation; very few or wrong linking words.
Lexical Resource: call it lexical_resource
- 9: a wide range used with full flexibility and precision; rare minor slips only.
- 8: a wide range used fluently and flexibly to convey precise meanings; less common words used
  skilfully, with occasional errors in word choice or collocation; rare spelling errors.
- 7: enough range for some flexibility and precision; less common words with some awareness of
  style and collocation; occasional errors in word choice, spelling or word formation.
- 6: an adequate range for the task; tries less common words, with some inaccuracy; some spelling
  or word formation errors, which do not stop communication.
- 5: a limited range, minimally adequate for the task; noticeable errors in spelling or word
  formation that may cause the reader some difficulty.
- 4: only basic vocabulary, used repetitively or wrongly for the task; limited control of word
  formation and spelling; errors may strain the reader.
- 3: a very limited range of words and expressions with very limited control of word formation
  and spelling; errors may severely distort the message.
Grammatical Range and Accuracy: call it grammar
- 9: a wide range of structures with full flexibility and accuracy; rare minor slips only.
- 8: a wide range of structures; the majority of sentences error-free; only very occasional errors
  or inappropriate forms.
- 7: a variety of complex structures; frequent error-free sentences; good control of grammar and
  punctuation, with a few errors.
- 6: a mix of simple and complex sentence forms; some errors in grammar and punctuation, which
  rarely reduce communication.
- 5: only a limited range of structures; complex sentences tried but less accurate than simple
  ones; frequent grammar errors, and punctuation may be faulty; errors can cause some difficulty
  for the reader.
- 4: a very limited range of structures, rare subordinate clauses; some accurate structures but
  errors predominate, and punctuation is often faulty.
- 3: tries sentence forms, but errors predominate and distort the meaning."""
PROMPT = """You are an experienced IELTS Writing examiner. Estimate the candidate's bands for the four
criteria from the task, the candidate's answer and the measured numbers. Be fair: neither generous
nor harsh. Pick the band whose description fits best, and judge each criterion on its own (they
often differ by half a band or more).
{register}
{task}
{common}

Rules:
- The answer was typed by the candidate. Judge only what is written.
- Never judge or mention the length or the word count: it is counted and handled separately,
  so an answer that seems short must not lose any band for it.{scanned}
- Bands: judge the whole answer against the descriptions. Never take a fixed amount off for each
  correction, and never raise or lower a band because of the number of style suggestions.
- evidence: up to 3 short quotes of the candidate's own words that justify the band (or, for
  Task Achievement / Response, which bullet point or part of the question is covered or missed).
- summary: one or two sentences, addressed to the candidate ("You ...").
- corrections: the most important points, up to 15, in the order they appear; each only once.
  kind, one of:
    G  grammar: the words break a rule of English grammar or punctuation. Before you choose G,
       name the rule to yourself; if you cannot, it is not G.
    T  spelling: a spelling or typing mistake.
    P  precision: the words are unclear, exaggerated, inconsistent with the rest, or say
       something the writer cannot mean.
    S  style: the words are correct English but could be more natural or effective. Optional:
       at most 3 in all, only where the gain is clear, and none at all is a good answer. Never
       suggest wording more formal than the register needs, and never add words only to pad.
    TA task: something the task asks for is missing, too thin, or answered wrongly.
  A preference of style is never G: if the words are grammatical but you would put them
  differently, it is S, or nothing at all. If your reason would be "more natural", "more formal",
  "more polite" or "more common", it is not G.
  original: the candidate's words copied exactly, as short as possible but long enough to find
  (2 to 8 words, never a whole sentence); for TA with nothing to quote, leave it empty.
  better: the smallest change that fixes it, keeping the writer's meaning and voice (for TA:
  what to add or change). why: for G, T and P, why it is wrong; for S, what the change gains.
- Leave alone what is right for the register: {keep}
- strengths: up to 3 specific things the candidate does well.
- priorities: up to 3 concrete practice actions for the next answer, most important first."""

# Task 1: the register comes first, and decides what counts as appropriate.
LETTER_REGISTER = """
First decide the register this letter needs, from who it is written to (register):
- reader: who the letter is to, in a few words ("a friend", "a landlord", "a company's manager").
- required: informal for a friend or a member of the family; semi-formal for someone the writer
  knows but is not close to, or works with (a neighbour, a colleague, a landlord, a teacher);
  formal for an organisation, an official, or someone the writer does not know.
- used: the register the candidate actually wrote in.
Judge the tone against the required register, not against formal or academic English. In an
informal letter, conversational English is the right English: do not prefer formal words or
sentence forms, and do not lower Lexical Resource or Grammar for contractions, phrasal verbs or
everyday expressions. A letter that is more formal than its reader calls for has the wrong
tone, just as one that is too casual has. The tone belongs to Task Achievement.
The usual openings and endings are right and need no change: "Dear Mr Hughes," with "Yours
sincerely,"; "Dear Sir or Madam," with "Yours faithfully,"; a first name with "Best wishes,",
"See you soon," or the like.
"""
ESSAY_REGISTER = """
An essay is written in a neutral to formal register.
"""
# What must not be "corrected", by the register the task needs.
KEEP = {
    "letter": "decide by the register you found. In an informal letter, natural conversational English is right: "
              'contractions ("I\'m", "don\'t"), phrasal verbs ("catch up", "pop round"), informal linking ("by the '
              'way", "anyway"), friendly offers and questions ("how about a beer?"), everyday wording ("spent five '
              'years getting a degree"), and anything said on purpose for effect; none of these is an error or a '
              "suggestion. In a semi-formal letter, polite everyday English with contractions is right. In a formal "
              "letter, an informal expression is S (the tone), never G.",
    "essay": "correct sentences you would merely write differently, and anything said on purpose for effect. An "
             "informal expression in an essay is S (the tone), never G.",
}

SCANNED = """
- The answer was scanned from a printed book and the scan has slips: letters read wrongly
  ("imporkant"), dots or spaces inside words ("i.ts", "the re"), broken lines. Ignore them: they
  are not the candidate's errors, so never count them as spelling errors or correct them."""

LABELS = {
    "paragraphs": "paragraphs",
    "sentences": "sentences",
    "words_per_sentence": "average words per sentence",
    "vocabulary_variety": "share of different words in each 40-word stretch, 0 to 1 (higher means more varied)",
    "not_in_dictionary": "words not in our dictionary (possible misspellings, or rare words)",
}
NAMES = {
    "task_response": {1: "Task Achievement", 2: "Task Response"},
    "coherence_cohesion": "Coherence and Cohesion",
    "lexical_resource": "Lexical Resource",
    "grammar": "Grammatical Range and Accuracy",
}


def measure(answer: str, task: dict) -> dict:
    words = word_count(answer)
    paragraphs = [p for p in re.split(r"\n\s*\n|\n(?=\s{2,})", answer.strip()) if p.strip()]
    if len(paragraphs) == 1 and answer.count("\n") >= 2:  # one line per paragraph, no blank lines
        paragraphs = [p for p in answer.splitlines() if p.strip()]
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", answer.strip()) if word_count(s)]
    tokens = re.findall(r"[a-z']+", answer.lower())
    unknown = unknown_words(answer)
    return {
        "words": words,
        "minimum": task["words"],
        "paragraphs": len(paragraphs),
        "sentences": len(sentences),
        "words_per_sentence": round(words / len(sentences), 1) if sentences else None,
        "vocabulary_variety": round(moving_type_token_ratio(tokens), 2) if tokens else None,
        "not_in_dictionary": len(unknown),
        "unknown_words": unknown[:20],
    }


def length_penalty(words: int, minimum: int) -> float:
    """Bands taken off Task Achievement / Response for an answer under the minimum. IELTS
    penalises short answers without publishing how much; this is our guess, to be checked
    against the books' sample answers: half a band if up to 10% short, one band
    if up to a third short, two bands if shorter."""
    if words >= minimum:
        return 0.0
    short = 1 - words / minimum
    return 0.5 if short <= 0.1 else 1.0 if short <= 1 / 3 else 2.0


def find(original: str, answer: str) -> tuple[int, int] | None:
    """Where the corrected words are in the answer (ignoring case and spacing), or None."""
    words = original.split()
    if not words:
        return None
    pattern = r"\s+".join(re.escape(w) for w in words)
    match = re.search(pattern, answer, re.I)
    return match.span() if match else None


CONTRACTIONS = {"n't": " not", "'m": " am", "'re": " are", "'ve": " have", "'ll": " will", "'d": " would",
                "'s": " is"}


def _uncontracted(text: str) -> str:
    """"I'm" as "i am", for telling a correction that only spells a contraction out."""
    text = normalise(text).lower().replace("’", "'").replace("can't", "cannot").replace("won't", "will not")
    for short, long in CONTRACTIONS.items():
        text = text.replace(short, long)
    return re.sub(r"[^a-z ]", "", text)


def keep_corrections(corrections: list[dict], answer: str, register: str | None = None) -> list[dict]:
    """The LLM's corrections that can be shown in the answer, in order: the corrected words must
    be in it, at most MAX_CORRECTED words long (not a whole sentence rewritten), and really changed.
    Of corrections that overlap, the shortest is kept (the LLM sometimes repeats one, or rewrites
    a sentence and also corrects one error in it). In a letter that is not formal, one that only
    spells a contraction out ("I'm" → "I am") is dropped: the contraction is right there."""
    found = []
    for c in corrections:
        span = find(c["original"], answer)
        if not (span and word_count(c["original"]) <= MAX_CORRECTED
                and normalise(c["better"]) != normalise(c["original"])):
            continue
        if register in ("informal", "semi-formal") and _uncontracted(c["better"]) == _uncontracted(c["original"]) \
                and c["better"].count("'") + c["better"].count("’") < c["original"].count("'") + c["original"].count("’"):
            continue
        found.append({**c, "original": answer[span[0]:span[1]], "start": span[0], "end": span[1]})
    kept = []
    for c in sorted(found, key=lambda c: c["end"] - c["start"]):  # shortest first
        if all(c["end"] <= k["start"] or c["start"] >= k["end"] for k in kept):
            kept.append(c)
    return sorted(kept, key=lambda c: c["start"])


def sort_out(judged: list[dict], answer: str, register: str | None = None) -> dict[str, list[dict]]:
    """The LLM's corrections, each named by its kind (KINDS) and put where it is shown:

    - "corrections": the errors (grammar, spelling, precision), with where they are in the answer
      ("start", "end"), to be marked there;
    - "suggestions": style, optional, with their place too but never marked as errors (the first
      MAX_SUGGESTIONS); a "grammar error" whose reason is a preference ("more natural") is one;
    - "task_notes": what the task asks for and the answer lacks ("original" may be empty)."""
    named = []
    for c in judged:
        if c.get("kind") not in KINDS:
            continue
        kind = "S" if c["kind"] == "G" and PREFERENCE.search(c["why"]) else c["kind"]
        named.append({**c, "kind": kind, "category": KINDS[kind]})
    placed = keep_corrections([c for c in named if c["kind"] != "TA"], answer, register)
    notes = [{k: c[k] for k in ("kind", "category", "original", "better", "why")}
             for c in named if c["kind"] == "TA" and (c["better"].strip() or c["why"].strip())]
    return {"corrections": [c for c in placed if c["kind"] in ERRORS],
            "suggestions": [c for c in placed if c["kind"] == "S"][:MAX_SUGGESTIONS],
            "task_notes": notes}


def normalise(text: str) -> str:
    """Spacing evened out; case kept ("i think" → "I think" is a correction)."""
    return " ".join(text.split())


def corrected(llm_bands: dict[str, float], words: int, minimum: int, shift: float = SHIFT) -> dict[str, float]:
    """The criterion bands from the LLM's: shifted, then Task Achievement / Response loses the
    length penalty; kept between 1 and 9, not yet rounded."""
    penalty = length_penalty(words, minimum)
    return {key: min(9.0, max(1.0, band + shift - (penalty if key == "task_response" else 0.0)))
            for key, band in llm_bands.items()}


def task_band(bands: dict[str, float]) -> float:
    """A task's band: the average of its four criteria, rounded like IELTS."""
    return round_band(sum(bands.values()) / len(bands))


async def judge(task: dict, answer: str, scanned: bool = False) -> tuple[dict, dict]:
    """The measured numbers and the LLM's judgement (its bands uncorrected)."""
    stats = measure(answer, task)
    numbers = "\n".join(f"- {label}: {stats[key]}" for key, label in LABELS.items() if stats[key] is not None)
    if stats["unknown_words"]:
        numbers += f"\n- the words not in our dictionary: {', '.join(stats['unknown_words'])}"
    letter = task["task"] == 1
    messages = [
        {"role": "system", "content": PROMPT.format(
            task=LETTER_TASK if letter else ESSAY_TASK, common=COMMON, scanned=SCANNED if scanned else "",
            register=LETTER_REGISTER if letter else ESSAY_REGISTER, keep=KEEP["letter" if letter else "essay"])},
        {"role": "user", "content": f"The task:\n{as_text(task, minimum=False)}\n\nMeasured numbers:\n{numbers}\n\n"
                                    f"The candidate's answer:\n{answer}"},
    ]
    schema = LETTER_SCHEMA if letter else SCHEMA
    return stats, await llm.complete_json(messages, schema, temperature=0.2, max_tokens=3500)


async def assess(task: dict, answer: str, scanned: bool = False) -> dict:
    """One task's assessment: its criteria with bands, the corrections, strengths and priorities.
    scanned: the answer is a sample answer from a book (for checking the bands), with scan slips."""
    stats, judged = await judge(task, answer, scanned)
    register = judged.get("register")  # a letter's: who it is to, the register needed and the one used
    sorted_out = sort_out(judged["corrections"], answer, register and register["required"])
    penalty = length_penalty(stats["words"], task["words"])
    bands = corrected({key: judged[key]["band"] for key in CRITERIA}, stats["words"], task["words"])
    criteria = []
    for key in CRITERIA:
        c = judged[key]
        name = NAMES[key][task["task"]] if key == "task_response" else NAMES[key]
        evidence = c["evidence"]
        if key == "task_response" and penalty:
            evidence = [f"{stats['words']} words, under the minimum of {task['words']}: "
                        f"{penalty:g} band{'s' if penalty > 1 else ''} off."] + evidence
        criteria.append({"id": key, "name": name, "evidence": evidence, "summary": c["summary"],
                         "llm_band": c["band"], "band": bands[key]})
    return {
        "task": task["task"],
        "stats": stats,
        "length_penalty": penalty,
        "criteria": criteria,
        "band": task_band(bands),
        "register": register,
        **sorted_out,
        "strengths": judged["strengths"],
        "priorities": judged["priorities"],
    }


def writing_band(task_bands: dict[int, float]) -> float:
    """Task 2 counts twice when both tasks are done."""
    if 1 in task_bands and 2 in task_bands:
        return round_band((task_bands[1] + 2 * task_bands[2]) / 3)
    return next(iter(task_bands.values()))


def unanswered(task: dict, words: int) -> dict:
    """A test task with 20 words or fewer: IELTS gives band 0 to no answer and band 1 to 20 words
    or fewer, without reading it further."""
    band = 0.0 if words == 0 else 1.0
    summary = ("You did not answer this task." if words == 0 else
               f"{words} words: an answer of 20 words or fewer gets band 1.")
    criteria = [{"id": key, "name": NAMES[key][task["task"]] if key == "task_response" else NAMES[key],
                 "evidence": [], "summary": summary, "band": band} for key in CRITERIA]
    return {"task": task["task"], "stats": {"words": words, "minimum": task["words"]}, "length_penalty": 0.0,
            "criteria": criteria, "band": band, "register": None, "corrections": [], "suggestions": [], "task_notes": [],
            "strengths": [], "priorities": []}


async def build(session: dict) -> dict:
    """The report of a Writing session: each answer's assessment, and the writing band.

    Practice (one task): an answer under MIN_WORDS gets corrections but no band. The full test
    (mode "test"): every task counts, as in IELTS; 20 words or fewer is band 1, none is band 0."""
    session = test.finish_if_needed(session)
    full_test = session["mode"] == "test"
    answers = [m for m in session["messages"] if m["role"] == "candidate"]
    tasks, short = [], []
    for m in answers:
        task = m["delivery"]["task"]
        words = word_count(m["text"])
        if full_test and words <= UNANSWERED_WORDS:
            tasks.append(unanswered(task, words))
            continue
        if not full_test and words < MIN_WORDS:
            short.append(task["task"])
        tasks.append(await assess(task, m["text"]))
    scored = [t for t in tasks if t["task"] not in short]
    report = {"tasks": tasks, "enough": bool(scored)}
    if not scored:
        report["note"] = (f"Write at least {MIN_WORDS} words for a band estimate. Your corrections are below.")
        return report
    bands = {t["task"]: t["band"] for t in scored}
    if len(scored) == 1:
        criteria = scored[0]["criteria"]
    else:  # both tasks: each criterion with Task 2 counted twice
        by_task = {t["task"]: {c["id"]: c for c in t["criteria"]} for t in scored}
        criteria = [{**by_task[2][c["id"]],
                     "name": "Task Achievement / Response" if c["id"] == "task_response" else c["name"],
                     "summary": " ".join(f"Task {n}: {by_task[n][c['id']]['summary']}" for n in (1, 2)),
                     "evidence": [e for n in (1, 2) for e in by_task[n][c["id"]]["evidence"][:2]],
                     "band": writing_band({n: by_task[n][c["id"]]["band"] for n in by_task})}
                    for c in by_task[2].values()]
    report.update(
        criteria=[{**c, "band": round_band(c["band"])} for c in criteria],
        overall=writing_band(bands),
        strengths=[s for t in scored for s in t["strengths"]][:3],
        priorities=[p for t in scored for p in t["priorities"]][:3],
    )
    if short:
        report["note"] = f"Task {short[0]} has under {MIN_WORDS} words, so only the other task is in the band."
    elif full_test:
        report["note"] = (f"Task 1 band {formatted(bands[1])}, Task 2 band {formatted(bands[2])}: "
                          f"the writing band counts Task 2 twice.")
    return report


def formatted(band: float) -> str:
    return f"{band:g}"

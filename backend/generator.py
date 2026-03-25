"""
backend/generator.py
--------------------
Retrieves relevant chunks from a document's ChromaDB collection,
then calls the Groq API to generate flashcards and quiz questions.

Prompts are subject-agnostic — they work for any PDF content.
Retrieval is always scoped to the specific document_id uploaded.

Shuffle & dedup:
  - Temperature is randomised per call (0.55–0.95) so the model
    never produces the same set twice.
  - A per-(document_id, topic) set of previously seen question
    fingerprints is kept in module-level memory so repeated
    Generate clicks within a server session won't surface
    identical questions.
"""

import json
import random
import hashlib
from tenacity import retry, stop_after_attempt, wait_exponential

from groq import Groq

from backend.config import get_settings
from backend.ingest import query_chroma
from backend.models import FlashcardSchema, QuizQuestion, MCQOption

settings = get_settings()
client   = Groq(api_key=settings.groq_api_key)

# ── In-memory dedup store (cleared on server restart) ────────────────────────
# Maps  (document_id, topic_lower) -> set of question fingerprints (str)
_seen_questions: dict[tuple, set] = {}


def _fingerprint(text: str) -> str:
    """Stable 8-char fingerprint of a question string."""
    return hashlib.md5(text.strip().lower().encode()).hexdigest()[:8]


def _random_temperature() -> float:
    """Returns a temperature in [0.55, 0.95] so each call feels fresh."""
    return round(random.uniform(0.55, 0.95), 2)


# ── Prompt templates (subject-agnostic) ──────────────────────────────────────

FLASHCARD_PROMPT = """\
You are an expert tutor. Based ONLY on the context below, generate exactly {num_cards} flashcards.

Context:
{context}

Rules:
- Each flashcard must be directly answerable from the context
- Vary difficulty: mix easy, medium, and hard cards
- Keep answers concise (1-3 sentences)
- Do NOT repeat any of these already-used questions: {used_qs}
- Return ONLY valid JSON — no preamble, no markdown fences

Required JSON format:
[
  {{
    "question": "...",
    "answer": "...",
    "difficulty": "easy" | "medium" | "hard",
    "topic": "short topic label (2-4 words)",
    "source_page": <page number as integer>
  }}
]
"""

MCQ_PROMPT = """\
You are an expert tutor. Based ONLY on the context below, generate exactly {num_quiz} multiple-choice questions.

Context:
{context}

Rules:
- 4 options per question labeled A, B, C, D
- Exactly one correct answer per question
- Make distractors plausible, not obviously wrong
- Do NOT repeat any of these already-used questions: {used_qs}
- Return ONLY valid JSON — no preamble, no markdown fences

Required JSON format:
[
  {{
    "question": "...",
    "quiz_type": "mcq",
    "options": [
      {{"label": "A", "text": "...", "is_correct": false}},
      {{"label": "B", "text": "...", "is_correct": true}},
      {{"label": "C", "text": "...", "is_correct": false}},
      {{"label": "D", "text": "...", "is_correct": false}}
    ],
    "answer": "B",
    "explanation": "brief explanation of why B is correct",
    "source_page": <integer>
  }}
]
"""

TRUEFALSE_PROMPT = """\
Based ONLY on the context below, generate exactly {num_quiz} true/false questions.

Context:
{context}

Rules:
- Do NOT repeat any of these already-used questions: {used_qs}

Return ONLY valid JSON:
[
  {{
    "question": "...",
    "quiz_type": "truefalse",
    "options": [
      {{"label": "True",  "text": "True",  "is_correct": true}},
      {{"label": "False", "text": "False", "is_correct": false}}
    ],
    "answer": "True",
    "explanation": "...",
    "source_page": <integer>
  }}
]
"""

SHORT_PROMPT = """\
Based ONLY on the context below, generate exactly {num_quiz} short-answer questions.

Context:
{context}

Rules:
- Do NOT repeat any of these already-used questions: {used_qs}

Return ONLY valid JSON:
[
  {{
    "question": "...",
    "quiz_type": "short",
    "answer": "...",
    "explanation": "...",
    "source_page": <integer>
  }}
]
"""

QUIZ_PROMPTS = {
    "mcq":       MCQ_PROMPT,
    "truefalse": TRUEFALSE_PROMPT,
    "short":     SHORT_PROMPT,
}


# ── Groq call with retry ──────────────────────────────────────────────────────

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _call_groq(prompt: str, temperature: float = 0.7) -> str:
    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=4096,
    )
    return response.choices[0].message.content.strip()


def _parse_json_safe(raw: str, label: str) -> list:
    """Strips accidental markdown fences and parses JSON."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[generator] JSON parse failed for {label}: {e}")
        return []


# ── Context builder — scoped to document_id ──────────────────────────────────

def _build_context(topic: str, document_id: str, n_chunks: int = 6) -> str:
    """
    Retrieves the most relevant chunks from this document's collection only.
    Never leaks content across different uploaded documents.
    """
    hits  = query_chroma(topic, document_id=document_id, n_results=n_chunks)
    parts = [f"[Page {h['page']}]\n{h['text']}" for h in hits]
    return "\n\n---\n\n".join(parts)


def _get_used_summary(document_id: str, topic: str) -> str:
    """Returns a compact human-readable list of already-used question stems."""
    key  = (document_id, topic.strip().lower())
    seen = _seen_questions.get(key, set())
    if not seen:
        return "none"
    # Return just fingerprints — enough for the model to know they exist
    return ", ".join(sorted(seen)[:30])  # cap at 30 to stay within token budget


def _register_questions(document_id: str, topic: str, questions: list[str]) -> None:
    key = (document_id, topic.strip().lower())
    if key not in _seen_questions:
        _seen_questions[key] = set()
    for q in questions:
        _seen_questions[key].add(_fingerprint(q))


# ── Public API ────────────────────────────────────────────────────────────────

def generate_flashcards(
    topic:       str,
    document_id: str,
    num_cards:   int = 10,
) -> list[FlashcardSchema]:
    """
    Generates flashcards grounded in the uploaded document's content.
    Each call uses a fresh random temperature and skips previously
    generated questions, so repeated requests always feel different.
    """
    context  = _build_context(topic, document_id)
    used_qs  = _get_used_summary(document_id, topic)
    temp     = _random_temperature()
    prompt   = FLASHCARD_PROMPT.format(
        num_cards=num_cards,
        context=context,
        used_qs=used_qs,
    )
    raw   = _call_groq(prompt, temperature=temp)
    items = _parse_json_safe(raw, "flashcards")

    # Shuffle at the Python level too, for extra variety in display order
    random.shuffle(items)

    cards = []
    new_questions = []
    for item in items:
        try:
            card = FlashcardSchema(**item)
            cards.append(card)
            new_questions.append(card.question)
        except Exception as e:
            print(f"[generator] Skipping malformed flashcard: {e}")

    _register_questions(document_id, topic, new_questions)
    return cards


def generate_quiz(
    topic:       str,
    document_id: str,
    num_quiz:    int = 5,
    quiz_type:   str = "mcq",
) -> list[QuizQuestion]:
    """
    Generates quiz questions grounded in the uploaded document's content.
    Each call uses a fresh random temperature and skips previously
    generated questions, so repeated requests always feel different.
    """
    if quiz_type not in QUIZ_PROMPTS:
        raise ValueError(f"quiz_type must be one of {list(QUIZ_PROMPTS.keys())}")

    context = _build_context(topic, document_id)
    used_qs = _get_used_summary(document_id, topic)
    temp    = _random_temperature()
    prompt  = QUIZ_PROMPTS[quiz_type].format(
        num_quiz=num_quiz,
        context=context,
        used_qs=used_qs,
    )
    raw   = _call_groq(prompt, temperature=temp)
    items = _parse_json_safe(raw, "quiz")

    # Shuffle MCQ options and re-sync all labels + answer letter
    labels = ["A", "B", "C", "D"]
    if quiz_type == "mcq":
        for item in items:
            if "options" in item and isinstance(item["options"], list):
                random.shuffle(item["options"])
                for idx, opt in enumerate(item["options"]):
                    opt["label"] = labels[idx]
                    if opt.get("is_correct"):
                        item["answer"] = labels[idx]

    random.shuffle(items)

    questions     = []
    new_questions = []
    for item in items:
        try:
            if "options" in item and item["options"]:
                item["options"] = [MCQOption(**o) for o in item["options"]]
            q = QuizQuestion(**item)
            questions.append(q)
            new_questions.append(q.question)
        except Exception as e:
            print(f"[generator] Skipping malformed question: {e}")

    _register_questions(document_id, topic, new_questions)
    return questions
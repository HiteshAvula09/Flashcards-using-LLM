"""
eval/squad_eval.py
------------------
Evaluates the flashcard generator against the SQuAD v2 dataset.

For each SQuAD passage we:
  1. Feed the passage as context directly to Groq
  2. Compare the generated answer against SQuAD ground-truth answers
  3. Compute Exact Match (EM) and F1 scores

Run:
    python -m eval.squad_eval --squad data/squad/squad_v2.json --n 100

Output:
    eval/results/eval_report.json
"""

import json
import re
import string
import argparse
from pathlib import Path
from datetime import datetime
from collections import Counter

from groq import Groq
from tenacity import retry, stop_after_attempt, wait_exponential

from backend.config import get_settings

settings = get_settings()
client   = Groq(api_key=settings.groq_api_key)

RESULTS_DIR = Path("eval/results")


# ── SQuAD loader ──────────────────────────────────────────────────────────────

def load_squad(path: str, n: int = 100) -> list[dict]:
    """
    Loads up to n answerable QA pairs from SQuAD v2 JSON.
    Skips unanswerable questions (is_impossible=True).
    """
    with open(path, "r") as f:
        data = json.load(f)

    samples = []
    for article in data["data"]:
        for para in article["paragraphs"]:
            context = para["context"]
            for qa in para["qas"]:
                if qa.get("is_impossible", False):
                    continue
                answers = list({a["text"] for a in qa["answers"]})
                if not answers:
                    continue
                samples.append({
                    "question": qa["question"],
                    "context":  context,
                    "answers":  answers,
                })
                if len(samples) >= n:
                    return samples
    return samples


# ── Groq call ─────────────────────────────────────────────────────────────────

EVAL_PROMPT = """\
Answer the question based ONLY on the context below.
Be concise — answer in one sentence or less.

Context: {context}

Question: {question}

Answer:"""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10), reraise=True)
def get_answer(context: str, question: str) -> str:
    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[{
            "role":    "user",
            "content": EVAL_PROMPT.format(context=context[:2000], question=question),
        }],
        temperature=0.0,
        max_tokens=128,
    )
    return response.choices[0].message.content.strip()


# ── Scoring ───────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = re.sub(r"\b(a|an|the)\b", " ", text)
    return " ".join(text.split())


def exact_match(prediction: str, ground_truths: list[str]) -> int:
    pred = _normalize(prediction)
    return int(any(pred == _normalize(gt) for gt in ground_truths))


def f1_score(prediction: str, ground_truths: list[str]) -> float:
    def _f1(pred: str, gt: str) -> float:
        pred_tokens = _normalize(pred).split()
        gt_tokens   = _normalize(gt).split()
        common      = Counter(pred_tokens) & Counter(gt_tokens)
        num_same    = sum(common.values())
        if num_same == 0:
            return 0.0
        precision = num_same / len(pred_tokens)
        recall    = num_same / len(gt_tokens)
        return 2 * precision * recall / (precision + recall)

    return max(_f1(prediction, gt) for gt in ground_truths)


# ── Main eval loop ────────────────────────────────────────────────────────────

def run_eval(squad_path: str, n: int = 100) -> dict:
    samples = load_squad(squad_path, n)
    print(f"[eval] Loaded {len(samples)} SQuAD samples")

    em_scores, f1_scores = [], []
    detailed = []

    for i, sample in enumerate(samples, 1):
        try:
            pred = get_answer(sample["context"], sample["question"])
        except Exception as e:
            print(f"[eval] Sample {i} failed: {e}")
            pred = ""

        em = exact_match(pred, sample["answers"])
        f1 = f1_score(pred, sample["answers"])
        em_scores.append(em)
        f1_scores.append(f1)

        detailed.append({
            "question":   sample["question"],
            "prediction": pred,
            "answers":    sample["answers"],
            "em":         em,
            "f1":         round(f1, 4),
        })

        if i % 10 == 0:
            print(
                f"[eval] {i}/{len(samples)} — "
                f"EM: {sum(em_scores)/len(em_scores):.3f}  "
                f"F1: {sum(f1_scores)/len(f1_scores):.3f}"
            )

    report = {
        "timestamp":   datetime.now().isoformat(),
        "model":       settings.groq_model,
        "num_samples": len(samples),
        "exact_match": round(sum(em_scores) / len(em_scores), 4),
        "f1":          round(sum(f1_scores) / len(f1_scores), 4),
        "samples":     detailed,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "eval_report.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n[eval] Results saved to {out_path}")
    print(f"[eval] Exact Match: {report['exact_match']:.4f}")
    print(f"[eval] F1 Score:    {report['f1']:.4f}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--squad", default="data/squad/squad_v2.json")
    parser.add_argument("--n",     type=int, default=100)
    args = parser.parse_args()
    run_eval(args.squad, args.n)
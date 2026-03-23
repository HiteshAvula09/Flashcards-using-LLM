"""
backend/scheduler.py
--------------------
SM-2 spaced repetition algorithm.

Rating scale:
    0 — complete blackout
    1 — wrong, but answer felt familiar
    2 — wrong, but easy to recall after seeing answer
    3 — correct, but required significant effort
    4 — correct with minor hesitation
    5 — perfect recall, instant
"""

from datetime import date, timedelta
from dataclasses import dataclass


@dataclass
class CardState:
    ease_factor:   float = 2.5
    interval_days: int   = 1
    repetitions:   int   = 0


@dataclass
class CardStateResult:
    ease_factor:   float
    interval_days: int
    repetitions:   int
    next_review:   date


def update_card(state: CardState, rating: int) -> CardStateResult:
    """
    Applies the SM-2 algorithm and returns the updated card state.

    Args:
        state:  Current CardState
        rating: User recall rating 0-5

    Returns:
        CardStateResult with updated fields and next_review date
    """
    if not (0 <= rating <= 5):
        raise ValueError("Rating must be between 0 and 5")

    ef   = state.ease_factor
    reps = state.repetitions
    ivl  = state.interval_days

    if rating < 3:
        # Failed recall — reset, show again in 1 day
        reps = 0
        ivl  = 1
    else:
        if reps == 0:
            ivl = 1
        elif reps == 1:
            ivl = 6
        else:
            ivl = round(ivl * ef)

        reps += 1
        ef = ef + (0.1 - (5 - rating) * (0.08 + (5 - rating) * 0.02))
        ef = max(1.3, ef)

    next_review = date.today() + timedelta(days=ivl)

    return CardStateResult(
        ease_factor   = round(ef, 4),
        interval_days = ivl,
        repetitions   = reps,
        next_review   = next_review,
    )


def get_due_cards(reviews: list[dict]) -> list[dict]:
    """
    Filters a list of card review dicts to those due today or overdue.
    Each dict must have a 'next_review' key (date or ISO string).
    """
    today = date.today()
    due   = []

    for r in reviews:
        nr = r["next_review"]
        if isinstance(nr, str):
            nr = date.fromisoformat(nr)
        if nr <= today:
            due.append(r)

    return due
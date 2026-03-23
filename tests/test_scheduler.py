"""
tests/test_scheduler.py
-----------------------
Unit tests for the SM-2 spaced repetition algorithm.
Run:  pytest tests/test_scheduler.py -v
"""

from datetime import date, timedelta
import pytest
from backend.scheduler import update_card, get_due_cards, CardState


def test_first_correct_review():
    state  = CardState()
    result = update_card(state, rating=4)
    assert result.repetitions   == 1
    assert result.interval_days == 1
    assert result.ease_factor   >= 2.5


def test_second_correct_review():
    state  = CardState(repetitions=1, interval_days=1)
    result = update_card(state, rating=4)
    assert result.repetitions   == 2
    assert result.interval_days == 6


def test_failed_review_resets():
    state  = CardState(repetitions=5, interval_days=20, ease_factor=2.5)
    result = update_card(state, rating=1)
    assert result.repetitions   == 0
    assert result.interval_days == 1


def test_ease_factor_increases_on_easy():
    state  = CardState(ease_factor=2.5)
    result = update_card(state, rating=5)
    assert result.ease_factor > 2.5


def test_ease_factor_decreases_on_hard():
    state  = CardState(ease_factor=2.5)
    result = update_card(state, rating=3)
    assert result.ease_factor < 2.5


def test_ease_factor_floor():
    state  = CardState(ease_factor=1.3)
    result = update_card(state, rating=3)
    assert result.ease_factor >= 1.3


def test_invalid_rating():
    state = CardState()
    with pytest.raises(ValueError):
        update_card(state, rating=6)


def test_next_review_date():
    state  = CardState()
    result = update_card(state, rating=4)
    assert result.next_review == date.today() + timedelta(days=result.interval_days)


def test_get_due_cards_filters_correctly():
    today     = date.today()
    yesterday = (today - timedelta(days=1)).isoformat()
    tomorrow  = (today + timedelta(days=1)).isoformat()

    reviews = [
        {"flashcard_id": "1", "next_review": yesterday},
        {"flashcard_id": "2", "next_review": today.isoformat()},
        {"flashcard_id": "3", "next_review": tomorrow},
    ]

    due     = get_due_cards(reviews)
    due_ids = [d["flashcard_id"] for d in due]

    assert "1" in due_ids
    assert "2" in due_ids
    assert "3" not in due_ids
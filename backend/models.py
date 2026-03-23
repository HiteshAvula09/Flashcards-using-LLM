"""
backend/models.py
-----------------
SQLAlchemy ORM models + Pydantic schemas for API request/response.

Tables:
    users          — registered students
    documents      — uploaded PDFs (any subject)
    flashcards     — generated Q&A pairs
    quiz_sessions  — a single quiz attempt
    card_reviews   — per-card SM-2 spaced repetition state
"""

import uuid
from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    String, Text, Integer, Float,
    ForeignKey, DateTime, Date, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pydantic import BaseModel, Field

from backend.database import Base


# ── ORM Models ────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id:         Mapped[str]      = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username:   Mapped[str]      = mapped_column(String(80), unique=True, nullable=False)
    email:      Mapped[str]      = mapped_column(String(120), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    documents: Mapped[list["Document"]]   = relationship(back_populates="user")
    reviews:   Mapped[list["CardReview"]] = relationship(back_populates="user")


class Document(Base):
    __tablename__ = "documents"

    id:          Mapped[str]      = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id:     Mapped[str]      = mapped_column(ForeignKey("users.id"), nullable=True)
    filename:    Mapped[str]      = mapped_column(String(255), nullable=False)
    title:       Mapped[str]      = mapped_column(String(255), nullable=True)
    page_count:  Mapped[int]      = mapped_column(Integer, default=0)
    chunk_count: Mapped[int]      = mapped_column(Integer, default=0)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user:       Mapped[Optional["User"]]  = relationship(back_populates="documents")
    flashcards: Mapped[list["Flashcard"]] = relationship(back_populates="document")


class Flashcard(Base):
    __tablename__ = "flashcards"

    id:          Mapped[str]      = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str]      = mapped_column(ForeignKey("documents.id"), nullable=False)
    question:    Mapped[str]      = mapped_column(Text, nullable=False)
    answer:      Mapped[str]      = mapped_column(Text, nullable=False)
    difficulty:  Mapped[str]      = mapped_column(String(10), default="medium")
    topic:       Mapped[str]      = mapped_column(String(120), nullable=True)
    source_page: Mapped[int]      = mapped_column(Integer, nullable=True)
    created_at:  Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    document: Mapped["Document"]         = relationship(back_populates="flashcards")
    reviews:  Mapped[list["CardReview"]] = relationship(back_populates="flashcard")


class QuizSession(Base):
    __tablename__ = "quiz_sessions"

    id:          Mapped[str]      = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id:     Mapped[str]      = mapped_column(ForeignKey("users.id"), nullable=True)
    document_id: Mapped[str]      = mapped_column(ForeignKey("documents.id"), nullable=False)
    score:       Mapped[float]    = mapped_column(Float, default=0.0)
    total:       Mapped[int]      = mapped_column(Integer, default=0)
    correct:     Mapped[int]      = mapped_column(Integer, default=0)
    quiz_type:   Mapped[str]      = mapped_column(String(20), default="mcq")
    created_at:  Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CardReview(Base):
    __tablename__ = "card_reviews"

    id:            Mapped[str]      = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id:       Mapped[str]      = mapped_column(ForeignKey("users.id"), nullable=True)
    flashcard_id:  Mapped[str]      = mapped_column(ForeignKey("flashcards.id"), nullable=False)

    # SM-2 fields
    ease_factor:   Mapped[float]    = mapped_column(Float, default=2.5)
    interval_days: Mapped[int]      = mapped_column(Integer, default=1)
    repetitions:   Mapped[int]      = mapped_column(Integer, default=0)
    next_review:   Mapped[date]     = mapped_column(Date, default=date.today)
    last_rating:   Mapped[int]      = mapped_column(Integer, nullable=True)
    last_reviewed: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    user:      Mapped[Optional["User"]]  = relationship(back_populates="reviews")
    flashcard: Mapped["Flashcard"]       = relationship(back_populates="reviews")


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class FlashcardSchema(BaseModel):
    question:    str
    answer:      str
    difficulty:  str = "medium"
    topic:       Optional[str] = None
    source_page: Optional[int] = None

    model_config = {"from_attributes": True}


class MCQOption(BaseModel):
    label:      str
    text:       str
    is_correct: bool


class QuizQuestion(BaseModel):
    question:    str
    quiz_type:   str
    options:     Optional[list[MCQOption]] = None
    answer:      str
    explanation: Optional[str] = None
    source_page: Optional[int] = None


class GenerateRequest(BaseModel):
    topic:       str  = Field(..., description="Topic to generate from")
    document_id: str  = Field(..., description="UUID of the ingested document")
    num_cards:   int  = Field(default=10, ge=1, le=30)
    num_quiz:    int  = Field(default=5,  ge=1, le=20)
    quiz_type:   str  = Field(default="mcq")


class GenerateResponse(BaseModel):
    flashcards:  list[FlashcardSchema]
    quiz:        list[QuizQuestion]
    document_id: str


class ReviewRating(BaseModel):
    flashcard_id: str
    user_id:      str
    rating:       int = Field(..., ge=0, le=5)
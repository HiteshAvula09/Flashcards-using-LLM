"""
backend/main.py
---------------
FastAPI application — all routes.

Start:
    uvicorn backend.main:app --reload --port 8000

Endpoints:
    POST   /ingest               — upload any PDF, ingest into ChromaDB
    POST   /generate             — generate flashcards + quiz via Groq
    GET    /documents            — list all uploaded documents
    GET    /review/{user_id}     — get cards due for review today
    POST   /review/submit        — submit SM-2 rating for a card
    POST   /quiz/submit          — save a completed quiz session
    GET    /cards/{document_id}  — list all flashcards for a document
    GET    /health               — health check
"""

import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database import get_db, create_tables
from backend.models import (
    Document, Flashcard, CardReview, QuizSession,
    GenerateRequest, GenerateResponse, ReviewRating,
)
from backend.ingest import ingest, list_documents
from backend.generator import generate_flashcards, generate_quiz
from backend.scheduler import update_card, get_due_cards, CardState

settings = get_settings()

app = FastAPI(
    title="Flashcard AI",
    description="AI-powered flashcard and quiz generator — works with any PDF",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    create_tables()


#Health

@app.get("/health")
def health():
    return {"status": "ok", "env": settings.app_env}


#Ingest

@app.post("/ingest")
async def ingest_pdf(
    user_id: str        = Form(default="anonymous"),
    file:    UploadFile = File(...),
    db:      Session    = Depends(get_db),
):
    """Upload any PDF and ingest it into ChromaDB + record in PostgreSQL."""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        result = ingest(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    doc = Document(
        id          = result["document_id"],
        user_id     = user_id if user_id != "anonymous" else None,
        filename    = file.filename,
        page_count  = result["page_count"],
        chunk_count = result["chunk_count"],
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return {
        "document_id": doc.id,
        "filename":    doc.filename,
        "page_count":  doc.page_count,
        "chunk_count": doc.chunk_count,
        "source":      result["source"],
    }


#Documents

@app.get("/documents")
def get_documents(db: Session = Depends(get_db)):
    """Lists all uploaded documents — used by the UI dropdown."""
    docs = db.query(Document).order_by(Document.ingested_at.desc()).all()
    return {
        "count": len(docs),
        "documents": [
            {
                "id":          d.id,
                "filename":    d.filename,
                "page_count":  d.page_count,
                "chunk_count": d.chunk_count,
                "ingested_at": d.ingested_at.isoformat(),
            }
            for d in docs
        ],
    }


#Generate

@app.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest, db: Session = Depends(get_db)):
    """Generate flashcards and a quiz for a given topic + document."""
    doc = db.get(Document, req.document_id)
    if not doc:
        raise HTTPException(404, f"Document '{req.document_id}' not found.")

    cards     = generate_flashcards(req.topic, req.document_id, req.num_cards)
    questions = generate_quiz(req.topic, req.document_id, req.num_quiz, req.quiz_type)

    for card in cards:
        fc = Flashcard(
            document_id = req.document_id,
            question    = card.question,
            answer      = card.answer,
            difficulty  = card.difficulty,
            topic       = card.topic,
            source_page = card.source_page,
        )
        db.add(fc)

    db.commit()

    return GenerateResponse(
        flashcards  = cards,
        quiz        = questions,
        document_id = req.document_id,
    )


#Review

@app.get("/review/{user_id}")
def get_review_cards(user_id: str, db: Session = Depends(get_db)):
    """Returns all flashcards due for review today for a user."""
    reviews = (
        db.query(CardReview)
        .filter(CardReview.user_id == user_id)
        .all()
    )

    review_dicts = [
        {
            "flashcard_id":  r.flashcard_id,
            "next_review":   r.next_review,
            "ease_factor":   r.ease_factor,
            "interval_days": r.interval_days,
            "repetitions":   r.repetitions,
        }
        for r in reviews
    ]

    due     = get_due_cards(review_dicts)
    due_ids = [d["flashcard_id"] for d in due]
    cards   = db.query(Flashcard).filter(Flashcard.id.in_(due_ids)).all()

    return {
        "user_id":   user_id,
        "due_count": len(cards),
        "cards": [
            {
                "id":         c.id,
                "question":   c.question,
                "answer":     c.answer,
                "difficulty": c.difficulty,
                "topic":      c.topic,
            }
            for c in cards
        ],
    }


@app.post("/review/submit")
def submit_review(rating: ReviewRating, db: Session = Depends(get_db)):
    """Submit a recall rating for one card — updates SM-2 state."""
    review = (
        db.query(CardReview)
        .filter(
            CardReview.user_id      == rating.user_id,
            CardReview.flashcard_id == rating.flashcard_id,
        )
        .first()
    )

    state = CardState(
        ease_factor   = review.ease_factor   if review else 2.5,
        interval_days = review.interval_days if review else 1,
        repetitions   = review.repetitions   if review else 0,
    )

    result = update_card(state, rating.rating)

    if review:
        review.ease_factor   = result.ease_factor
        review.interval_days = result.interval_days
        review.repetitions   = result.repetitions
        review.next_review   = result.next_review
        review.last_rating   = rating.rating
    else:
        review = CardReview(
            user_id       = rating.user_id,
            flashcard_id  = rating.flashcard_id,
            ease_factor   = result.ease_factor,
            interval_days = result.interval_days,
            repetitions   = result.repetitions,
            next_review   = result.next_review,
            last_rating   = rating.rating,
        )
        db.add(review)

    db.commit()

    return {
        "flashcard_id":  rating.flashcard_id,
        "next_review":   result.next_review.isoformat(),
        "interval_days": result.interval_days,
        "ease_factor":   result.ease_factor,
    }


#Quiz

@app.post("/quiz/submit")
def submit_quiz(
    user_id:     str   = Form(default="anonymous"),
    document_id: str   = Form(...),
    score:       float = Form(...),
    total:       int   = Form(...),
    correct:     int   = Form(...),
    quiz_type:   str   = Form(default="mcq"),
    db: Session = Depends(get_db),
):
    """Save a completed quiz session."""
    session = QuizSession(
        user_id     = user_id if user_id != "anonymous" else None,
        document_id = document_id,
        score       = score,
        total       = total,
        correct     = correct,
        quiz_type   = quiz_type,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"session_id": session.id, "score": score}


#Cards list

@app.get("/cards/{document_id}")
def list_cards(document_id: str, db: Session = Depends(get_db)):
    """List all flashcards saved for a document."""
    cards = db.query(Flashcard).filter(Flashcard.document_id == document_id).all()
    return {
        "document_id": document_id,
        "count":       len(cards),
        "cards": [
            {
                "id":         c.id,
                "question":   c.question,
                "answer":     c.answer,
                "difficulty": c.difficulty,
                "topic":      c.topic,
            }
            for c in cards
        ],
    }
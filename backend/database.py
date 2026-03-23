"""
backend/database.py
-------------------
SQLAlchemy engine, session factory, and Base for all ORM models.
Also contains create_tables() called on app startup.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from backend.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency — yields a DB session, always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    """Creates all tables if they don't exist. Safe to call multiple times."""
    from backend.models import User, Document, Flashcard, QuizSession, CardReview  # noqa: F401
    Base.metadata.create_all(bind=engine)
    print("[db] Tables created / verified.")
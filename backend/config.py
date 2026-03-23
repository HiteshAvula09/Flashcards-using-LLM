"""
backend/config.py
-----------------
Single source of truth for all configuration.
Reads from .env via pydantic-settings — never hardcode credentials.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # Groq
    groq_api_key: str
    groq_model: str = "llama-3.3-70b-versatile"

    # PostgreSQL
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "localhost"
    postgres_port: int = 5433

    # ChromaDB
    # No fixed collection name — each uploaded PDF gets its own
    # collection named after its document_id (set at ingest time)
    chroma_path: str = "data/chroma_db"

    # Embedding
    embed_model: str = "all-MiniLM-L6-v2"

    # Chunking
    chunk_size: int = 500
    chunk_overlap: int = 50

    # App
    app_env: str = "development"
    secret_key: str = "changeme"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:"
            f"{self.postgres_password}@{self.postgres_host}:"
            f"{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    """Cached — only reads .env once per process."""
    return Settings()
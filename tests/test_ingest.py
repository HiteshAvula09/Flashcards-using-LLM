"""
tests/test_ingest.py
--------------------
Unit tests for PDF parsing and chunking logic.
Run:  pytest tests/test_ingest.py -v
"""

from backend.ingest import _clean_text, chunk_pages


def test_clean_text_removes_hyphen_breaks():
    raw    = "photo-\nsynthesis is important"
    result = _clean_text(raw)
    assert "photosynthesis" in result


def test_clean_text_collapses_blank_lines():
    raw    = "line one\n\n\n\nline two"
    result = _clean_text(raw)
    assert "\n\n\n" not in result


def test_chunk_pages_basic():
    pages = [
        {
            "page":   1,
            "text":   "This is a test sentence for chunking purposes. " * 30,
            "source": "test.pdf",
        }
    ]
    chunks = chunk_pages(pages)
    assert len(chunks) >= 1
    for c in chunks:
        assert "chunk_id" in c
        assert "text"     in c
        assert "page"     in c
        assert len(c["text"]) > 0


def test_chunk_ids_are_unique():
    pages = [
        {"page": 1, "text": "First page content. " * 50, "source": "test.pdf"},
        {"page": 2, "text": "Second page content. " * 50, "source": "test.pdf"},
    ]
    chunks = chunk_pages(pages)
    ids    = [c["chunk_id"] for c in chunks]
    assert len(ids) == len(set(ids)), "Chunk IDs are not unique"


def test_chunk_metadata_preserved():
    pages = [{"page": 42, "text": "Some content here. " * 40, "source": "doc.pdf"}]
    chunks = chunk_pages(pages)
    for c in chunks:
        assert c["page"]   == 42
        assert c["source"] == "doc.pdf"
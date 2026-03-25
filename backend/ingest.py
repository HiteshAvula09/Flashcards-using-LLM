"""
backend/ingest.py
-----------------
Step 1 of the pipeline: PDF → chunks → embeddings → ChromaDB.

Each uploaded PDF gets its own ChromaDB collection named after
its document_id — works with any PDF on any subject.

Run standalone:
    python -m backend.ingest --pdf data/raw/yourfile.pdf
"""

import os
import re
import uuid
import argparse
from pathlib import Path

import fitz                                              # PyMuPDF
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings as ChromaSettings

from backend.config import get_settings

settings = get_settings()


#Step 1: Extract raw text per page

def extract_pages(pdf_path: str) -> list[dict]:
    """
    Opens any PDF and returns a list of page dicts.
    Works regardless of subject — any textbook, notes, or paper.
    """
    doc   = fitz.open(pdf_path)
    pages = []

    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text")
        text = _clean_text(text)
        if len(text.strip()) < 100:
            continue
        pages.append({
            "page":   page_num,
            "text":   text,
            "source": Path(pdf_path).name,
        })

    doc.close()
    print(f"[ingest] Extracted {len(pages)} non-empty pages from '{Path(pdf_path).name}'")
    return pages


def _clean_text(text: str) -> str:
    text = re.sub(r"-\n", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


#Step 2: Chunk with LangChain

def chunk_pages(pages: list[dict]) -> list[dict]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )

    chunks = []
    for page in pages:
        for i, split in enumerate(splitter.split_text(page["text"])):
            chunks.append({
                "chunk_id": f"page{page['page']}_chunk{i}",
                "text":     split.strip(),
                "page":     page["page"],
                "source":   page["source"],
            })

    avg = sum(len(c["text"]) for c in chunks) // max(len(chunks), 1)
    print(f"[ingest] Created {len(chunks)} chunks (avg {avg} chars each)")
    return chunks


#Step 3: Embed

def embed_chunks(chunks: list[dict]):
    model  = SentenceTransformer(settings.embed_model)
    texts  = [c["text"] for c in chunks]
    print(f"[ingest] Embedding {len(texts)} chunks with '{settings.embed_model}'...")

    vectors = model.encode(
        texts,
        batch_size=64,
        show_progress_bar=True,
        convert_to_numpy=True,
    )

    ids        = [c["chunk_id"] for c in chunks]
    embeddings = vectors.tolist()
    metadatas  = [
        {"page": c["page"], "source": c["source"], "text": c["text"]}
        for c in chunks
    ]
    return ids, embeddings, metadatas


#Step 4: Store in ChromaDB (per-document collection)

def store_in_chroma(
    document_id: str,
    ids:         list[str],
    embeddings:  list[list[float]],
    metadatas:   list[dict],
    documents:   list[str],
) -> int:
    """
    Each PDF gets its own ChromaDB collection named by document_id.
    Multiple PDFs coexist without polluting each other.
    Retrieval is always scoped to the document the user chose.
    """
    os.makedirs(settings.chroma_path, exist_ok=True)

    client = chromadb.PersistentClient(
        path=settings.chroma_path,
        settings=ChromaSettings(anonymized_telemetry=False),
    )

    collection = client.get_or_create_collection(
        name=document_id,
        metadata={"hnsw:space": "cosine"},
    )

    batch = 100
    for i in range(0, len(ids), batch):
        collection.upsert(
            ids        = ids[i:i+batch],
            embeddings = embeddings[i:i+batch],
            metadatas  = metadatas[i:i+batch],
            documents  = documents[i:i+batch],
        )

    count = collection.count()
    print(f"[ingest] Stored {count} chunks in collection '{document_id}'")
    return count


#Retrieval helper (called by generator.py)

def query_chroma(
    query_text:  str,
    document_id: str,
    n_results:   int = 5,
) -> list[dict]:
    """
    Retrieves the top-n most relevant chunks for a query,
    scoped to a specific document's ChromaDB collection.
    """
    model  = SentenceTransformer(settings.embed_model)
    vector = model.encode([query_text]).tolist()

    client = chromadb.PersistentClient(
        path=settings.chroma_path,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    collection = client.get_collection(document_id)

    results = collection.query(
        query_embeddings=vector,
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )

    hits = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        hits.append({
            "text":     doc,
            "page":     meta["page"],
            "source":   meta["source"],
            "distance": round(dist, 4),
        })
    return hits


def list_documents() -> list[str]:
    """Returns all document collection names stored in ChromaDB."""
    client = chromadb.PersistentClient(
        path=settings.chroma_path,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    return [col.name for col in client.list_collections()]


#Full pipeline

def ingest(pdf_path: str, document_id: str = None) -> dict:
    """
    Full pipeline: any PDF → chunks → embeddings → ChromaDB.

    Args:
        pdf_path:    Path to any PDF file
        document_id: Optional UUID — auto-generated if not provided
    """
    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    if document_id is None:
        document_id = str(uuid.uuid4())

    pages  = extract_pages(pdf_path)
    chunks = chunk_pages(pages)
    ids, embeddings, metadatas = embed_chunks(chunks)
    documents = [m["text"] for m in metadatas]

    count = store_in_chroma(document_id, ids, embeddings, metadatas, documents)

    print(f"[ingest] Done. document_id={document_id}")
    return {
        "document_id": document_id,
        "page_count":  len(pages),
        "chunk_count": count,
        "source":      Path(pdf_path).name,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest any PDF into ChromaDB")
    parser.add_argument("--pdf", required=True, help="Path to any PDF file")
    parser.add_argument("--id",  default=None,  help="Optional document UUID")
    args   = parser.parse_args()
    result = ingest(args.pdf, args.id)
    print(result)
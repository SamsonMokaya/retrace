from __future__ import annotations

from pathlib import Path

import chromadb
from chromadb.config import Settings

CHROMA_PATH = Path(__file__).parent / "chroma_data"
COLLECTION_NAME = "memory_events"

_client: chromadb.PersistentClient | None = None


def _get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(CHROMA_PATH), settings=Settings(anonymized_telemetry=False))
    return _client


def get_collection():
    return _get_client().get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "Memory event embeddings for semantic search"},
    )


def add_event(event_id: int, embedding: list[float], metadata: dict | None = None) -> None:
    """Store one event embedding. id is stored as string for Chroma."""
    coll = get_collection()
    doc_id = str(event_id)
    meta = metadata or {}
    meta["event_id"] = event_id
    coll.add(ids=[doc_id], embeddings=[embedding], metadatas=[meta])


def clear_all() -> None:
    """Remove all vectors from the collection."""
    coll = get_collection()
    n = coll.count()
    if n == 0:
        return
    # Get all ids and delete (Chroma has no "delete all")
    result = coll.get(include=[])
    ids = result.get("ids") or []
    if ids:
        coll.delete(ids=ids)


def count() -> int:
    """Number of vectors in the collection."""
    coll = get_collection()
    return coll.count()


def search(embedding: list[float], top_k: int = 10) -> list[int]:
    """Return list of event_ids (ints) ordered by relevance."""
    coll = get_collection()
    results = coll.query(query_embeddings=[embedding], n_results=top_k, include=["metadatas"])
    ids = []
    if results and results["ids"] and results["ids"][0]:
        for doc_id in results["ids"][0]:
            try:
                ids.append(int(doc_id))
            except (ValueError, TypeError):
                pass
    return ids

"""Semantic search over the sonic-kb knowledge base.

Loads pre-computed embeddings from _vector_index.json, encodes queries with
sentence-transformers, and returns ranked results via brute-force cosine similarity.
"""

from __future__ import annotations

import numpy as np

from ._loader import load_vector_index


def search_kb(
    query: str,
    top_k: int = 5,
    content_type: str | None = None,
) -> list[dict]:
    """Search the KB by natural language query.

    Returns a ranked list of {id, type, title, text, score} dicts.
    Raises RuntimeError if sentence-transformers is not installed.
    Raises FileNotFoundError (via loader) if vector index doesn't exist.
    """
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise RuntimeError(
            "sentence-transformers is required for semantic search. "
            "Install with: pip install sonic-knowledge-base[vector]"
        )

    index = load_vector_index()
    if index is None:
        return []

    chunks = index["chunks"]
    if content_type:
        chunks = [c for c in chunks if c["type"] == content_type]
    if not chunks:
        return []

    model = SentenceTransformer(index["model"])
    query_emb = model.encode([query], normalize_embeddings=True)[0]

    embeddings = np.array([c["embedding"] for c in chunks], dtype=np.float32)
    scores = embeddings @ query_emb.astype(np.float32)

    top_indices = np.argsort(scores)[::-1][:top_k]

    results = []
    for idx in top_indices:
        idx = int(idx)
        c = chunks[idx]
        results.append({
            "id": c["id"],
            "type": c["type"],
            "title": c["title"],
            "text": c["text"],
            "score": round(float(scores[idx]), 4),
        })
    return results

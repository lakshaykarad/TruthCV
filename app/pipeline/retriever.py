from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.models import Chunk
from app.db.queries import get_primary_resume
from app.pipeline.embedder import embed_text

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 5 # I JUST WANT ONLY TOP 5 K CHUNKS THAT MATCH WITH OUR REQUIRMENTS
MIN_SIMILARITY = 0.4 

# Converts one Chunk Python dict
def _chunk_to_dict(chunk : Chunk, score : float) ->dict[str,Any]:
    return {
        "chunk_id" : chunk.chunk_id,
        "text" : chunk.text,
        "type" : chunk.chunk_type,
        "metadata" : chunk.chunk_metadata,
        "score" : round(score, 4)
    }

def find_similar_chunks_for_user(
    db: Session,
    user_id: int,
    query_text: str,
    top_k: int = DEFAULT_TOP_K,
    min_score: float = MIN_SIMILARITY,
) -> list[dict[str, Any]]:
    resume = get_primary_resume(db, user_id)
    
    if resume is None:
        logger.warning("User id=%s has no primary resume", user_id)
        return []

    return find_similar_chunks(
        db, resume.id, query_text, top_k=top_k, min_score=min_score,
    )


# Takes a query, creates its embedding, searches the given resume's chunks, gets the top k, and removes results below 0.4 similarity.
def find_similar_chunks(
    db: Session,
    resume_id: int,
    query_text: str,
    top_k: int = DEFAULT_TOP_K,
    min_score: float = MIN_SIMILARITY,
) -> list[dict[str, Any]]:
    
    if not query_text or not query_text.strip():
        return []

    if len(query_text.split()) <= 2:
        query_text_for_embedding = f"search_query: {query_text}"

    else:
        query_text_for_embedding = query_text

    query_vector = embed_text(query_text_for_embedding)
    
    statement = (
        select(
            Chunk,
            (1 - Chunk.embedding.cosine_distance(query_vector)).label("score"),
        )
        .where(Chunk.resume_id == resume_id)
        .order_by(Chunk.embedding.cosine_distance(query_vector))
        .limit(top_k)
    )

    rows = db.execute(statement).all()

    results = [
        _chunk_to_dict(chunk, score)
        for chunk, score in rows
        if score >= min_score
    ]

    logger.info(
        "Query '%s...' → %d/%d chunks above %.2f",
        query_text[:30], len(results), top_k, min_score,
    )
    return results

def find_chunks_for_skills(
    db: Session,
    resume_id: int,
    skills: list[str],
    top_k_per_skill: int = 2,
    min_score: float = MIN_SIMILARITY,
) -> list[dict[str, Any]]:
   
    combined: dict[str, dict[str, Any]] = {}

    for skill in skills:
        matches = find_similar_chunks(
            db, resume_id, skill,
            top_k=top_k_per_skill, min_score=min_score,
        )
        for match in matches:
            existing = combined.get(match["chunk_id"]) 
            if existing is None or match["score"] > existing["score"]:
                combined[match["chunk_id"]] = match

    merged = sorted(combined.values(), key=lambda c: c["score"], reverse=True)
    logger.info("Skills → %d unique chunks", len(merged))
    return merged
 
if __name__ == "__main__":
    import sys

    from app.db.session import get_session
    from app.db.queries import get_or_create_user

    logging.basicConfig(level=logging.INFO)

    query = sys.argv[1] if len(sys.argv) > 1 else "FastAPI Docker"
    email = sys.argv[2] if len(sys.argv) > 2 else "test@truthcv.com"

    with get_session() as db:
        user = get_or_create_user(db, email)
        results = find_similar_chunks_for_user(db, user.id, query)

    print(f"\nQuery: {query!r}")
    print(f"Found {len(results)} matching chunks:\n")
    for i, chunk in enumerate(results, 1):
        print(f"[{i}] score={chunk['score']:.3f}  type={chunk['type']}")
        print(f"    {chunk['text'][:100]}")
        print()
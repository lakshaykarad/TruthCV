from __future__ import annotations

import logging
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.models import Chunk
from app.db.queries import get_primary_resume
from app.pipeline.embedder import embed_text
from app.config import settings
import re as _re

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = settings.top_k
MIN_SIMILARITY = settings.similarity_threshold


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
  
# Ignore this words 
_SKILL_STOPWORDS = {
    "development", "experience", "projects", "project", "hackathons",
    "knowledge", "skills", "familiarity", "strong", "and", "or", "with",
    "of", "in", "the", "restful", "foundational", "concepts",
}

# extract technical skill keywords
def _skill_terms(skill : str) -> list[str]:
    terms : list[str] = []
    # scans the entire text from left to right 
    for tok in _re.findall(r"[A-Za-z][A-Za-z0-9+#.]*", skill):
        tok = tok.rstrip(".")
        # ignore . if there is no letter or number
        if len(tok) > 1 and tok.lower() not in _SKILL_STOPWORDS:
            terms.append(tok)
    return terms
# compare 2 string to check if keyword match or not
def _has_term(text : str , term : str) -> bool:
    pattern =  rf"(?<![A-Za-z0-9]){_re.escape(term)}(?![A-Za-z0-9])"
    return _re.search(pattern, text, _re.IGNORECASE) is  not None
 
# turn nested str, list, dict into a flat list list of string
def _flatten(value : Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [s for v in value for s in _flatten(v)]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _flatten(v)]
    
    return []

# find where from a chunk belong? where from it start
def _owner_project(text : str, names : list[str]) -> str | None:
    head = text[:80].lower()
    best, best_pos = None, None
    for name in names:
        if not name:
            continue
        pos = head.find(name.lower())
        if pos != -1 and (best_pos is None or pos < best_pos):
            best, best_pos = name,pos
    return best

# Return the top_n projects most relevant to the JD
def rank_projects(
    db: Session,
    resume_id: int,
    jd_json: dict[str, Any],
    projects: list[dict[str, Any]],
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """
    Return the top_n projects most relevant to the JD.

    Score per project = sum over JD skills of weight * evidence, where
      weight   = 2 for required skills, 1 for preferred skills
      evidence = best vector-search similarity of one of the project's chunks
               + 1 if the skill appears (whole word) in the project's
                 own name / tech / bullets
    """
    names = [(p.get("name") or "").strip() for p in projects]
    weighted = (
        [(s, 2.0) for s in jd_json.get("required_skills") or []]
        + [(s, 1.0) for s in jd_json.get("preferred_skills") or []]
    )
    scores = {n.lower(): 0.0 for n in names if n}

    for skill, weight in weighted:
        best: dict[str, float] = {}
        for m in find_similar_chunks(db, resume_id, f"experience with {skill}", top_k=8):
            if not str(m["type"]).startswith("project"):
                continue
            owner = _owner_project(m["text"], names)
            if owner:
                key = owner.lower()
                best[key] = max(best.get(key, 0.0), m["score"])
        for key, sim in best.items():
            scores[key] += weight * sim
 
        terms = _skill_terms(skill)
        if not terms:
            continue
        for proj, name in zip(projects, names):
            if not name:
                continue
            haystack = " ".join(
                [name, *_flatten(proj.get("tech")), *_flatten(proj.get("description"))]
            )
            if any(_has_term(haystack, t) for t in terms):
                scores[name.lower()] += weight

    ranked = sorted(
        zip(projects, names),
        key=lambda pn: scores.get(pn[1].lower(), 0.0),
        reverse=True,
    )
    logger.info(
        "Project ranking: %s",
        [(n, round(scores.get(n.lower(), 0.0), 2)) for _, n in ranked],
    )
    return [p for p, _ in ranked[:top_n]]

    
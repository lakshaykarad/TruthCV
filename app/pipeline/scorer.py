from __future__ import annotations

from typing import Any 
import logging

from sqlalchemy.orm import Session
from app.pipeline.retriever  import find_similar_chunks
from app.config import settings

logger = logging.getLogger(__name__)

WEAK_THRESHOLD = settings.weak_threshold
PARTIAL_THRESHOLD = settings.partial_threshold
STRONG_THRESHOLD = settings.strong_threshold
EVIDENCE_TOP_K = 3
SHOULD_APPLY_THRESHOLD = settings.should_apply_threshold


def classify_tier(score : float) -> str:
    if score >= STRONG_THRESHOLD:
        return "matched"
    if score >= PARTIAL_THRESHOLD:
        return "partial"
    if score >= WEAK_THRESHOLD:
        return "weak"
    return "missing"

def skill_appears_in_text(skill: str, text: str) -> bool:
     
    if not skill or not text:
        return False
    return skill.lower() in text.lower()

def score_one_skill(
    db : Session,
    resume_id : int,
    skill : str
) -> dict[str, Any] :
    matches = find_similar_chunks(
        db,
        resume_id,
        skill,
        top_k=EVIDENCE_TOP_K,
        min_score=WEAK_THRESHOLD
    )
    
    if not matches:
        return {
            "skill": skill,
            "score": 0.0,
            "tier": "missing",
            "evidence": [],
        }
    
    best = matches[0]
    
    evidence = [
        {
            "score": m["score"],
            "chunk_type": m["type"],
            "evidence_text": m["text"],
        }for m in matches
    ] # we can use loop here by making evidence as list []
    
    if not skill_appears_in_text(skill, best["text"]):
        logger.debug(
        "False positive: skill '%s' not in chunk '%s...' (score %.3f)",
        skill, best["text"][:50], best["score"],
        )
        return {
        "skill": skill,
        "score": best["score"],
        "tier": "missing",
        "evidence": [],   # ← was evidence, now empty
        }
    return {
        "skill" : skill,
        "score" : best["score"],
        "tier" : classify_tier(best["score"]),
        "evidence" : evidence
    }
    
    
    
def score_skill_list(
    db : Session,
    resume_id : int,
    skills : list[str]
) -> dict[str, list[dict[str,Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {
        "matched": [],
        "partial": [],
        "weak": [],
        "missing": [],
    }
    
    for skill in skills:
        if not skill or not skill.strip():
            continue
        result = score_one_skill(db, resume_id, skill)
        grouped[result["tier"]].append(result)

    return grouped

def score_match(
    db: Session,
    resume_id: int,
    jd_json: dict[str, Any],
) -> dict[str, Any]: 
    

    required_skills = jd_json.get("required_skills") or []
    preferred_skills = jd_json.get("preferred_skills") or []
 
    required_report = score_skill_list(db, resume_id, required_skills)
    preferred_report = score_skill_list(db, resume_id, preferred_skills)
    qualifications = jd_json.get("qualifications") or []

    
    required_total = len(required_skills)
    required_matched = len(required_report["matched"])
    required_partial = len(required_report["partial"])
    required_strong_enough = required_matched + required_partial
  
    if required_total == 0:
        match_percent = 0
    else:
        match_percent = round(required_strong_enough / required_total * 100)

    should_apply = match_percent >= SHOULD_APPLY_THRESHOLD

    preferred_matched = len(preferred_report["matched"]) + len(preferred_report["partial"])
    
    logger.info(
        "Match: %d%% (%d/%d required), should_apply=%s",
        match_percent, required_strong_enough, required_total, should_apply,
    )
    
    return {
        "required_skills_match_percent": match_percent,
        "should_apply": should_apply,
        "required": required_report,
        "preferred": preferred_report,
        "qualifications": qualifications,
        "counts": {
            "required_total": required_total,
            "required_matched": required_matched,
            "required_partial": required_partial,
            "preferred_total": len(preferred_skills),
            "preferred_matched": preferred_matched,
        },
        "note": (
            "Match % covers required skills only. "
            "Qualifications (years, degrees) are not scored — "
            "review them manually."
        ),
    } 
 
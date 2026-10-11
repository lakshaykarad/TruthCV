import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from fastapi.responses import StreamingResponse
from app.db.queries import get_or_create_user, get_primary_resume
from app.db.session import get_db
from app.pipeline.extractor import extract_jd_json
from app.pipeline.generator import (
    answer_questions,
    generate_cover_letter,
    generate_tailored_resume,
)
from app.pipeline.pdf_writer import render_cover_letter_pdf, render_resume_pdf

from app.db.models import Resume

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/generate",tags=["generate"])

DEFAULT_USER_EMAIL  = "test@truthcv.com"
MAX_JD_CHARS = 10_000
MAX_INSTRUCTIONS_CHARS = 2_000
MAX_QUESTIONS = 5


class GenerateResumeRequest(BaseModel):
    jd_text : str = Field(..., min_length=20, max_length=MAX_JD_CHARS)
    user_instructions: str = Field(default="", max_length=MAX_INSTRUCTIONS_CHARS)
    
    
class GenerateLetterRequest(BaseModel):
    jd_text : str = Field(..., min_length=20, max_length=MAX_JD_CHARS)
    
class GenerateAnswerRequest(BaseModel):
    jd_text : str = Field(..., min_length=20, max_length=MAX_JD_CHARS)
    questions : list[str] = Field(..., min_length=1, max_length=MAX_QUESTIONS) 
    user_instructions: str = Field(default="", max_length=MAX_INSTRUCTIONS_CHARS)


def _load_primary_resume(
    db : Session,
    email : str
) -> Resume:
    user = get_or_create_user(db , email)
    resume = get_primary_resume(db, user.id)
    
    if resume is None:
        raise HTTPException(
            status_code=404,
            detail="No primary resume found. upload one first"
        )
    return resume



def _parse_jd(
    jd_text : str
) -> dict:
    try:
        jd_json = extract_jd_json(jd_text)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not parse JD: {e}")
    
    if not jd_json or not jd_json.get("title") and not jd_json.get("required_skills"):
        raise HTTPException(
            status_code=422,
            detail="JD extraction returned no usable data. Check the JD text."
        )
    
    return jd_json


@router.post("/resume")
def generate_resume(
    body: GenerateResumeRequest,
    email: str = Query(default=DEFAULT_USER_EMAIL),
    db: Session = Depends(get_db),
) -> dict:
    """
    Tailor the primary resume to a JD.
    Returns: structured JSON + PDF path.
    """
    resume = _load_primary_resume(db, email)
    jd_json = _parse_jd(body.jd_text)

    logger.info("Generating tailored resume: role='%s'", jd_json.get("title"))

    try:
        tailored = generate_tailored_resume(
            db,
            resume.id,
            jd_json,
            user_instructions=body.user_instructions,
        )
    except Exception as e:
        logger.exception("Tailoring failed")
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")

    try:
        pdf_path = render_resume_pdf(tailored)
    except Exception as e:
        logger.exception("PDF render failed")
        raise HTTPException(status_code=500, detail=f"PDF render failed: {e}")

    filename = Path(pdf_path).name

    return {
        "status": "ok",
        "jd": jd_json,
        "tailored": tailored,
        "pdf_path": pdf_path,
        "download_url": f"/download/{filename}",
    }

 
@router.post("/cover-letter")
def generate_letter(
    body: GenerateLetterRequest,
    email: str = Query(default=DEFAULT_USER_EMAIL),
    db: Session = Depends(get_db),
) -> dict:
 
    resume = _load_primary_resume(db, email)
    jd_json = _parse_jd(body.jd_text)
    
    try:
        letter = generate_cover_letter(db, resume.id, jd_json)
    except Exception as e:
        logger.exception("Cover letter failed")
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")

    try:
        pdf_path = render_cover_letter_pdf(
            letter,
            candidate_name=(resume.json_data or {}).get("name") or "Candidate",
        )
    except Exception as e:
        logger.exception("PDF render failed")
        raise HTTPException(status_code=500, detail=f"PDF render failed: {e}")

    filename = Path(pdf_path).name

    return {
        "status": "ok",
        "jd": jd_json,
        "cover_letter": letter,
        "word_count": len(letter.split()),
        "pdf_path": pdf_path,
        "download_url": f"/download/{filename}",
    }

@router.post("/answers")
def generate_answers(
    body: GenerateAnswerRequest,
    email: str = Query(default=DEFAULT_USER_EMAIL),
    db: Session = Depends(get_db),
) -> dict:
    """
    Answer up to 5 user questions about the resume + JD.
    Read-only — no DB writes.
    """
    resume = _load_primary_resume(db, email)
    jd_json = _parse_jd(body.jd_text)

    logger.info(
        "Answering %d question(s): role='%s'",
        len(body.questions), jd_json.get("title"),
    )

    try:
        answers = answer_questions(
            db,
            resume.id,
            jd_json,
            body.questions,
            user_instructions=body.user_instructions,
        )
    except ValueError as e:
       
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Answering failed")
        raise HTTPException(status_code=500, detail=f"Answering failed: {e}")

    return {
        "status": "ok",
        "jd": jd_json,
        "answers": answers,
        "count": len(answers),
    }

class ScoreRequest(BaseModel):
    jd_text: str = Field(..., min_length=20, max_length=MAX_JD_CHARS)


@router.post("/score")
def score_jd(
    body: ScoreRequest,
    email: str = Query(default=DEFAULT_USER_EMAIL),
    db: Session = Depends(get_db),
) -> dict: 
    resume = _load_primary_resume(db, email)
    jd_json = _parse_jd(body.jd_text)

    from app.pipeline.scorer import score_match
    report = score_match(db, resume.id, jd_json)

    return {
        "status": "ok",
        "match_percent": report["required_skills_match_percent"],
        "should_apply": report["should_apply"],
        "matched": [s["skill"] for s in report["required"]["matched"]],
        "partial": [s["skill"] for s in report["required"]["partial"]],
        "missing": [s["skill"] for s in report["required"]["missing"]],
        "preferred_matched": [s["skill"] for s in report["preferred"]["matched"]],
        "counts": report["counts"],
    }
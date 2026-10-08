from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any
import groq
from dotenv import load_dotenv
from groq import Groq
from sqlalchemy.orm import Session
from app.db.models import Resume
from app.pipeline.retriever import find_similar_chunks_for_user
from app.pipeline.scorer import score_match

load_dotenv()

logger = logging.getLogger(__name__)

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
GENERATION_MODEL = os.getenv("GENERATION_MODEL", "openai/gpt-oss-120b")
GENERATION_TIMEOUT = int(os.getenv("GENERATION_TIMEOUT", "180"))
PROMPT_DIR = Path(__file__).resolve().parents[2] / "ollama" / "prompts"
 
def _load_prompt(name: str) -> str:
    """Load a prompt template by name. e.g. 'cover_letter' → cover_letter.txt"""
    path = PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8")

"""Convert JSON data into simple python string"""
# - Python Programming (score 0.95): "Developed core backend API services."
# - Project Management (score 0.60): "(no evidence)"
def _format_matched_skills(report: dict) -> str:
    lines = []
    for item in (report.get("matched") or []) + (report.get("partial") or []):
        evidence = (
            item["evidence"][0]["evidence_text"] if item.get("evidence") else "(no evidence)"
        )
        lines.append(f'- {item["skill"]} (score {item["score"]:.2f}): "{evidence}"')
    return "\n".join(lines) if lines else "(none)"

"""Same like last call, convert JSON data into string""" 
# [{"skill": "React", "score": 0.81, "evidence": [...]},
#  {"skill": "JavaScript", "score": 0.68, "evidence": [...]}]
# "React, JavaScript"
def _format_skill_names(items: list[dict]) -> str:
    names = [x["skill"] for x in items]
    return ", ".join(names) if names else "(none)"

"""Build list of bullets points"""
# ["Design REST APIs", "Write unit tests", "Review code"]
# - Design REST APIs
# - Write unit tests
# - Review code
def _format_bullets(items: list[str]) -> str:
    return "\n".join(f"- {x}" for x in items) if items else "(none)"

"""Format the guy education as a bullet list"""
#- BCA — University of Rajasthan (2023-2026)
def _format_education(resume_json: dict) -> str:
    edu = resume_json.get("education") or []
    if not edu:
        return "(not provided)"
    return "\n".join(
        f"- {e.get('degree', '')} — {e.get('institution', '')} ({e.get('year', '')})"
        for e in edu
    )

def _call_groq(
    prompt: str,
    *,
    json_mode: bool = False,
    max_tokens: int = 8192,
    effort: str = "low",
) -> str:
    # kwargs = keyword arguments 
    kwargs: dict[str, Any] = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = groq_client.chat.completions.create(
        model=GENERATION_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        reasoning_effort=effort,
        max_completion_tokens=max_tokens,
        **kwargs, # unpack the keyword arguments -> Json to normal text
    )
    choice = response.choices[0] # groq give n number of answer but we need only one. 
    logger.info("finish_reason=%s usage=%s", choice.finish_reason, response.usage)

    if choice.finish_reason == "length":
        raise ValueError("LLM output truncated (raise max_tokens or lower effort)")
    if not choice.message.content:
        raise ValueError(f"Empty LLM response (finish_reason={choice.finish_reason})")
    return choice.message.content.strip()

 
def generate_cover_letter(
    db: Session,
    resume_id: int,
    jd_json: dict[str, Any],
) -> str:
    """Generate a cover letter for a specific JD + resume."""
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise ValueError(f"Resume id={resume_id} not found")

    report = score_match(db, resume_id, jd_json)
    match_pct = report["required_skills_match_percent"]
    required = report["required"]

    if match_pct < 40:
        logger.warning("Low match (%d%%). This is a stretch application.", match_pct)
        extra_context = (
            "OVERRIDE RULES 1 and 8: Write ONE short paragraph (under 90 words). "
            "The candidate does not match this role. Be honest — this is a "
            "stretch application. Do NOT use words like 'confident', "
            "'excited', or 'eager'. Focus on ONE transferable skill."
        )
    else:
        extra_context = ""

    resume_json = resume.json_data or {}
    candidate_name = resume_json.get("name") or "Candidate"

    contact_bits = []
    for field in ("location", "email", "phone", "website"):
        if resume_json.get(field):
            contact_bits.append(resume_json[field])
    contact_line = " | ".join(contact_bits) if contact_bits else "(not provided)"
 
    # medium or week skilsl add here
    partial_items = required.get("partial") or required.get("weak") or []

    template = _load_prompt("cover_letter")
    prompt = (
        template
        .replace("{{CANDIDATE_NAME}}", candidate_name)
        .replace("{{CONTACT_LINE}}", contact_line)
        .replace("{{JOB_TITLE}}", jd_json.get("title") or "the role")
        .replace("{{COMPANY}}", jd_json.get("company") or "your company")
        .replace("{{RESPONSIBILITIES}}",
                 _format_bullets(jd_json.get("responsibilities") or []))
        .replace("{{MATCHED_SKILLS}}", _format_matched_skills(required))
        .replace("{{PARTIAL_SKILLS}}", _format_skill_names(partial_items))
        .replace("{{MISSING_SKILLS}}",
                 _format_skill_names(required.get("missing") or []))
        .replace("{{QUALIFICATIONS}}",
                 _format_bullets(jd_json.get("qualifications") or []))
        .replace("{{STRETCH_NOTE}}", extra_context)
        .replace("{{EDUCATION}}", _format_education(resume_json))
    )

    logger.info(
        "Generating cover letter: resume=%d role='%s' company='%s' match=%d%%",
        resume_id, jd_json.get("title"), jd_json.get("company"), match_pct,
    )

    # Plain text output: NO json_mode here
    text = _call_groq(prompt, effort="medium")
    logger.info("Cover letter generated: %d characters", len(text))
    return text

 
MAX_USER_EXTRAS_CHARS = 500
REQUIRED_NONEMPTY = ("summary", "skills", "projects")
ALLOWED_KEYS = {
    "name", "tailored_title", "email", "phone", "location",
    "website", "links", "summary", "skills", "projects",
    "experience", "education", "achievements",
}

def _build_jd_query(jd_json: dict[str, Any]) -> str:
    """(Optional, currently unused) Combine JD skills into one retriever query."""
    parts = (
        (jd_json.get("required_skills") or []) +
        (jd_json.get("preferred_skills") or [])
    )
    if jd_json.get("title"):
        parts = [jd_json["title"]] + parts
    return " ".join(parts) if parts else "software engineer"


def _fetch_relevant_chunks_text(
    db: Session,
    user_id: int,
    jd_json: dict[str, Any],
    top_k: int = 15,
) -> str: 
    query = _build_jd_query(jd_json)
    chunks = find_similar_chunks_for_user(db, user_id, query, top_k=top_k)
    if not chunks:
        logger.warning("Retriever returned 0 chunks for query: %r", query)
        return "(no relevant chunks found)"
    logger.info("Retrieved %d relevant chunks", len(chunks))
    return "\n".join(f"[{c['type']}] {c['text']}" for c in chunks)

def _parse_and_validate(raw: str) -> dict[str, Any]:
    """Strip code fences, parse JSON, and reject empty/skeleton answers."""
    cleaned = re.sub(
        r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.DOTALL
    ).strip()
    data = json.loads(cleaned)

    if not isinstance(data, dict):
        raise ValueError("LLM did not return a JSON object")

    # unwrap {"resume": {...}} style answers
    if isinstance(data.get("resume"), dict):
        data = data["resume"]

    missing = [k for k in REQUIRED_NONEMPTY if not data.get(k)]
    if missing:
        raise ValueError(f"LLM returned empty fields: {missing}")
    if not isinstance(data["skills"], dict):
        raise ValueError("'skills' must be an object of category → list")
    return data


def generate_tailored_resume(
    db: Session,
    resume_id: int,
    jd_json: dict[str, Any],
    user_extras: str = "",
) -> dict[str, Any]:
    """Tailor a resume to a specific JD. Uses the RAG retriever to save tokens."""

    # load resume FIRST
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise ValueError(f"Resume id={resume_id} not found")
    
    original: dict[str, Any] = resume.json_data or {}
    if not original:
        raise ValueError(f"Resume id={resume_id} has no json_data")

    # build mini resume (structured facts, no bullet descriptions)
    mini = {
        "skills": original.get("skills") or [],
        "project_names": [
            p.get("name") for p in (original.get("projects") or [])
            if p.get("name")
        ],
    }
    # 3. Fetch only the relevant chunks via RAG
    relevant_chunks = _fetch_relevant_chunks_text(
        db, resume.user_id, jd_json, top_k=15,
    )

    # 4. Cap user input
    if user_extras and len(user_extras) > MAX_USER_EXTRAS_CHARS:
        logger.warning("user_extras too long, truncating")
        user_extras = user_extras[:MAX_USER_EXTRAS_CHARS]

    # 5. Build prompt: mini resume + chunks + JD
    template = _load_prompt("tailored_resume")
    prompt = (
        template
        .replace("{{RESUME_JSON}}", json.dumps(mini, indent=2, ensure_ascii=False))
        .replace("{{RELEVANT_CHUNKS}}", relevant_chunks)
        .replace("{{JD_JSON}}", json.dumps(jd_json, indent=2, ensure_ascii=False))
        .replace("{{USER_EXTRAS}}", user_extras or "(none)")
    )

    logger.info(
        "Tailoring resume: resume=%d role='%s' company='%s'",
        resume_id, jd_json.get("title"), jd_json.get("company"),
    )

    # 6. Call LLM
    data: dict[str, Any] | None = None
    last_err: Exception | None = None
    for attempt in range(1, 4):
        try:
            raw = _call_groq(prompt, json_mode=True)
            logger.debug("RAW LLM OUTPUT: %s", raw[:3000])
            data = _parse_and_validate(raw)
            break
        except (json.JSONDecodeError, ValueError, groq.BadRequestError) as e:
            last_err = e 
            logger.warning("Attempt %d failed: %s", attempt, e)
            prompt += (
                "\n\nREMINDER: Output ONLY one JSON object with ALL schema keys. "
                "summary, skills and projects must NOT be empty."
            )
    if data is None:
        raise RuntimeError(f"Tailoring failed after 3 attempts: {last_err}") from last_err

    # 7. Post-processing: code owns the facts
    for field in ("name", "email", "phone", "location", "website"):
        data[field] = original.get(field)
    
    data["links"] = list(dict.fromkeys(original.get("links") or []))
    # Education
    data["education"] = original.get("education") or []
    # Tailored title
    data["tailored_title"] = jd_json.get("title") or data.get("tailored_title")
    # Experience — always from original (LLM has no say)
    data["experience"] = original.get("experience") or []
    data["achievements"] = original.get("achievements") or []


    # Projects — verify names, restore tech + links from original
    orig_projects = {
        (p.get("name") or "").strip().lower(): p
        for p in (original.get("projects") or [])
    }
    clean_projects = []
    for proj in data.get("projects") or []:
        key = (proj.get("name") or "").strip().lower()
        if key not in orig_projects:
            logger.warning("Dropping unknown project from LLM: %r", proj.get("name"))
            continue
        proj["tech"] = orig_projects[key].get("tech") or []
        proj["links"] = list(dict.fromkeys(orig_projects[key].get("links") or []))
        clean_projects.append(proj)
    data["projects"] = clean_projects

    logger.info(
        "Tailored resume ready: %d projects, %d skills groups",
        len(data.get("projects", [])),
        len(data.get("skills", {})),
    )

    # 8. Drop null/empty fields
    data = {
        k: v for k, v in data.items()
        if v is not None and v != [] and v != {}
    }
    data.pop("linkedin", None)
    data.pop("github", None)
    return data
 
 
 
if __name__ == "__main__":
    import sys

    from app.db.queries import get_or_create_user, get_primary_resume
    from app.db.session import get_session

    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    mode = sys.argv[1] if len(sys.argv) > 1 else "tailor"

    jd_json =  {
    "title": "Associate Software Engineer (Backend & Mobile Integration)",
    "company": "Razorpay",
    "required_skills": ["Python", "FastAPI", "PostgreSQL", "Android Development (Kotlin/Java)", "RESTful APIs"],
    "preferred_skills": ["Docker", "Redis", "AWS", "Fintech projects/hackathons"],
    "responsibilities": [
        "Design, build, and maintain scalable REST APIs for payment services",
        "Collaborate on seamless integration between Android applications and backend services",
        "Write clean, efficient, and well-tested code (unit and integration tests)",
        "Participate in code reviews and troubleshoot technical issues across the stack"
    ],
    "qualifications": [
        "Bachelor's degree in Computer Science, Engineering, or a related technical field",
        "Strong foundational knowledge of Python and backend concepts",
        "Hands-on experience with Android development through academic projects, personal apps, or internships",
        "Familiarity with databases (like PostgreSQL) and version control (Git)"
    ]
}

    with get_session() as db:
        user = get_or_create_user(db, "test@truthcv.com")
        resume = get_primary_resume(db, user.id)
        if resume is None:
            print("No primary resume. Upload one first.")
            sys.exit(1)

        if mode == "letter":
            letter = generate_cover_letter(db, resume.id, jd_json)
            print("\n" + "=" * 60)
            print("COVER LETTER")
            print("=" * 60)
            print(letter)
            print("=" * 60)
            print(f"\nWord count: {len(letter.split())}")
        else:
            result = generate_tailored_resume(db, resume.id, jd_json)
            print(json.dumps(result, indent=2, ensure_ascii=False))
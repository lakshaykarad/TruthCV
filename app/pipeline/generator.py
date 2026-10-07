from __future__ import annotations

import logging
import os
import re
import json
from pathlib import Path
from typing import Any
from groq import Groq
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from app.db.models import Resume
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

def _format_matched_skills(report: dict) -> str:
    """Turn matched skills into a bullet list with evidence."""
    lines = []
    for item in report["matched"] + report["partial"]:
        evidence = item["evidence"][0]["evidence_text"] if item["evidence"] else "(no evidence)"
        lines.append(f'- {item["skill"]} (score {item["score"]:.2f}): "{evidence}"')
    return "\n".join(lines) if lines else "(none)"


def _format_skill_names(items: list[dict]) -> str:
    """Just the skill names, comma-separated."""
    names = [x["skill"] for x in items]
    return ", ".join(names) if names else "(none)"


def _format_bullets(items: list[str]) -> str:
    """A plain bullet list of strings."""
    return "\n".join(f"- {x}" for x in items) if items else "(none)"

def _call_groq(prompt: str) -> str:
    """Send the prompt to Groq, return the generated text."""
    response = groq_client.chat.completions.create(
    model=GENERATION_MODEL,
    messages=[{"role": "user", "content": prompt}],
    temperature=0.4,       # lower for JSON tasks — more deterministic
    top_p=0.8,
    reasoning_effort="medium",
    max_tokens=3072,       # ← 2× the budget
    response_format={"type": "json_object"},   # ← forces valid JSON
    )
    return response.choices[0].message.content.strip()

def _format_education(resume_json: dict) -> str:
    """List the candidate's real education entries."""
    edu = resume_json.get("education") or []
    if not edu:
        return "(not provided)"
    lines = []
    for e in edu:
        degree = e.get("degree", "")
        inst = e.get("institution", "")
        year = e.get("year", "")
        lines.append(f"- {degree} — {inst} ({year})")
    return "\n".join(lines)

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
 
    if match_pct < 40:
        logger.warning(
            "Low match (%d%%). This is a stretch application.",
            match_pct,
        )
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
    if resume_json.get("email"):
        contact_bits.append(resume_json["email"])
    if resume_json.get("phone"):
        contact_bits.append(resume_json["phone"])
    if resume_json.get("website"):
        contact_bits.append(resume_json["website"])
    contact_line = " | ".join(contact_bits) if contact_bits else "(not provided)"
 
    template = _load_prompt("cover_letter")
    prompt = (
        template
        .replace("{{CANDIDATE_NAME}}", candidate_name)
        .replace("{{CONTACT_LINE}}", contact_line)
        .replace("{{JOB_TITLE}}", jd_json.get("title") or "the role")
        .replace("{{COMPANY}}", jd_json.get("company") or "your company")
        .replace("{{RESPONSIBILITIES}}",
                 _format_bullets(jd_json.get("responsibilities") or []))
        .replace("{{MATCHED_SKILLS}}", _format_matched_skills(report["required"]))
        .replace("{{PARTIAL_SKILLS}}",
                 _format_skill_names(report["required"]["weak"]))
        .replace("{{MISSING_SKILLS}}",
                 _format_skill_names(report["required"]["missing"]))
        .replace("{{QUALIFICATIONS}}",                 
                 _format_bullets(jd_json.get("qualifications") or []))
        .replace("{{STRETCH_NOTE}}", extra_context)
        .replace("{{EDUCATION}}", _format_education(resume_json))
    )

    logger.info(
        "Generating cover letter: resume=%d role='%s' company='%s' match=%d%%",
        resume_id, jd_json.get("title"), jd_json.get("company"), match_pct,
    )
 
    text = _call_groq(prompt)

    logger.info("Cover letter generated: %d characters", len(text))
    return text
 
MAX_USER_EXTRAS_CHARS = 500 

def generate_tailored_resume(
    db: Session,
    resume_id: int,
    jd_json: dict[str, Any],
    user_extras: str = "",
) -> dict[str, Any]:
    
    # 1. Load resume
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise ValueError(f"Resume id={resume_id} not found")

    # 2. Score
    report = score_match(db, resume_id, jd_json)

    # 3. Cap user input
    if user_extras and len(user_extras) > MAX_USER_EXTRAS_CHARS:
        logger.warning("user_extras too long, truncating")
        user_extras = user_extras[:MAX_USER_EXTRAS_CHARS]

    # 4. Build prompt
    template = _load_prompt("tailored_resume")
    prompt = (
        template
        .replace("{{RESUME_JSON}}", json.dumps(resume.json_data, indent=2))
        .replace("{{JD_JSON}}", json.dumps(jd_json, indent=2))
        .replace("{{MATCH_REPORT}}", json.dumps(report, indent=2))
        .replace("{{USER_EXTRAS}}", user_extras or "(none)")
    )

    logger.info(
        "Tailoring resume: resume=%d role='%s' company='%s'",
        resume_id, jd_json.get("title"), jd_json.get("company"),
    )

    # 5. Call LLM with retry on JSON parse failure
    last_error: Exception | None = None
    for attempt in range(1, 3):
        raw = _call_groq(prompt)
        cleaned = re.sub(
            r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.DOTALL
        ).strip()

        try:
            data = json.loads(cleaned)
            # Guarantee contact fields survive, no matter what the LLM does
            original = resume.json_data or {}
            for field in ["name", "email", "phone", "location", "linkedin", "github", "website", "links"]:
                if original.get(field):
                    data[field] = original[field]
                elif field not in data:
                    data[field] = [] if field == "links" else None
            
            # Guarantee project links survive
            for proj in data.get("projects") or []:
                original_proj = next(
                    (p for p in original.get("projects") or []
                     if p.get("name", "").lower() == proj.get("name", "").lower()),
                    None,
                )
                if original_proj and original_proj.get("links"):
                    proj["links"] = original_proj["links"]
                elif "links" not in proj:
                    proj["links"] = []
            break
        except json.JSONDecodeError as e:
            last_error = e
            logger.warning("Attempt %d: invalid JSON (%s)", attempt, e)
            if attempt == 2:
                logger.error("Raw output preview: %s", cleaned[:500])
                raise ValueError(
                    f"Tailored resume is not valid JSON: {e}"
                ) from e
            prompt += "\n\nREMINDER: Output ONLY the JSON object. No extra text."

    logger.info(
        "Tailored resume ready: %d projects, %d skills groups",
        len(data.get("projects", [])),
        len(data.get("skills", {})),
    )
    return data

 
if __name__ == "__main__":
    import json
    import sys

    from app.db.queries import get_or_create_user, get_primary_resume
    from app.db.session import get_session

    logging.basicConfig(level=logging.INFO)

    # A JD that matches Aakriti's frontend resume
    jd_json = {
        "title": "Frontend Engineer",
        "company": "Design Startup",
        "required_skills": ["React", "JavaScript", "HTML", "CSS"],
        "preferred_skills": ["Tailwind CSS", "Fabric.js", "Git"],
        "responsibilities": [
            "Build and maintain user-facing features using React",
            "Collaborate with designers on component libraries",
            "Ensure cross-browser compatibility and performance",
        ],
        "qualifications": [
            "Bachelor's degree in Computer Science or equivalent",
        ],
    }

    with get_session() as db:
        user = get_or_create_user(db, "test@truthcv.com")
        resume = get_primary_resume(db, user.id)
        if resume is None:
            print("No primary resume. Upload one first.")
            sys.exit(1)

        letter = generate_cover_letter(db, resume.id, jd_json)

    print("\n" + "=" * 60)
    print("COVER LETTER")
    print("=" * 60)
    print(letter)
    print("=" * 60)
    print(f"\nWord count: {len(letter.split())}")
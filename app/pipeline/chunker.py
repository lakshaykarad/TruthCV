from __future__ import annotations

import hashlib, logging, re
from typing import Any

logger = logging.getLogger(__name__)

MAX_CHUNK_CHARS = 400
MIN_CHUNK_CHARS = 3
 
_JUNK_PATTERNS = re.compile(
    r"^(none specified|not specified|n/?a|none|null|unknown|not mentioned|"
    r"hobbies:?\s*none.*|spoken languages:?\s*none.*|"
    r"basic volunteer activities:?\s*none.*)$",
    re.IGNORECASE,
)
SKILL_CATEGORIES = {
    "languages": [
        "c", "c++", "python", "java", "javascript", "typescript",
        "go", "rust", "kotlin", "swift", "ruby", "php",
    ],
    "frontend": [
        "html", "css", "react", "vue", "angular", "tailwind css",
        "sass", "next.js", "svelte",
    ],
    "backend": [
        "fastapi", "django", "flask", "node.js", "express",
        "spring boot", "rails",
    ],
    "database": [
        "postgresql", "mysql", "mongodb", "redis", "sqlite",
        "sql", "dynamodb",
    ],
    "devops": [
        "docker", "kubernetes", "aws", "gcp", "azure", "nginx",
        "terraform", "ci/cd",
    ],
    "tools": [
        "git", "github", "gitlab", "vs code", "vercel", "netlify",
        "postman", "jira",
    ],
    "design": [
        "fabric.js", "canva", "figma", "photoshop", "illustrator",
    ],
    "data": [
        "pandas", "numpy", "tensorflow", "pytorch", "scikit-learn",
    ],
}


def is_junk(text: str) -> bool:
    """ Ignore empty string or string < MIN_CHUNK_CHARS, and matches with patterns ex none na NA """
    if not text or len(text.strip()) < MIN_CHUNK_CHARS:
        return True
    return bool(_JUNK_PATTERNS.match(text.strip()))


def replace_white_space(text: str) -> str:
    """Replace all whitespace with a single space."""
    return " ".join(text.split())

"""Safety net, prevents the chunks from becoming too long"""
def shorten_text(text: str, limit: int = MAX_CHUNK_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"

def build_chunk(
    text: str,
    source: str,
    chunk_type: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    text = shorten_text(replace_white_space(text))
    if is_junk(text):
        return None

    chunk_id = hashlib.sha1(
        f"{source}:{chunk_type}:{text}".encode("utf-8")
    ).hexdigest()[:16]

    return {
        "id": chunk_id,
        "text": text,
        "source": source,
        "type": chunk_type,
        "metadata": metadata or {},
    }

def remove_duplicates(strings: list[str]) -> list[str]: 
    seen: set[str] = set()
    result: list[str] = []
    for s in strings:
        key = replace_white_space(s).lower()
        if key and key not in seen:
            seen.add(key)
            result.append(s)
    return result

def group_skills(skills: list[str]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    ungrouped: list[str] = []
    for skill in skills:
        found = False
        for category, known in SKILL_CATEGORIES.items():
            if any(k == skill.lower() for k in known):
                groups.setdefault(category, []).append(skill)
                found = True
                break
        if not found:
            ungrouped.append(skill)
    if ungrouped:
        groups["other"] = ungrouped
    return groups

def chunk_resume(resume: dict[str, Any]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    name = resume.get("name") or "Candidate"
    seen_texts: set[str] = set()

    def emit(text: str, chunk_type: str, metadata: dict | None = None) -> None:
        """Build chunk, skip if text already emitted, else append."""
        key = replace_white_space(text).lower()
        if not key or key in seen_texts:
            return
        seen_texts.add(key)
        c = build_chunk(text, "resume", chunk_type, metadata)
        if c:
            chunks.append(c)
 
    contact_parts = [
        f"Email: {resume['email']}"     if resume.get("email")   else None,
        f"Phone: {resume['phone']}"     if resume.get("phone")   else None,
        f"Website: {resume['website']}" if resume.get("website") else None,
    ]
    contact_line = " | ".join(b for b in contact_parts if b)
    if contact_line:
        emit(f"{name} — {contact_line}", "contact", {"name": name})

    for link in resume.get("links") or []:
        emit(f"{name}'s link: {link}", "link", {"url": link})
 
    skills = remove_duplicates(resume.get("skills") or [])
    if skills:
        emit(f"{name}'s skills: {', '.join(skills)}", "skills_summary",
             {"skills": skills})
        
         # Grouped chunks (by category)
    groups = group_skills(skills)
    category_labels = {
        "languages": "Programming languages",
        "frontend": "Frontend skills",
        "backend": "Backend skills",
        "database": "Database skills",
        "devops": "DevOps and cloud",
        "tools": "Tools and platforms",
        "design": "Canvas and design",
        "data": "Data and ML",
        "other": "Other skills",
    }
    for cat, cat_skills in groups.items():
        label = category_labels.get(cat, cat.title())
        emit(f"{label}: {', '.join(cat_skills)}", "skill_group",
             {"category": cat, "skills": cat_skills})
 
    for exp in resume.get("experience") or []:
        if not isinstance(exp, dict):
            continue

        title   = replace_white_space(exp.get("title")   or "")
        company = replace_white_space(exp.get("company") or "")
        dur     = replace_white_space(exp.get("duration") or "")

        if not (title or company):
            continue

        if title and company:
            headline = f"{name} worked as {title} at {company}"
        elif title:
            headline = f"{name} worked as {title}"
        else:
            headline = f"{name} worked at {company}"
        if dur:
            headline += f" ({dur})"

        emit(headline, "experience",
             {"title": title, "company": company, "duration": dur})

        for bullet in exp.get("description") or []:
            bullet = replace_white_space(str(bullet))
            if is_junk(bullet):
                continue
            emit(f"{title or company}: {bullet}", "experience_detail",
                 {"title": title, "company": company})
 
    for proj in resume.get("projects") or []:
        if not isinstance(proj, dict):
            continue

        project_name = replace_white_space(proj.get("name") or "")
        if not project_name:
            continue

        tech  = remove_duplicates(proj.get("tech")  or [])
        links = remove_duplicates(proj.get("links") or [])

        headline = f"Project: {project_name}"
        if tech:
            headline += f" (Tech: {', '.join(tech)})"
        if links:
            headline += f" — {', '.join(links)}"

        emit(headline, "project",
             {"name": project_name, "tech": tech, "links": links})

        for bullet in proj.get("description") or []:
            bullet = replace_white_space(str(bullet))
            if is_junk(bullet):
                continue
            emit(f"{project_name}: {bullet}", "project_detail", {"project": project_name})
 
    for edu in resume.get("education") or []:
        if not isinstance(edu, dict):
            continue

        deg  = replace_white_space(edu.get("degree") or "")
        inst = replace_white_space(edu.get("institution") or "")
        year = replace_white_space(edu.get("year") or "")
        if not (deg or inst):
            continue

        if deg and inst:
            text = f"{name} studied {deg} at {inst}"
        elif deg:
            text = f"{name} studied {deg}"
        else:
            text = f"{name} studied at {inst}"
        if year:
            text += f" ({year})"

        emit(text, "education",
             {"degree": deg, "institution": inst, "year": year})

    # --- 6. achievements ---
    for ach in resume.get("achievements") or []:
        ach = replace_white_space(str(ach))
        if is_junk(ach):
            continue
        emit(f"{name}: {ach}", "achievement", {"achievement": ach})

    # --- 7. other details ---
    for detail in resume.get("other_details") or []:
        detail = replace_white_space(str(detail))
        if is_junk(detail):
            continue
        emit(f"{name}: {detail}", "other", {"detail": detail})

    logger.info("Resume → %d chunks", len(chunks))
    return chunks
 
def chunk_jd(jd: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Expected JD JSON:
      { "title": str, "company": str,
        "required_skills": [str], "preferred_skills": [str],
        "responsibilities": [str], "qualifications": [str] }
    """
    chunks: list[dict[str, Any]] = []
    title   = replace_white_space(jd.get("title") or "Role")
    company = replace_white_space(jd.get("company") or "")

    c = build_chunk(
        f"Job: {title}" + (f" at {company}" if company else ""),
        "jd", "header", {"title": title, "company": company},
    )
    if c: chunks.append(c)

    for field, chunk_type in [
        ("required_skills",   "required_skill"),
        ("preferred_skills",  "preferred_skill"),
        ("responsibilities",  "responsibility"),
        ("qualifications",    "qualification"),
    ]:
        for item in remove_duplicates(jd.get(field) or []):
            label = field.replace("_", " ").title().rstrip("s")
            c = build_chunk(f"{label}: {item}", "jd", chunk_type,
                            {"skill": item} if "skill" in chunk_type else {})
            if c: chunks.append(c)

    logger.info("JD → %d chunks", len(chunks))
    return chunks


# ---------- smoke test ----------
if __name__ == "__main__":
    import json, sys
    from app.pipeline.pdf_reader import read_pdf
    from app.pipeline.extractor import extract_resume_json

    logging.basicConfig(level=logging.INFO)
    pdf = sys.argv[1] if len(sys.argv) > 1 else "resume.pdf"

    resume = extract_resume_json(read_pdf(pdf))
    chunks = chunk_resume(resume)

    print(json.dumps(chunks, indent=2, ensure_ascii=False))
    print(f"\nTotal: {len(chunks)} chunks")
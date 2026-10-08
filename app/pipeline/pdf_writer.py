from __future__ import annotations

import logging 
import re 
from datetime import datetime
from pathlib import Path
from typing import Any
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"
OUTPUT_DIR = Path("output") # new folder name as output
OUTPUT_DIR.mkdir(exist_ok=True)

# Jinja2 environment
_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)), #load the file from "templates"
    autoescape=False 
)

MAX_RESUME_PAGES = 2

def _safe_filename(name : str) -> str:
    if not name:
        return "candidate"
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "candidate"


#add https:// if missing
def _ensure_scheme(url : str) -> str:
    if not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url
    return f"https://{url}"


def _short_link_label(url: str) -> str:
    """'github.com/user/repo' → 'GitHub'; keeps display clean."""
    low = url.lower()
    mapping = {"github": "GitHub", "linkedin": "LinkedIn", "leetcode": "LeetCode"}
    
    for key, label in mapping.items():
        if key in low:
            return label
            
    if any(domain in low for domain in ["vercel.app", "netlify.app", "github.io"]):
        return "Live"
        
    return url


def _build_contact_line(resume: dict[str, Any]) -> str:
    """Assemble 'City | email | phone | website | github | leetcode' with links."""
    email, web = resume.get("email"), resume.get("website")
    
    parts = [
        resume.get("location"),
        f'<a href="mailto:{email}">{email}</a>' if email else None,
        resume.get("phone"),
        f'<a href="{_ensure_scheme(web)}">{web}</a>' if web else None,
        *[f'<a href="{_ensure_scheme(lk)}">{lk}</a>' for lk in resume.get("links") or [] if lk]
    ]
    
    sep = '<span class="sep">|</span>'
    return f" {sep} ".join(p for p in parts if p)


def _build_project_links(links:list[str]) ->list[dict[str,str]]:
    out = []
    
    for url in links or []:
        if not url:
            continue
        out.append({"label": _short_link_label(url), "href": _ensure_scheme(url)})

        
    return out



def _normalize_for_template(tailored: dict[str, Any]) -> dict[str, Any]:
    """Prepare the tailored JSON for the template."""
    projects = []
    for p in tailored.get("projects") or []:
        projects.append({
            "name": p.get("name") or "",
            "tech": p.get("tech") or [],
            "links": _build_project_links(p.get("links") or []),
            "description": [str(b).strip() for b in (p.get("description") or []) if b],
        })

    return {
        "name": (tailored.get("name") or "Candidate").strip(),
        "tailored_title": (tailored.get("tailored_title") or "").strip(),
        "contact_line": _build_contact_line(tailored),
        "summary": (tailored.get("summary") or "").strip(),
        "skills": tailored.get("skills") or {},
        "projects": projects,
        "experience": tailored.get("experience") or [],
        "education": tailored.get("education") or [],
        "achievements": tailored.get("achievements") or [],
    }


def render_resume_pdf(
    tailored_json : dict[str, Any],
    output_path : str | None = None
) -> str:
    if not tailored_json:
        return ValueError("Cannot render empty tailored resume")
    
    template = _env.get_template("resume.html")
    context = _normalize_for_template(tailored_json)
    html = template.render(**context)
    
    if output_path is None:
        fname = f"resume{_safe_filename(context['name'])}.pdf"
        output_path = str(OUTPUT_DIR/fname)
    
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        doc = HTML(string=html).render()
        page_count = len(doc.pages)
        doc.write_pdf(str(out))
    except Exception as e:
        logger.error("Resume PDF render failed: %s", e)
        raise RuntimeError(f"Could not render PDF: {e}") from e

    size_kb = out.stat().st_size // 1020     
    logger.info("Wrote resume PDF: %s (%d pages, %d KB)", out,page_count,size_kb)
    
    # resume page warning only we not force resume in single page
    if page_count > MAX_RESUME_PAGES:
        logger.warning(
            "Resume is %d pages (soft max %d). Consider trimming.",
            page_count, MAX_RESUME_PAGES
        )
    
    return str(out)


def render_cover_letter_pdf(
    letter_text: str,
    candidate_name: str,
    output_path: str | None = None,
) -> str:
    if not letter_text or not letter_text.strip():
        raise ValueError("Cannot render empty cover letter")

    template = _env.get_template("cover_letter.html")
    html = template.render(
        letter_text=letter_text.strip(),
        candidate_name=candidate_name or "Candidate",
        date=datetime.now().strftime("%B %d, %Y"),
    )

    if output_path is None:
        fname = f"cover_letter_{_safe_filename(candidate_name)}.pdf"
        output_path = str(OUTPUT_DIR/fname)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        HTML(string=html).write_pdf(str(out))
    except Exception as e:
        logger.error("Cover letter PDF render failed: %s", e)
        raise RuntimeError(f"Could not render cover letter PDF: {e}") from e

    logger.info("Wrote cover letter PDF: %s (%d KB)", out, out.stat().st_size // 1024)
    return str(out)
 
import json
import logging

from app.db.queries import get_or_create_user, get_primary_resume
from app.db.session import get_session
from app.pipeline.generator import generate_tailored_resume
from app.pipeline.pdf_writer import render_resume_pdf, render_cover_letter_pdf

logging.basicConfig(level=logging.INFO)

# Backend JD — matches Rahul's RapidLink + URL-Shorten
jd_json = {
    "title": "Android + Backend Developer",
    "company": "Fintech Startup (Early Stage)",
    "required_skills": [
        "Kotlin",
        "Android",
        "Jetpack Compose",
        "FastAPI",
        "Python",
        "PostgreSQL",
        "REST API design",
    ],
    "preferred_skills": [
        "Docker",
        "Redis",
        "Firebase",
        "JWT authentication",
        "Retrofit",
    ],
    "responsibilities": [
        "Build and maintain the Android client using Kotlin and Jetpack Compose",
        "Design and implement REST APIs using FastAPI and PostgreSQL",
        "Integrate the mobile app with backend services (auth, payments, user data)",
        "Write unit tests for both Android components and backend endpoints",
        "Collaborate with designers and product on new feature specifications",
        "Debug production issues across the mobile and backend stack",
    ],
    "qualifications": [
        "0-2 years of experience in mobile or backend development",
        "Portfolio of personal or academic projects in Kotlin and Python",
        "Bachelor's degree in Computer Science or related field (or equivalent experience)",
    ],
}

with get_session() as db:
    user = get_or_create_user(db, "test@truthcv.com")
    resume = get_primary_resume(db, user.id)
    if resume is None:
        print("No primary resume. Upload one first.")
        raise SystemExit(1)     

    result = generate_tailored_resume(db, resume.id, jd_json)
    from app.pipeline.generator import generate_cover_letter
    letter = generate_cover_letter(db, resume.id, jd_json)
print(json.dumps(result, indent=2, ensure_ascii=False))

resume_path = render_resume_pdf(result)
print(f"\n✅ Resume PDF       : {resume_path}")

letter_path = render_cover_letter_pdf(letter, candidate_name=result.get("name", "Candidate"))
print(f"✅ Cover letter PDF : {letter_path}")

# 5. Also write an HTML preview
from pathlib import Path
from app.pipeline.pdf_writer import _env, _normalize_for_template

html = _env.get_template("resume.html").render(
    **_normalize_for_template(result)
)
preview_path = Path("output/resume_preview.html")
preview_path.parent.mkdir(exist_ok=True)
preview_path.write_text(html, encoding="utf-8")

print(f"\n🌐 HTML preview     : {preview_path.absolute()}")
print(f"\nOpen the files to check the output.")

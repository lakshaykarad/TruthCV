# scripts/test_scorer.py
import json
import logging

from app.db.queries import get_or_create_user, get_primary_resume
from app.db.session import get_session
from app.pipeline.scorer import score_match

logging.basicConfig(level=logging.INFO)

# A JD that MATCHES Aakriti's frontend profile
jd_json = {
    "title": "Frontend Engineer",
    "company": "Design Startup",
    "required_skills": ["React", "JavaScript", "HTML", "CSS"],
    "preferred_skills": ["Tailwind CSS", "Fabric.js", "Git"],
}

with get_session() as db:
    user = get_or_create_user(db, "test@truthcv.com")
    resume = get_primary_resume(db, user.id)

    report = score_match(db, resume.id, jd_json)

print(json.dumps(report, indent=2, ensure_ascii=False))
# scripts/test_db.py
from app.db.session import get_session, engine
from app.db.queries import (
    get_or_create_user,
    save_resume_with_chunks,
    get_primary_resume,
    get_chunks_for_user,
    save_application,
    get_applications,
)
from app.db.models import create_tables
create_tables(engine=engine)

with get_session() as db:
    user = get_or_create_user(db, "test@truthcv.com", "Test User")
    print(f"User id={user.id}")

    resume = save_resume_with_chunks(
        db,
        user_id=user.id,
        filename="dummy.pdf",
        raw_text="dummy text",
        json_data={"name": "Test"},
        chunks=[{
            "id": "abc123",
            "text": "Test chunk",
            "type": "skill",
            "metadata": {},
            "embedding": [0.0] * 384,
        }],
    )
    print(f"Resume id={resume.id}")

    primary = get_primary_resume(db, user.id)
    print(f"Primary resume id={primary.id if primary else None}")

    chunks = get_chunks_for_user(db, user.id)
    print(f"Chunks: {len(chunks)}")

    app = save_application(db, user.id, resume.id, "Google", "SDE-1")
    print(f"Application id={app.id}")

    apps = get_applications(db, user.id)
    print(f"Total applications: {len(apps)}")
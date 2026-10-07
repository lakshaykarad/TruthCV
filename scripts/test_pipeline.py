"""
Full pipeline test: PDF → text → JSON → chunks → embeddings → Postgres
Then verify the retriever and scorer work against the saved data.

Run:
    python -m scripts.test_pipeline resume.pdf
"""

import logging
import sys

from app.db.models import create_tables
from app.db.queries import (
    get_chunks_for_user,
    get_or_create_user,
    get_primary_resume,
    save_resume_with_chunks,
)
from app.db.session import engine, get_session
from app.pipeline.chunker import chunk_resume
from app.pipeline.embedder import embed_chunks
from app.pipeline.extractor import extract_resume_json
from app.pipeline.pdf_reader import read_pdf
from app.pipeline.retriever import find_similar_chunks_for_user
from app.pipeline.scorer import score_match

logging.basicConfig(level=logging.INFO)

# A sample JD used to test the scorer at the end
SAMPLE_JD = {
    "title": "Backend Engineer",
    "company": "Razorpay",
    "required_skills": ["Python", "FastAPI", "PostgreSQL", "Redis", "Docker"],
    "preferred_skills": ["AWS", "Kubernetes", "fintech"],
    "responsibilities": [
        "Design and build REST APIs for payment services",
        "Write unit and integration tests",
    ],
    "qualifications": ["2+ years of Python experience"],
}


def main(pdf_path: str, email: str = "test@truthcv.com") -> None:
    create_tables(engine)

    # ── INGESTION ────────────────────────────────────────────────
    print(f"\n[1/7] Reading PDF: {pdf_path}")
    raw_text = read_pdf(pdf_path)
    print(f"      Extracted {len(raw_text)} chars")

    print("[2/7] Extracting structured JSON")
    json_data = extract_resume_json(raw_text)
    print(f"      Name: {json_data.get('name')}")

    print("[3/7] Chunking")
    chunks = chunk_resume(json_data)
    print(f"      {len(chunks)} chunks")

    print("[4/7] Embedding")
    chunks = embed_chunks(chunks)
    print(f"      {len(chunks[0]['embedding'])} dims per chunk")

    print("[5/7] Saving to Postgres")
    with get_session() as db:
        user = get_or_create_user(db, email, "Test User")
        resume = save_resume_with_chunks(
            db,
            user_id=user.id,
            filename=pdf_path.split("/")[-1].split("\\")[-1],
            raw_text=raw_text,
            json_data=json_data,
            chunks=chunks,
            make_primary=True,
        )
        print(f"      user id       : {user.id}")
        print(f"      resume id     : {resume.id}")
        print(f"      chunks saved  : {len(chunks)}")

        # Keep references for the next steps
        user_id = user.id
        resume_id = resume.id

    # ── VERIFY SAVE ──────────────────────────────────────────────
    print("\n--- Fetched back ---")
    with get_session() as db:
        primary = get_primary_resume(db, user_id)
        fetched_chunks = get_chunks_for_user(db, user_id)
        print(f"primary resume id : {primary.id if primary else None}")
        print(f"chunks fetched    : {len(fetched_chunks)}")

        if fetched_chunks:
            sample = fetched_chunks[0]
            print(f"first chunk type  : {sample.chunk_type}")
            print(f"first chunk text  : {sample.text[:80]}...")
            print(f"embedding dims    : {len(sample.embedding)}")

    # ── RETRIEVER ────────────────────────────────────────────────
    print("\n[6/7] Testing retriever")
    test_queries = ["FastAPI", "Redis", "Docker"]   # change if needed for other resumes
    with get_session() as db:
        for q in test_queries:
            results = find_similar_chunks_for_user(db, user_id, q, top_k=3)
            print(f"\n  Query: {q!r} → {len(results)} chunks")
            for r in results:
                print(f"    [{r['score']:.3f}] ({r['type']}) {r['text'][:70]}...")

    # ── SCORER ───────────────────────────────────────────────────
    print("\n[7/7] Testing scorer")
    with get_session() as db:
        report = score_match(db, resume_id, SAMPLE_JD)

    print(f"\n  Match %: {report['required_skills_match_percent']}")
    print(f"  Apply? : {report['should_apply']}")
    print(f"  Matched: {[s['skill'] for s in report['required']['matched']]}")
    print(f"  Partial: {[s['skill'] for s in report['required']['partial']]}")
    print(f"  Missing: {[s['skill'] for s in report['required']['missing']]}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.test_pipeline <resume.pdf>")
        sys.exit(1)
    main(sys.argv[1])
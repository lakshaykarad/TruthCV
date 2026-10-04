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

logging.basicConfig(level=logging.INFO)

def main(pdf_path: str, email: str = "test@truthcv.com") -> None:
    
    create_tables(engine)
 
    print(f"\n[1/5] Reading PDF: {pdf_path}")
    raw_text = read_pdf(pdf_path)
    print(f"      Extracted {len(raw_text)} chars")
 
    print("[2/5] Extracting structured JSON")
    json_data = extract_resume_json(raw_text)
    print(f"      Name: {json_data.get('name')}")
 
    print("[3/5] Chunking")
    chunks = chunk_resume(json_data)
    print(f"      {len(chunks)} chunks")
 
    print("[4/5] Embedding")
    chunks = embed_chunks(chunks)
    print(f"      {len(chunks[0]['embedding'])} dims per chunk")
 
    print("[5/5] Saving to Postgres")
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

        print(f"\n--- Saved ---")
        print(f"user id       : {user.id}")
        print(f"resume id     : {resume.id}")
        print(f"chunks saved  : {len(chunks)}")
 
    print("\n--- Fetched back ---")
    with get_session() as db:
        user = get_or_create_user(db, email)
        primary = get_primary_resume(db, user.id)
        fetched_chunks = get_chunks_for_user(db, user.id)

        print(f"primary resume id : {primary.id if primary else None}")
        print(f"chunks fetched    : {len(fetched_chunks)}")

        if fetched_chunks:
            sample = fetched_chunks[0]
            print(f"\nFirst chunk:")
            print(f"  type      : {sample.chunk_type}")
            print(f"  text      : {sample.text[:80]}...")
            print(f"  embedding : {len(sample.embedding)} dims")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.test_pipeline <resume.pdf>")
        sys.exit(1)
    main(sys.argv[1])
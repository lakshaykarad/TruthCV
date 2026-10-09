from __future__ import annotations
from pathlib import Path
import logging
import tempfile

from fastapi import APIRouter, Depends, File, HTTPException,Query, UploadFile
from sqlalchemy.orm import Session

from app.db.queries import(
    get_primary_resume,
    get_or_create_user,
    soft_delete_resume,
    save_resume_with_chunks
)

from app.db.session import get_db 
from app.pipeline.pdf_reader import read_pdf
from app.pipeline.embedder import embed_chunks
from app.pipeline.extractor import extract_resume_json
from app.pipeline.chunker import chunk_resume
  
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resume", tags=["resume"])


MAX_FILE_SIZE = 10*2024*2024 # 10 MB max size 
DEFAULT_USER_EMAIL = "test@truthcv.com" 

@router.post("/upload")
async def upload(
    db : Session = Depends(get_db),
    file : UploadFile = File(...),
    email : str = Query(DEFAULT_USER_EMAIL)
) -> dict:
    
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")
    
    contents = await file.read()
    if not contents:
        HTTPException(status_code=400, detail="Empty file.")
        
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code="413", detail=f"File too large. {MAX_FILE_SIZE // (1024 * 1024)}MB.")
    
    # PyMuPDF can't read bytes. it need path to an actual file on disk
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(contents)
        tmp_path = tmp.name
    try: 
        logger.info("Upload stated: file%s, size=%d bytes", file.filename, len(contents))
        
        raw_text = read_pdf(tmp_path)
        
        if not raw_text.strip():
            raise HTTPException(status_code=400, detail="Could not extract text from PDF")
        
        json_data = extract_resume_json(raw_text)
        
        if not json_data:
            raise HTTPException(status_code=400, detail="Extractor returned empty JSON.")
        
        chunks = chunk_resume(json_data)
        if not chunks: # Unprocessable Content 
            raise HTTPException(status_code=422, detail="Chunker produced 0 chunks.")
        
        chunks = embed_chunks(chunks)
    
        user = get_or_create_user(db, email)
        resume = save_resume_with_chunks(db,
        user_id=user.id,
        filename = file.filename,
        raw_text=raw_text,
        json_data=json_data,
        chunks=chunks,
        make_primary=True)
        
        db.commit()
        
        return {
            "status" : "ok",
            "resume_id" : resume.id,
            "filename" : file.filename,
            "name" : json_data.get("name"),
            "email" : json_data.get("email"),
            "chunks" : len(chunks),
            "message" : "Resume uploaded and processed successfully",
        }
        
    except HTTPException:
        db.rollback()
        raise
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to process resume: {e}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)    
        
@router.get("/current")
def get_current_resume(
    email : str = Query(default=DEFAULT_USER_EMAIL),
    db: Session = Depends(get_db)
) ->dict:
    user = get_or_create_user(db, email)
    resume = get_primary_resume(db, user.id)
    
    if resume is None:
        raise HTTPException(status_code=404, detail="No primary resume. upload one first")
    
    return {
        "resume_id" : resume.id,
        "filename" : resume.filename,
        "uploaded_at" : resume.uploaded_at.isoformat() if resume.uploaded_at else None,
        "json_data" : resume.json_data
    }
    
@router.delete("/current")
def delete_current_resume(
    email : str = Query(default=DEFAULT_USER_EMAIL),
    db : Session = Depends(get_db)
) -> dict:
    user = get_or_create_user(db,email)
    resume = get_primary_resume(db, user.id)

    if resume is None:
        raise HTTPException(status_code=404, detail="No primary resume")
    
    resume_id = resume.id
    soft_delete_resume(db, user.id, resume_id)
    db.commit()
    
    return {
        "status" : "ok",
        "resume_id" : resume_id,
        "message" : "Resume deleted"
    }    
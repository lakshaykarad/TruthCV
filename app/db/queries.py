from __future__ import annotations

import hashlib
import logging
from typing import Any
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.db.models import Application, Chunk, Resume, User

logger = logging.getLogger(__name__)

# if email is match in db return it.
def get_user_by_email(db: Session, email: str) -> User | None: 
    return db.scalar(select(User).where(User.email == email))

# 
def create_user(db: Session, email: str, full_name: str | None = None) -> User:
    user = User(email=email, full_name=full_name)
    db.add(user)
    db.flush()   
    logger.info("Created user id=%s email=%s", user.id, email)
    return user

def get_or_create_user(db: Session, email: str, full_name: str | None = None) -> User:
    user = get_user_by_email(db, email)
    if user is not None:
        return user
    return create_user(db, email, full_name)
 
def hash_resume_text(raw_text: str) -> str: 
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


def find_duplicate_resume(db: Session, user_id: int, raw_text: str) -> Resume | None: 
    text_hash = hash_resume_text(raw_text)
    return db.scalar(
        select(Resume).where(
            Resume.user_id == user_id,
            Resume.text_hash == text_hash,
            Resume.is_deleted == False,    
        )
    )

def save_resume_with_chunks(
    db: Session,
    user_id: int,
    filename: str,
    raw_text: str,
    json_data: dict,
    chunks: list[dict[str, Any]],
    make_primary: bool = True,
) -> Resume:
   
    if make_primary:
        db.execute(
            update(Resume)
            .where(Resume.user_id == user_id, Resume.is_primary == True)  
            .values(is_primary=False)
        )

    resume = Resume(
        user_id=user_id,
        filename=filename,
        raw_text=raw_text,
        json_data=json_data,
        text_hash=hash_resume_text(raw_text),
        is_primary=make_primary,
    )
    db.add(resume)
    db.flush()  

    for chunk in chunks:
        db.add(
            Chunk(
                resume_id=resume.id,
                chunk_id=chunk["id"],
                text=chunk["text"],
                chunk_type=chunk["type"],
                chunk_metadata=chunk.get("metadata", {}),
                embedding=chunk["embedding"],
            )
        )

    logger.info(
        "Saved resume id=%s with %d chunks (primary=%s)",
        resume.id, len(chunks), make_primary,
    )
    return resume


def get_primary_resume(db: Session, user_id: int) -> Resume | None: 
    return db.scalar(
        select(Resume).where(
            Resume.user_id == user_id,
            Resume.is_primary == True,     
            Resume.is_deleted == False,    
        )
        .order_by(Resume.uploaded_at.desc())
        .limit(1)
    )


def get_all_resumes(db: Session, user_id: int) -> list[Resume]: 
    return list(
        db.scalars(
            select(Resume)
            .where(Resume.user_id == user_id, Resume.is_deleted == False)  
            .order_by(Resume.uploaded_at.desc())
        )
    )


def set_primary_resume(db: Session, user_id: int, resume_id: int) -> None: 
    db.execute(
        update(Resume)
        .where(Resume.user_id == user_id, Resume.is_primary == True)   
        .values(is_primary=False)
    )
    db.execute(
        update(Resume)
        .where(Resume.id == resume_id, Resume.user_id == user_id)
        .values(is_primary=True)
    )
    logger.info("User id=%s primary resume is now id=%s", user_id, resume_id)


def soft_delete_resume(db: Session, user_id: int, resume_id: int) -> None:
    db.execute(
        update(Resume)
        .where(Resume.id == resume_id, Resume.user_id == user_id)
        .values(is_deleted=True, is_primary=False)
    )
    logger.info("Soft-deleted resume id=%s (user=%s)", resume_id, user_id)

 
def get_chunks_for_resume(db: Session, resume_id: int) -> list[Chunk]:
  
    return list(
        db.scalars(select(Chunk).where(Chunk.resume_id == resume_id))
    )


def get_chunks_for_user(db: Session, user_id: int) -> list[Chunk]:
   
    resume = get_primary_resume(db, user_id)
    if resume is None:
        return []
    return get_chunks_for_resume(db, resume.id)
 
def save_application(
    db: Session,
    user_id: int,
    resume_id: int,
    company_name: str,
    role_title: str,
    status: str = "drafted",
) -> Application: 
    app = Application(
        user_id=user_id,
        resume_id=resume_id,
        company_name=company_name,
        role_title=role_title,
        status=status,
    )
    db.add(app)
    db.flush()
    logger.info(
        "Saved application id=%s user=%s company=%s",
        app.id, user_id, company_name,
    )
    return app


def get_applications(db: Session, user_id: int, limit: int = 50) -> list[Application]:
    
    return list(
        db.scalars(
            select(Application)
            .where(Application.user_id == user_id)
            .order_by(Application.applied_at.desc())
            .limit(limit)
        )
    )


def update_application_status(
    db: Session, application_id: int, new_status: str
) -> None: 
    db.execute(
        update(Application)
        .where(Application.id == application_id)
        .values(status=new_status)
    )
    logger.info("Application id=%s → status=%s", application_id, new_status)
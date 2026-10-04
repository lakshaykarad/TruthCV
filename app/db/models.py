from __future__ import annotations

import os
import logging
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import(  Boolean,DateTime,ForeignKey,Index,String,Text,func,)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import (DeclarativeBase,Mapped,mapped_column,relationship)

logger = logging.getLogger(__name__)

EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384"))

# When you delete the parent item, the child item is also deleted automatically

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id : Mapped[int] = mapped_column(primary_key=True)
    email : Mapped[str] = mapped_column(String(256), nullable=True) #at producation we can set it as false for testing it's ok to go with this.
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at : Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resumes : Mapped[list["Resume"]] = relationship(
        back_populates="user",cascade="all, delete-orphan"
    )
    applications : Mapped[list["Application"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"

 
class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    raw_text: Mapped[str] = mapped_column(Text)
    json_data: Mapped[dict] = mapped_column(JSONB)
 
    text_hash: Mapped[str] = mapped_column(String(64), index=True) 
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
 
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="resumes")
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )

    """ SELECT * FROM resumes 
        WHERE user_id = :user_id 
        AND is_primary = true 
        AND is_deleted = false;
    """
    
    __table_args__ = (
        Index("ix_resumes_user_primary", "user_id", "is_primary", "is_deleted"),
    )

    def __repr__(self) -> str:
        return f"<Resume id={self.id} file={self.filename!r} primary={self.is_primary}>"


 
class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    resume_id: Mapped[int] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[str] = mapped_column(String(32))  
    text: Mapped[str] = mapped_column(Text)
    chunk_type: Mapped[str] = mapped_column(String(50), index=True)
 
    chunk_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)

    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    resume: Mapped["Resume"] = relationship(back_populates="chunks")

    __table_args__ = (
        Index("ix_chunks_resume_type", "resume_id", "chunk_type"),
    )

    def __repr__(self) -> str:
        return f"<Chunk id={self.id} type={self.chunk_type} text={self.text[:40]!r}>"

 
class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    
    resume_id: Mapped[int] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"), index=True
    )

    company_name: Mapped[str] = mapped_column(String(255))
    role_title: Mapped[str] = mapped_column(String(255))
 
    status: Mapped[str] = mapped_column(String(50), default="drafted", index=True)

    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    user: Mapped["User"] = relationship(back_populates="applications")

    __table_args__ = (
        Index("ix_applications_user_date", "user_id", "applied_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Application id={self.id} company={self.company_name!r} "
            f"role={self.role_title!r}>"
        )


 
def create_tables(engine) -> None:
    """
    Create all tables if they don't exist. Safe to run repeatedly.
    For dev only. Deploy with Alembic migrations later.
    """
    try:
        Base.metadata.create_all(engine)
        logger.info("Tables ready: %s", list(Base.metadata.tables.keys()))
    except Exception as e:
        logger.error("Failed to create tables: %s", e)
        logger.error(
            "Common causes: pgvector extension not enabled, "
            "wrong DATABASE_URL, or Postgres not running"
        )
        raise

 
if __name__ == "__main__":
    from sqlalchemy import text

    from app.db.session import engine

    logging.basicConfig(level=logging.INFO)

    create_tables(engine)

    with engine.connect() as conn:
        tables = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' ORDER BY table_name"
            )
        ).fetchall()

    print("\nTables in 'truthcv' database:")
    for (name,) in tables:
        print(f"  - {name}")

    with engine.connect() as conn:
        col = conn.execute(
            text(
                "SELECT data_type, udt_name FROM information_schema.columns "
                "WHERE table_name='chunks' AND column_name='embedding'"
            )
        ).fetchone()

    if col:
        print(f"\nchunks.embedding → {col[0]} ({col[1]})")
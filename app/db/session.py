
from __future__ import annotations

import os, logging
from typing import Any, Iterator
from contextlib import contextmanager
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not found")

engine = create_engine(
    DATABASE_URL, pool_pre_ping=True, echo=False
)

SessionLocal  = sessionmaker(
    bind=engine,
    autoflush=False,  # don't auto-flush before quries 
    autocommit=False,      
    expire_on_commit=False
)

logging.info("DB engine created")

@contextmanager 
def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception: 
        session.rollback()
        raise
    finally:
        session.close()
        
def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try: 
        yield db
    finally:
        db.close()

 
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Just test that we can connect and run a trivial query
    from sqlalchemy import text

    with get_session() as db:
        result = db.execute(text("SELECT version();")).scalar()
        print(f"Connected. Postgres version:\n  {result}")

        result = db.execute(text("SELECT extversion FROM pg_extension WHERE extname='vector';")).scalar()
        print(f"pgvector version: {result}")

        result = db.execute(text("SELECT current_database();")).scalar()
        print(f"Current database: {result}")

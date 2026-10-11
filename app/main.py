from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db.models import create_tables
from app.db.session import engine
from app.routers import download, generate, health, resume 

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
 
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s", settings.app_name, settings.app_version)

    for key in ("database_url", "groq_api_key"):
        if not getattr(settings, key, None):
            logger.warning("Missing setting: %s", key)

    try:
        create_tables(engine)
        logger.info("Database tables ready.")
    except Exception as e:
        logger.error("Could not create tables: %s", e)

    yield

    logger.info("Shutting down %s", settings.app_name)
 
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Tailor your resume to any job description using RAG.",
    lifespan=lifespan,
)
 
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
 
app.include_router(health.router)
app.include_router(resume.router)
app.include_router(generate.router)
app.include_router(download.router)
 
app.mount(
    "/app",
    StaticFiles(directory="frontend", html=True),
    name="frontend",
)
 
@app.get("/")
def root() -> dict:
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
        "frontend": "/app/",
    }

 
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=True,
    )
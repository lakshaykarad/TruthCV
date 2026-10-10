from __future__ import annotations

import logging

import requests
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)) -> dict: 
    checks: dict[str, str] = {}
    try:
        result = db.execute(text("SELECT 1")).scalar()
        checks["database"] = "ok" if result == 1 else "fail"
    except Exception as e:
        logger.warning("Health: DB check failed: %s", e)
        checks["database"] = "fail"
 
    try:
        r = requests.get(f"{settings.ollama_host}/api/tags", timeout=3)
        checks["ollama"] = "ok" if r.status_code == 200 else "fail"
    except Exception as e:
        logger.warning("Health: Ollama check failed: %s", e)
        checks["ollama"] = "unreachable"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"

    return {
        "status": overall,
        "app": settings.app_name,
        "version": settings.app_version,
        "checks": checks,
    }
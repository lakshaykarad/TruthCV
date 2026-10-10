from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/download", tags=["download"])

_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9_\-\.]+\.pdf$")


@router.get("/{filename}")
def download_pdf(
    filename: str,
    inline: bool = Query(default=False, description="If true, preview in browser."),
) -> FileResponse:
    """
    Serve a generated PDF from the output directory.
    Rejects any filename that isn't a simple .pdf inside output/.
    """
    # ── Security: block path traversal ──
    if not _SAFE_FILENAME_RE.match(filename):
        raise HTTPException(status_code=400, detail="Invalid filename.")

    file_path = settings.output_dir / filename

    # Ensure resolved path is still inside OUTPUT_DIR
    try:
        file_path.resolve().relative_to(settings.output_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path.")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    disposition = "inline" if inline else "attachment"
    logger.info("Serving PDF: %s (%s)", filename, disposition)

    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=filename,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )
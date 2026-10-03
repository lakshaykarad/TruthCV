from pypdf import PdfReader
from pypdf.errors import PdfReadError
import logging
import re

logger = logging.getLogger(__name__)

# [('Google', 'https://google.com')]  without this -> Check out [Google](https://google.com) for searching.
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

def read_pdf(file_path: str) -> str:
    """Extract text from a PDF. Raises ValueError if unreadable."""
    try:
        reader = PdfReader(file_path)
    except PdfReadError as e:
        raise ValueError(f"Cannot read PDF: {e}") from e

    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except PdfReadError:
            raise ValueError("PDF is password-protected")

    pages_text: list[str] = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if not text.strip():
            logger.warning("Page %d returned empty text", i + 1)
        pages_text.append(text)

    full_text = "\n".join(pages_text)
 
    full_text = _MD_LINK_RE.sub(lambda m: m.group(2), full_text)

    if not full_text.strip():
        raise ValueError("No extractable text. PDF is likely scanned — needs OCR.")

    return full_text
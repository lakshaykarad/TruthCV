from pypdf import PdfReader
from pypdf.errors import PdfReadError
import logging
 
logger = logging.getLogger(__name__)
def read_pdf(file_path : str) -> str:
    "Extract text from a PDF. Raises ValueError if unreadable"
    try:
        reader = PdfReader(file_path)
    except PdfReadError as e:
        raise ValueError(f"Cannot read PDF: {e}")
    
    # check if pdf is encrypted
    if reader.is_encrypted: 
        try:
            reader.decrypt("")
        except PdfReadError as e:
            raise ValueError("PDF is password-protected")
    
    pages_text = []
    for i, page in enumerate(reader.pages) or " ":
        text = page.extract_text() or ""
        if not text.strip():
            logger.warning(f"Page {i+1} returned empty text")
        pages_text.append(text)
    
    full_text = "\n".join(pages_text).strip()
    
    if not full_text:
        raise ValueError("No extractable text. PDF is likely scanned — needs OCR.")
    
    return full_text
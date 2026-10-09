from pypdf import PdfReader
from pypdf.errors import PdfReadError
import logging
import pymupdf
import re
from pymupdf import Document, Page

logger = logging.getLogger(__name__)

# [('Google', 'https://google.com')]  without this -> Check out [Google](https://google.com) for searching.
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")




def _extract_hyperlinks(file_path : str) -> dict[int, list[str]]:
    
    result : dict[int, list[str]] = {}
    
    try:
        doc :Document = pymupdf.open(file_path)
    except Exception as e:
        logger.error("Pymupdf could not open PDF %s",e)
        return result
    
    page: Page
    for page_num, page in enumerate(doc, start=1):
        try:
            links = page.get_links()
        except Exception as e:
            logger.warning("get_links failed at page %d: %s", page_num, page)
            continue
    
        page_urls : list[str] = []
        for link in links:
            uri = link.get("uri")
            if not uri:
                continue
            uri : str = uri.strip()
            
            if not uri:continue
            
            if uri.lower().startswith(("mailto:", "tel:", "file:", "javascript:")):continue
            
            uri = re.sub(r"^https?://", "", uri)
            uri = uri.rstrip("/")
            if "." not in uri:
                continue
            page_urls.append(uri)

        if page_urls:
            result[page_num] = list(dict.fromkeys(page_urls))
        
    doc.close()
    return result
        
def read_pdf(file_path: str) -> str: 
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
    
    links_by_pages = _extract_hyperlinks(file_path)
    if links_by_pages:
        lines = ["", "[HYPERLINKS]"]
        for page_num in sorted(links_by_pages.keys()):
            for entry in links_by_pages[page_num]:
                lines.append(f"page:{page_num} | {entry}")
        lines.append("")
        lines.append("[RESUME]") 
        full_text = "\n".join(lines) + "\n" + full_text

    if not full_text.strip():
        raise ValueError("No extractable text. PDF is likely scanned — needs OCR.")
    
    return full_text

        
    
    
    
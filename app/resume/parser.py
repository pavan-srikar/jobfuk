import io
import pypdf
from typing import Optional

def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extracts raw text from PDF file bytes."""
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    extracted = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            extracted.append(text)
    return "\n\n".join(extracted).strip()

def extract_text_from_file_bytes(filename: str, content: bytes) -> str:
    """Extracts text based on file extension."""
    lower_name = filename.lower()
    if lower_name.endswith(".pdf"):
        return extract_text_from_pdf_bytes(content)
    else:
        # Default to UTF-8 decoded text
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return content.decode("latin-1", errors="ignore")

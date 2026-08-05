from io import BytesIO

from docx import Document
from pypdf import PdfReader


class ResumeTextMissingError(Exception):
    """The document is valid but has no useful embedded text."""


def extract_resume_text(data: bytes, media_type: str) -> str:
    if media_type == "application/pdf":
        reader = PdfReader(BytesIO(data))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    elif media_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        document = Document(BytesIO(data))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    else:
        raise ValueError("Unsupported resume media type")
    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if len(normalized) < 20:
        raise ResumeTextMissingError
    return normalized

"""Image OCR via Pillow + pytesseract (images only, never PDFs)."""

from __future__ import annotations

import io
import shutil
from pathlib import Path

import pytesseract
from PIL import Image

from app.ingestion.parsed_document import ParsedDocument

_WINDOWS_TESSERACT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")


def _configure_tesseract() -> None:
    """Prefer PATH; fall back to the common Windows install location."""
    if shutil.which("tesseract"):
        return
    if _WINDOWS_TESSERACT.is_file():
        pytesseract.pytesseract.tesseract_cmd = str(_WINDOWS_TESSERACT)


_configure_tesseract()


class OcrService:
    """OCR a single image into a ParsedDocument."""

    def ocr(self, data: bytes) -> ParsedDocument:
        image = Image.open(io.BytesIO(data))
        text = pytesseract.image_to_string(image) or ""
        text = text.strip()
        return ParsedDocument(
            text=text,
            tables=[],
            page_count=1,
            char_count=len(text),
        )

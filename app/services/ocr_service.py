"""Image OCR via Pillow + pytesseract (images only, never PDFs)."""

from __future__ import annotations

import io

import pytesseract
from PIL import Image

from app.ingestion.parsed_document import ParsedDocument


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

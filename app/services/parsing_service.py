"""PDF text/table extraction via pdfplumber"""

from __future__ import annotations

import io

import pdfplumber

from app.ingestion.parsed_document import ParsedDocument


class ParsingService:
    """Extract text and tables from native PDF bytes."""

    def parse(self, data: bytes) -> ParsedDocument:
        text_parts: list[str] = []
        tables: list[list[list[str]]] = []
        page_count = 0

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_parts.append(page_text)
                for table in page.extract_tables() or []:
                    normalized = [
                        [("" if cell is None else str(cell)).strip() for cell in row]
                        for row in table
                        if row
                    ]
                    if normalized:
                        tables.append(normalized)

        text = "\n".join(text_parts)
        return ParsedDocument(
            text=text,
            tables=tables,
            page_count=page_count,
            char_count=len(text),
        )

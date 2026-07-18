"""Route extraction by report_type."""

from __future__ import annotations

from pydantic import BaseModel

from app.ingestion.extractors.cbc import extract_cbc
from app.ingestion.extractors.echo import extract_echo
from app.ingestion.extractors.fields import ExtractedField
from app.ingestion.extractors.radiology import extract_radiology
from app.ingestion.extractors.ultrasound import extract_ultrasound
from app.ingestion.parsed_document import ParsedDocument


def extract(
    report_type: str, parsed: ParsedDocument
) -> tuple[BaseModel, dict[str, ExtractedField]]:
    match report_type:
        case "cbc":
            return extract_cbc(parsed)
        case "echo":
            return extract_echo(parsed)
        case "chest_radiology":
            return extract_radiology(parsed)
        case "renal_ultrasound":
            return extract_ultrasound(parsed)
        case _:
            raise ValueError(f"Unsupported report_type: {report_type}")

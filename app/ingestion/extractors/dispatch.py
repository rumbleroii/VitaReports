"""Dispatch extraction by report_type."""

from __future__ import annotations

from pydantic import BaseModel

from app.ingestion.extractors.cbc import extract_cbc
from app.ingestion.extractors.echo import extract_echo
from app.ingestion.extractors.fields import ExtractedField
from app.ingestion.extractors.radiology import extract_radiology
from app.ingestion.extractors.ultrasound import extract_ultrasound
from app.ingestion.parsed_document import ParsedDocument

_EXTRACTORS = {
    "cbc": extract_cbc,
    "echo": extract_echo,
    "chest_radiology": extract_radiology,
    "renal_ultrasound": extract_ultrasound,
}


def extract(
    report_type: str, parsed: ParsedDocument
) -> tuple[BaseModel, dict[str, ExtractedField]]:
    try:
        fn = _EXTRACTORS[report_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported report_type: {report_type}") from exc
    return fn(parsed)


def scored_field_names(report: BaseModel) -> list[str]:
    """Top-level schema fields used for match-rate scoring."""
    return list(report.model_fields.keys())

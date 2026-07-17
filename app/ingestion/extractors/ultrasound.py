"""Renal ultrasound report field extractor."""

from __future__ import annotations

from typing import Any

from app.ingestion.extractors.fields import (
    ExtractedField,
    find_field,
    find_section_body,
    impression_list,
)
from app.ingestion.extractors.synonyms import ULTRASOUND_SYNONYMS
from app.ingestion.parsed_document import ParsedDocument
from app.schemas.reports.ultrasound import RenalUltrasoundReport
from app.schemas.reports_common import KidneyFinding, NarrativeSection

_TEXT_FIELDS = (
    "facility",
    "department",
    "address",
    "patient_name",
    "mrn",
    "gender",
    "referring_physician",
    "referring_department",
    "clinical_indication",
    "technique",
    "comparison",
    "recommendation",
    "radiologist",
    "report_id",
)


def extract_ultrasound(
    parsed: ParsedDocument,
) -> tuple[RenalUltrasoundReport, dict[str, ExtractedField]]:
    confidences: dict[str, ExtractedField] = {}
    data: dict[str, Any] = {"impression": []}

    for name in _TEXT_FIELDS:
        hit = find_field(parsed, ULTRASOUND_SYNONYMS[name], value_kind="text")
        confidences[name] = hit
        data[name] = hit.value

    for name, kind in (
        ("date_of_birth", "date"),
        ("age_years", "int"),
        ("exam_date", "date"),
        ("report_date", "date"),
    ):
        hit = find_field(parsed, ULTRASOUND_SYNONYMS[name], value_kind=kind)
        confidences[name] = hit
        data[name] = hit.value

    for name in ("indication_creatinine", "indication_egfr", "indication_acr"):
        hit = find_field(parsed, ULTRASOUND_SYNONYMS[name], value_kind="quantitative")
        confidences[name] = hit
        data[name] = hit.value

    for kidney in ("right_kidney", "left_kidney"):
        section = find_section_body(parsed, ULTRASOUND_SYNONYMS[kidney])
        if section.value is None:
            section = find_field(parsed, ULTRASOUND_SYNONYMS[kidney], value_kind="text")
        confidences[kidney] = section
        if section.value:
            data[kidney] = KidneyFinding(body=str(section.value))
        else:
            data[kidney] = None

    for narr in ("renal_doppler", "urinary_bladder"):
        section = find_section_body(parsed, ULTRASOUND_SYNONYMS[narr])
        confidences[narr] = section
        if section.value:
            data[narr] = NarrativeSection(
                title=section.source_label or narr.replace("_", " ").title(),
                body=str(section.value),
            )
        else:
            data[narr] = None

    impression = impression_list(parsed)
    confidences["impression"] = impression
    data["impression"] = impression.value or []

    return RenalUltrasoundReport.model_validate(data), confidences

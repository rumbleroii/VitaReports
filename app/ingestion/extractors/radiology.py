"""Chest radiology report field extractor."""

from __future__ import annotations

from typing import Any

from app.ingestion.extractors.fields import (
    ExtractedField,
    find_field,
    find_section_body,
    impression_list,
)
from app.ingestion.extractors.synonyms import RADIOLOGY_SYNONYMS
from app.ingestion.parsed_document import ParsedDocument
from app.schemas.reports.radiology import ChestRadiologyReport

_TEXT_FIELDS = (
    "facility",
    "report_type",
    "mrn",
    "patient_name",
    "referring_dept",
    "clinical_dx",
    "test_name",
    "position",
    "exam_title",
    "clinical_indication",
    "comparison",
    "resident_radiologist",
    "consultant_radiologist",
    "printed_by",
    "page",
)


def extract_radiology(
    parsed: ParsedDocument,
) -> tuple[ChestRadiologyReport, dict[str, ExtractedField]]:
    confidences: dict[str, ExtractedField] = {}
    data: dict[str, Any] = {"impression": []}

    for name in _TEXT_FIELDS:
        hit = find_field(parsed, RADIOLOGY_SYNONYMS[name], value_kind="text")
        confidences[name] = hit
        data[name] = hit.value

    for name, kind in (
        ("referral_date", "date"),
        ("test_time", "datetime"),
        ("interpretation_time", "datetime"),
        ("cardiothoracic_ratio", "float"),
        ("cardiothoracic_ratio_prior", "float"),
        ("print_datetime", "datetime"),
    ):
        hit = find_field(parsed, RADIOLOGY_SYNONYMS[name], value_kind=kind)
        confidences[name] = hit
        data[name] = hit.value

    findings = find_section_body(parsed, RADIOLOGY_SYNONYMS["findings"])
    if findings.value is None:
        findings = find_field(parsed, RADIOLOGY_SYNONYMS["findings"], value_kind="text")
    confidences["findings"] = findings
    data["findings"] = findings.value

    impression = impression_list(parsed)
    confidences["impression"] = impression
    data["impression"] = impression.value or []

    return ChestRadiologyReport.model_validate(data), confidences

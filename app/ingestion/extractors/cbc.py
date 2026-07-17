"""CBC report field extractor."""

from __future__ import annotations

from typing import Any

from app.ingestion.extractors.fields import ExtractedField, find_field
from app.ingestion.extractors.synonyms import CBC_SYNONYMS
from app.ingestion.parsed_document import ParsedDocument
from app.schemas.reports.cbc import CbcReport

_QUANT_FIELDS = (
    "nucleated_rbc",
    "wbc",
    "rbc",
    "hemoglobin",
    "hematocrit",
    "mchc",
    "lymphocytes_abs",
    "platelets",
    "neutrophils_abs",
    "monocytes_abs",
    "eosinophils_abs",
    "basophils_abs",
)

_TEXT_FIELDS = ("facility", "report_title", "patient_name", "mrn", "test_id")


def extract_cbc(parsed: ParsedDocument) -> tuple[CbcReport, dict[str, ExtractedField]]:
    confidences: dict[str, ExtractedField] = {}
    data: dict[str, Any] = {"extra_results": []}

    for name in _TEXT_FIELDS:
        hit = find_field(parsed, CBC_SYNONYMS[name], value_kind="text")
        confidences[name] = hit
        data[name] = hit.value

    age = find_field(parsed, CBC_SYNONYMS["age_years"], value_kind="int")
    confidences["age_years"] = age
    data["age_years"] = age.value

    test_date = find_field(parsed, CBC_SYNONYMS["test_date"], value_kind="date")
    confidences["test_date"] = test_date
    data["test_date"] = test_date.value

    for name in _QUANT_FIELDS:
        hit = find_field(parsed, CBC_SYNONYMS[name], value_kind="quantitative")
        confidences[name] = hit
        data[name] = hit.value

    return CbcReport.model_validate(data), confidences

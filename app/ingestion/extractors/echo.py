"""Echo report field extractor."""

from __future__ import annotations

from typing import Any

from app.ingestion.extractors.fields import (
    ExtractedField,
    find_field,
    find_section_body,
    impression_list,
)
from app.ingestion.extractors.synonyms import ECHO_SYNONYMS
from app.ingestion.parsed_document import ParsedDocument
from app.schemas.reports.echo import EchoReport
from app.schemas.reports_common import NarrativeSection

_TEXT_FIELDS = (
    "facility",
    "department",
    "address",
    "report_title",
    "patient_name",
    "mrn",
    "sex",
    "referring_physician",
    "indication",
    "clinical_correlation",
    "signed_by",
    "report_id",
)

_QUANT_FIELDS = (
    "lvedd_mm",
    "lvesd_mm",
    "ivsd_mm",
    "pwd_mm",
    "ef_percent",
    "lv_mass_index",
    "la_diameter_mm",
    "la_volume_index",
    "ea_ratio",
    "ee_prime_lateral",
    "deceleration_time_ms",
    "tapse_mm",
    "rvsp_mmhg",
    "aortic_root_mm",
)


def extract_echo(parsed: ParsedDocument) -> tuple[EchoReport, dict[str, ExtractedField]]:
    confidences: dict[str, ExtractedField] = {}
    data: dict[str, Any] = {"findings_sections": [], "impression": []}

    for name in _TEXT_FIELDS:
        hit = find_field(parsed, ECHO_SYNONYMS[name], value_kind="text")
        confidences[name] = hit
        data[name] = hit.value

    for name, kind in (
        ("date_of_birth", "date"),
        ("age_years", "int"),
        ("bsa_m2", "float"),
        ("bmi", "float"),
        ("study_date", "date"),
        ("report_date", "date"),
    ):
        hit = find_field(parsed, ECHO_SYNONYMS[name], value_kind=kind)
        confidences[name] = hit
        data[name] = hit.value

    for name in _QUANT_FIELDS:
        hit = find_field(parsed, ECHO_SYNONYMS[name], value_kind="quantitative")
        confidences[name] = hit
        data[name] = hit.value

    findings = find_section_body(
        parsed, ["Findings", "FINDINGS", "Echo Findings", "Study Findings"]
    )
    confidences["findings_sections"] = findings
    if findings.value:
        data["findings_sections"] = [
            NarrativeSection(title="Findings", body=str(findings.value))
        ]

    impression = impression_list(parsed)
    confidences["impression"] = impression
    data["impression"] = impression.value or []

    return EchoReport.model_validate(data), confidences

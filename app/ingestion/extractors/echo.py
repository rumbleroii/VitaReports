"""Echo report field extractor (exact-label matching for Fakeeh-style reports)."""

from __future__ import annotations

import re
from typing import Any

from app.ingestion.extractors.fields import (
    ExtractedField,
    find_field,
    find_section_body,
    impression_list,
    normalize_label,
    parse_date_value,
    parse_float_value,
    parse_int_value,
    parse_quantitative,
)
from app.ingestion.extractors.synonyms import ECHO_SYNONYMS
from app.ingestion.parsed_document import ParsedDocument
from app.schemas.reports.echo import EchoReport
from app.schemas.reports_common import NarrativeSection

_HEADER_TEXT = (
    "patient_name",
    "mrn",
    "sex",
    "referring_physician",
    "indication",
    "clinical_correlation",
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

_FINDING_SUBSECTIONS = (
    "Left Ventricle",
    "Left Atrium",
    "Right Heart",
    "Valves",
    "Other",
)

_NUM_RE = re.compile(r"(-?\d+(?:[.,]\d+)?)")
_SIGNED_RE = re.compile(
    r"(?m)^\s*(Dr\.\s+[A-Za-z][A-Za-z.\- ]+,\s*(?:MD|MBBS|FACC|FACS|PhD)"
    r"(?:,\s*[A-Z]{2,})*)\s*$"
)


def _exact_synonym_hit(label: str, synonyms: list[str]) -> tuple[float, str] | None:
    norm = normalize_label(label)
    if not norm:
        return None
    for syn in synonyms:
        if norm == normalize_label(syn):
            return 1.0, syn
    return None


def _ordered_synonyms(synonyms: list[str]) -> list[str]:
    return sorted(synonyms, key=lambda s: len(normalize_label(s)), reverse=True)


def _find_echo_header(
    parsed: ParsedDocument,
    synonyms: list[str],
    *,
    value_kind: str,
) -> ExtractedField:
    """Header fields with day-first dates (Fakeeh DD/MM/YYYY)."""
    if value_kind == "date":
        hit = find_field(parsed, synonyms, value_kind="text", exact_only=True)
        if hit.value is None:
            return ExtractedField(value=None, confidence=0.0, source_label=None)
        parsed_date = parse_date_value(str(hit.value), dayfirst=True)
        return ExtractedField(
            value=parsed_date,
            confidence=hit.confidence if parsed_date is not None else 0.0,
            source_label=hit.source_label,
        )
    if value_kind == "int":
        hit = find_field(parsed, synonyms, value_kind="text", exact_only=True)
        if hit.value is None:
            return ExtractedField(value=None, confidence=0.0, source_label=None)
        parsed_int = parse_int_value(str(hit.value))
        return ExtractedField(
            value=parsed_int,
            confidence=hit.confidence if parsed_int is not None else 0.0,
            source_label=hit.source_label,
        )
    if value_kind == "float":
        hit = find_field(parsed, synonyms, value_kind="text", exact_only=True)
        if hit.value is None:
            return ExtractedField(value=None, confidence=0.0, source_label=None)
        parsed_float = parse_float_value(str(hit.value))
        return ExtractedField(
            value=parsed_float,
            confidence=hit.confidence if parsed_float is not None else 0.0,
            source_label=hit.source_label,
        )
    return find_field(parsed, synonyms, value_kind=value_kind, exact_only=True)


def _find_echo_quant(parsed: ParsedDocument, synonyms: list[str]) -> ExtractedField:
    ordered = _ordered_synonyms(synonyms)

    for table in parsed.tables:
        for row in table:
            if not row:
                continue
            label = (row[0] or "").strip()
            hit = _exact_synonym_hit(label, ordered)
            if not hit:
                continue
            confidence, source = hit
            raw = " ".join(cell for cell in row[1:] if cell).strip()
            value = parse_quantitative(raw)
            if value is not None:
                return ExtractedField(value=value, confidence=confidence, source_label=source)

    for line in parsed.text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        for syn in ordered:
            pattern = re.compile(rf"(?i)^\s*{re.escape(syn)}\s*[:\-–]?\s*(.*)$")
            m = pattern.match(stripped)
            if not m:
                continue
            raw = m.group(1).strip()
            if not raw:
                continue
            value = parse_quantitative(raw)
            if value is not None:
                return ExtractedField(value=value, confidence=1.0, source_label=syn)

        num_split = _NUM_RE.search(stripped)
        if not num_split:
            continue
        label_part = stripped[: num_split.start()].strip(" :-–\t")
        hit = _exact_synonym_hit(label_part, ordered)
        if not hit:
            continue
        confidence, source = hit
        raw = stripped[num_split.start() :].strip()
        value = parse_quantitative(raw)
        if value is not None:
            return ExtractedField(value=value, confidence=confidence, source_label=source)

    return ExtractedField(value=None, confidence=0.0, source_label=None)


def _extract_findings_sections(parsed: ParsedDocument) -> ExtractedField:
    body_hit = find_section_body(
        parsed, ["Findings", "FINDINGS", "Echo Findings", "Study Findings"]
    )
    if not body_hit.value:
        return ExtractedField(value=[], confidence=0.0, source_label=None)

    body = str(body_hit.value)
    sections: list[NarrativeSection] = []
    # Split on known subsection titles when present.
    pattern = re.compile(
        rf"(?i)\b({'|'.join(re.escape(s) for s in _FINDING_SUBSECTIONS)})\s*:\s*"
    )
    parts = pattern.split(body)
    if len(parts) >= 3:
        # parts: [preamble, title1, text1, title2, text2, ...]
        for i in range(1, len(parts) - 1, 2):
            title = parts[i].strip()
            text = parts[i + 1].strip()
            if text:
                sections.append(NarrativeSection(title=title, body=text))
    if not sections:
        sections = [NarrativeSection(title="Findings", body=body.strip())]

    return ExtractedField(
        value=sections,
        confidence=body_hit.confidence,
        source_label=body_hit.source_label,
    )


def _extract_signed_by(parsed: ParsedDocument) -> ExtractedField:
    m = _SIGNED_RE.search(parsed.text)
    if m:
        return ExtractedField(
            value=m.group(1).strip(), confidence=0.95, source_label="signature"
        )
    hit = find_field(
        parsed, ECHO_SYNONYMS["signed_by"], value_kind="text", exact_only=True
    )
    if hit.value:
        return hit
    return ExtractedField(value=None, confidence=0.0, source_label=None)


def _extract_facility_lines(parsed: ParsedDocument) -> tuple[ExtractedField, ExtractedField, ExtractedField]:
    lines = [ln.strip() for ln in parsed.text.splitlines() if ln.strip()]
    facility = ExtractedField(value=None, confidence=0.0, source_label=None)
    department = ExtractedField(value=None, confidence=0.0, source_label=None)
    title = ExtractedField(value=None, confidence=0.0, source_label=None)

    if lines:
        facility = ExtractedField(value=lines[0], confidence=0.9, source_label="header")
    if len(lines) > 1 and "cardiology" in lines[1].lower():
        department = ExtractedField(value=lines[1], confidence=0.9, source_label="header")

    title_hit = find_field(
        parsed, ECHO_SYNONYMS["report_title"], value_kind="text", exact_only=True
    )
    if title_hit.value:
        title = title_hit
    else:
        for ln in lines:
            if "echocardiogram" in ln.lower() and "report" in ln.lower():
                title = ExtractedField(value=ln, confidence=0.9, source_label="header")
                break

    return facility, department, title


def extract_echo(parsed: ParsedDocument) -> tuple[EchoReport, dict[str, ExtractedField]]:
    confidences: dict[str, ExtractedField] = {}
    data: dict[str, Any] = {"findings_sections": [], "impression": []}

    facility, department, report_title = _extract_facility_lines(parsed)
    confidences["facility"] = facility
    confidences["department"] = department
    confidences["report_title"] = report_title
    data["facility"] = facility.value
    data["department"] = department.value
    data["report_title"] = report_title.value

    for name in _HEADER_TEXT:
        hit = _find_echo_header(parsed, ECHO_SYNONYMS[name], value_kind="text")
        confidences[name] = hit
        data[name] = hit.value

    # Report ID often appears as ``Report ID: … | Page 1 of 1``
    if isinstance(data.get("report_id"), str) and "|" in data["report_id"]:
        data["report_id"] = data["report_id"].split("|", 1)[0].strip() or None

    for name, kind in (
        ("date_of_birth", "date"),
        ("age_years", "int"),
        ("bsa_m2", "float"),
        ("bmi", "float"),
        ("study_date", "date"),
        ("report_date", "date"),
    ):
        hit = _find_echo_header(parsed, ECHO_SYNONYMS[name], value_kind=kind)
        confidences[name] = hit
        data[name] = hit.value

    for name in _QUANT_FIELDS:
        hit = _find_echo_quant(parsed, ECHO_SYNONYMS[name])
        confidences[name] = hit
        data[name] = hit.value

    findings = _extract_findings_sections(parsed)
    confidences["findings_sections"] = findings
    data["findings_sections"] = findings.value or []

    impression = impression_list(parsed)
    confidences["impression"] = impression
    data["impression"] = impression.value or []

    signed = _extract_signed_by(parsed)
    confidences["signed_by"] = signed
    data["signed_by"] = signed.value

    return EchoReport.model_validate(data), confidences

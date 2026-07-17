"""Renal ultrasound report field extractor (SGH-style)."""

from __future__ import annotations

import re
from typing import Any

from app.ingestion.extractors.fields import (
    ExtractedField,
    find_field,
    impression_list,
    parse_date_value,
    parse_float_value,
    parse_int_value,
)
from app.ingestion.extractors.synonyms import ULTRASOUND_SYNONYMS
from app.ingestion.parsed_document import ParsedDocument
from app.schemas.reports.ultrasound import RenalUltrasoundReport
from app.schemas.reports_common import KidneyFinding, NarrativeSection, QuantitativeValue

_HEADER_TEXT = (
    "patient_name",
    "mrn",
    "gender",
    "referring_physician",
    "referring_department",
    "recommendation",
    "report_id",
)

_FINDING_PARTS = (
    "Right Kidney",
    "Left Kidney",
    "Renal Doppler",
    "Urinary Bladder",
)

_SIZE_RE = re.compile(
    r"(?i)Measures?\s+([\d.]+\s*x\s*[\d.]+\s*x\s*[\d.]+\s*cm)",
)
_BOSNIAK_RE = re.compile(
    r"(?i)Bosniak\s+(?:category\s+)?([IVX0-9]+)",
)
_CREAT_RE = re.compile(
    r"(?i)creatinine\s*\(?\s*([\d.]+)\s*(mg/dL)?",
)
_EGFR_RE = re.compile(
    r"(?i)eGFR\s*\(?\s*([\d.]+)\s*(mL/min(?:/1\.73m[²2])?)?",
)
_ACR_RE = re.compile(
    r"(?i)ACR\s*\)?\s*([\d.]+)\s*(mg/g)?",
)
_SIGNED_RE = re.compile(
    r"(?m)^\s*(Dr\.\s+[A-Za-z][A-Za-z.\- ]+,\s*(?:MD|MBBS|FRCR|FACC|FACS|PhD)"
    r"(?:,\s*[A-Z]{2,})*)\s*$"
)


def _find_us_header(
    parsed: ParsedDocument,
    synonyms: list[str],
    *,
    value_kind: str,
) -> ExtractedField:
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
    return find_field(parsed, synonyms, value_kind=value_kind, exact_only=True)


def _header_block(parsed: ParsedDocument) -> tuple[ExtractedField, ExtractedField, ExtractedField]:
    lines = [ln.strip() for ln in parsed.text.splitlines() if ln.strip()]
    facility = ExtractedField(value=None, confidence=0.0, source_label=None)
    department = ExtractedField(value=None, confidence=0.0, source_label=None)
    address = ExtractedField(value=None, confidence=0.0, source_label=None)
    if lines:
        facility = ExtractedField(value=lines[0], confidence=0.95, source_label="header")
    if len(lines) > 1 and "department" in lines[1].lower():
        department = ExtractedField(value=lines[1], confidence=0.95, source_label="header")
    if len(lines) > 2 and ("jeddah" in lines[2].lower() or "road" in lines[2].lower()):
        address = ExtractedField(value=lines[2], confidence=0.9, source_label="header")
    return facility, department, address


def _section_until(
    parsed: ParsedDocument,
    headings: list[str],
    stop_headings: list[str],
) -> ExtractedField:
    """Capture a labeled section until a stop heading (multi-line narratives)."""
    lines = parsed.text.splitlines()
    stop_norm = {h.lower().rstrip(":") for h in stop_headings}
    for i, line in enumerate(lines):
        stripped = line.strip().rstrip(":")
        for heading in headings:
            if stripped.lower() != heading.lower().rstrip(":"):
                continue
            body_lines: list[str] = []
            for nxt in lines[i + 1 :]:
                nxt_s = nxt.strip()
                if not nxt_s:
                    if body_lines:
                        # Keep blank lines inside a section; stop only on next heading.
                        continue
                    continue
                head = nxt_s.rstrip(":").lower()
                if head in stop_norm or any(
                    head.startswith(s.lower().rstrip(":")) for s in stop_headings
                ):
                    # Also stop when next finding subsection starts inline.
                    break
                # Inline subsection titles on findings lines
                if any(
                    nxt_s.lower().startswith(s.lower() + ":")
                    for s in _FINDING_PARTS
                ) and heading.lower() not in {"findings"}:
                    break
                body_lines.append(nxt_s)
            body = " ".join(body_lines).strip()
            # Drop leading page-noise digits like lone "2"
            body = re.sub(r"^\d+\s+", "", body)
            if body:
                return ExtractedField(value=body, confidence=1.0, source_label=heading)
    return ExtractedField(value=None, confidence=0.0, source_label=None)


def _split_findings(parsed: ParsedDocument) -> dict[str, ExtractedField]:
    findings = _section_until(
        parsed,
        ["Findings", "FINDINGS"],
        ["Impression", "IMPRESSION", "Recommendation", "Conclusion"],
    )
    out: dict[str, ExtractedField] = {
        "right_kidney": ExtractedField(value=None, confidence=0.0, source_label=None),
        "left_kidney": ExtractedField(value=None, confidence=0.0, source_label=None),
        "renal_doppler": ExtractedField(value=None, confidence=0.0, source_label=None),
        "urinary_bladder": ExtractedField(value=None, confidence=0.0, source_label=None),
    }
    if not findings.value:
        return out

    body = str(findings.value)
    pattern = re.compile(
        rf"(?i)\b({'|'.join(re.escape(s) for s in _FINDING_PARTS)})\s*:\s*"
    )
    parts = pattern.split(body)
    if len(parts) < 3:
        return out

    mapping = {
        "right kidney": "right_kidney",
        "left kidney": "left_kidney",
        "renal doppler": "renal_doppler",
        "urinary bladder": "urinary_bladder",
    }
    for i in range(1, len(parts) - 1, 2):
        title = parts[i].strip()
        text = parts[i + 1].strip()
        key = mapping.get(title.lower())
        if key and text:
            out[key] = ExtractedField(value=text, confidence=1.0, source_label=title)
    return out


def _kidney_from_text(text: str | None, source: str | None) -> KidneyFinding | None:
    if not text:
        return None
    size_m = _SIZE_RE.search(text)
    bosniak_m = _BOSNIAK_RE.search(text)
    return KidneyFinding(
        size_text=size_m.group(1).strip() if size_m else None,
        body=text.strip(),
        bosniak_category=bosniak_m.group(1).upper() if bosniak_m else None,
    )


def _quant_from_match(
    match: re.Match[str] | None,
    *,
    default_unit: str | None = None,
) -> ExtractedField:
    if not match:
        return ExtractedField(value=None, confidence=0.0, source_label=None)
    num = parse_float_value(match.group(1))
    unit = None
    if match.lastindex and match.lastindex >= 2:
        unit = match.group(2)
    unit = unit or default_unit
    if num is None:
        return ExtractedField(value=None, confidence=0.0, source_label=None)
    return ExtractedField(
        value=QuantitativeValue(
            value_num=num,
            value_text=match.group(0).strip(),
            unit=unit,
        ),
        confidence=0.95,
        source_label=match.group(0)[:40],
    )


def _extract_lab_hints(text: str) -> dict[str, ExtractedField]:
    return {
        "indication_creatinine": _quant_from_match(_CREAT_RE.search(text), default_unit="mg/dL"),
        "indication_egfr": _quant_from_match(
            _EGFR_RE.search(text), default_unit="mL/min/1.73m2"
        ),
        "indication_acr": _quant_from_match(_ACR_RE.search(text), default_unit="mg/g"),
    }


def _extract_radiologist(parsed: ParsedDocument) -> ExtractedField:
    m = _SIGNED_RE.search(parsed.text)
    if m:
        return ExtractedField(
            value=m.group(1).strip(), confidence=0.95, source_label="signature"
        )
    return ExtractedField(value=None, confidence=0.0, source_label=None)


def extract_ultrasound(
    parsed: ParsedDocument,
) -> tuple[RenalUltrasoundReport, dict[str, ExtractedField]]:
    confidences: dict[str, ExtractedField] = {}
    data: dict[str, Any] = {"impression": []}

    facility, department, address = _header_block(parsed)
    confidences["facility"] = facility
    confidences["department"] = department
    confidences["address"] = address
    data["facility"] = facility.value
    data["department"] = department.value
    data["address"] = address.value

    for name in _HEADER_TEXT:
        hit = _find_us_header(parsed, ULTRASOUND_SYNONYMS[name], value_kind="text")
        confidences[name] = hit
        data[name] = hit.value

    if isinstance(data.get("report_id"), str):
        rid = data["report_id"]
        # ``SGH-RAD-2026-04521 | Printed: …`` or embedded in a longer footer
        rid = rid.split("|")[0].strip()
        rid = re.sub(r"(?i)^.*?Report ID:\s*", "", rid).strip() or rid
        data["report_id"] = rid or None

    for name, kind in (
        ("date_of_birth", "date"),
        ("age_years", "int"),
        ("exam_date", "date"),
        ("report_date", "date"),
    ):
        hit = _find_us_header(parsed, ULTRASOUND_SYNONYMS[name], value_kind=kind)
        confidences[name] = hit
        data[name] = hit.value

    clinical = _section_until(
        parsed,
        ULTRASOUND_SYNONYMS["clinical_indication"],
        ["Technique", "Comparison", "Findings"],
    )
    confidences["clinical_indication"] = clinical
    data["clinical_indication"] = clinical.value

    technique = _section_until(
        parsed, ULTRASOUND_SYNONYMS["technique"], ["Comparison", "Findings"]
    )
    confidences["technique"] = technique
    data["technique"] = technique.value

    comparison = _section_until(
        parsed, ULTRASOUND_SYNONYMS["comparison"], ["Findings", "Impression"]
    )
    confidences["comparison"] = comparison
    data["comparison"] = comparison.value

    labs = _extract_lab_hints(parsed.text)
    for name, hit in labs.items():
        confidences[name] = hit
        data[name] = hit.value

    findings = _split_findings(parsed)
    rk = findings["right_kidney"]
    lk = findings["left_kidney"]
    confidences["right_kidney"] = rk
    confidences["left_kidney"] = lk
    data["right_kidney"] = _kidney_from_text(
        str(rk.value) if rk.value else None, rk.source_label
    )
    data["left_kidney"] = _kidney_from_text(
        str(lk.value) if lk.value else None, lk.source_label
    )

    for narr in ("renal_doppler", "urinary_bladder"):
        hit = findings[narr]
        confidences[narr] = hit
        if hit.value:
            data[narr] = NarrativeSection(
                title=hit.source_label or narr.replace("_", " ").title(),
                body=str(hit.value),
            )
        else:
            data[narr] = None

    impression_body = _section_until(
        parsed,
        ["Impression", "IMPRESSION"],
        ["Recommendation", "Advice"],
    )
    if impression_body.value:
        items = [
            part.strip(" -•\t")
            for part in re.split(r"[\n;]|•|\d+\.\s+", str(impression_body.value))
            if part.strip(" -•\t")
        ]
        impression = ExtractedField(
            value=items or [str(impression_body.value)],
            confidence=impression_body.confidence,
            source_label=impression_body.source_label,
        )
    else:
        impression = impression_list(parsed)
    confidences["impression"] = impression
    data["impression"] = impression.value or []

    # Recommendation may be a labeled line or short section
    if not data.get("recommendation"):
        rec = _find_us_header(
            parsed, ULTRASOUND_SYNONYMS["recommendation"], value_kind="text"
        )
        if not rec.value:
            rec = _section_until(
                parsed,
                ULTRASOUND_SYNONYMS["recommendation"],
                ["Dr.", "Page", "Report ID", "Electronically"],
            )
        confidences["recommendation"] = rec
        data["recommendation"] = rec.value

    signed = _extract_radiologist(parsed)
    confidences["radiologist"] = signed
    data["radiologist"] = signed.value

    return RenalUltrasoundReport.model_validate(data), confidences

"""CBC report field extractor (exact-label matching for KAUH-style panels)."""

from __future__ import annotations

import re
from typing import Any

from app.ingestion.extractors.fields import (
    ExtractedField,
    find_field,
    normalize_label,
    parse_date_value,
    parse_int_value,
    parse_quantitative,
)
from app.ingestion.extractors.synonyms import CBC_SYNONYMS
from app.ingestion.parsed_document import ParsedDocument
from app.schemas.reports.cbc import CbcReport

_HEADER_TEXT_FIELDS = ("patient_name", "test_id")

_QUANT_FIELDS = (
    "nucleated_rbc",
    "wbc",
    "rbc",
    "hemoglobin",
    "hematocrit",
    "mchc",
    "lymphocytes_abs",
    "mcv",
    "platelets",
    "monocytes_pct",
    "eosinophils_pct",
    "neutrophils_abs",
    "monocytes_abs",
    "eosinophils_abs",
    "mch",
    "lymphocytes_pct",
    "pdw",
    "pct",
    "neutrophils_pct",
    "rdw_cv",
    "p_lcr",
    "ig_pct",
    "ig_abs",
    "basophils_pct",
    "basophils_abs",
    "mpv",
)

_NUM_RE = re.compile(r"(-?\d+(?:[.,]\d+)?)")


def _exact_synonym_hit(label: str, synonyms: list[str]) -> tuple[float, str] | None:
    """Exact normalized label match only (no fuzzy containment)."""
    norm = normalize_label(label)
    if not norm:
        return None
    for syn in synonyms:
        if norm == normalize_label(syn):
            return 1.0, syn
    return None


def _ordered_synonyms(synonyms: list[str]) -> list[str]:
    return sorted(synonyms, key=lambda s: len(normalize_label(s)), reverse=True)


def _find_cbc_header(
    parsed: ParsedDocument,
    synonyms: list[str],
    *,
    value_kind: str,
) -> ExtractedField:
    """Header fields: exact label match; day-first dates for KAUH PDFs."""
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


def _find_cbc_quant(parsed: ParsedDocument, synonyms: list[str]) -> ExtractedField:
    """Find a CBC analyte by exact label in tables, then text lines."""
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

        # Label may carry trailing punctuation the synonym omits (e.g. "HCT)-").
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


def extract_cbc(parsed: ParsedDocument) -> tuple[CbcReport, dict[str, ExtractedField]]:
    confidences: dict[str, ExtractedField] = {}
    data: dict[str, Any] = {"extra_results": []}

    for name in _HEADER_TEXT_FIELDS:
        hit = _find_cbc_header(parsed, CBC_SYNONYMS[name], value_kind="text")
        confidences[name] = hit
        data[name] = hit.value

    age = _find_cbc_header(parsed, CBC_SYNONYMS["age_years"], value_kind="int")
    confidences["age_years"] = age
    data["age_years"] = age.value

    test_date = _find_cbc_header(parsed, CBC_SYNONYMS["test_date"], value_kind="date")
    confidences["test_date"] = test_date
    data["test_date"] = test_date.value

    for name in _QUANT_FIELDS:
        hit = _find_cbc_quant(parsed, CBC_SYNONYMS[name])
        confidences[name] = hit
        data[name] = hit.value

    return CbcReport.model_validate(data), confidences

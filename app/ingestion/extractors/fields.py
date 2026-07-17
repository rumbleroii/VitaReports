"""Shared field extraction helpers (synonym + regex)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from dateutil import parser as date_parser

from app.ingestion.parsed_document import ParsedDocument
from app.schemas.reports_common import QuantitativeValue

_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


@dataclass
class ExtractedField:
    value: object | None
    confidence: float
    source_label: str | None = None


def normalize_label(text: str) -> str:
    return _NORMALIZE_RE.sub("", (text or "").lower())


def _match_synonym(
    label: str,
    synonyms: list[str],
    *,
    exact_only: bool = False,
) -> tuple[float, str] | None:
    norm = normalize_label(label)
    if not norm:
        return None
    # Prefer longest exact match first (MCHC before MCH, etc.).
    ordered = sorted(synonyms, key=lambda s: len(normalize_label(s)), reverse=True)
    for syn in ordered:
        syn_norm = normalize_label(syn)
        if not syn_norm:
            continue
        if norm == syn_norm:
            return 1.0, syn
    if exact_only:
        return None
    for syn in ordered:
        syn_norm = normalize_label(syn)
        if not syn_norm:
            continue
        if syn_norm in norm or norm in syn_norm:
            return 0.85, syn
    return None


_VALUE_RE = re.compile(
    r"(?P<num>-?\d+(?:[.,]\d+)?)\s*(?P<unit>[a-zA-Z%/µμ^0-9.]*)?"
)
_RANGE_RE = re.compile(
    r"(?P<low>-?\d+(?:[.,]\d+)?)\s*[-–—to]+\s*(?P<high>-?\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
_ONE_SIDED_RANGE_RE = re.compile(
    r"(?P<op>[<>≤≥]=?)\s*(?P<bound>-?\d+(?:[.,]\d+)?)"
)
_FLAG_RE = re.compile(r"\b([HLhl]|High|Low)\b")


def parse_quantitative(raw: str) -> QuantitativeValue | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    cleaned = raw.replace(",", "")
    match = _VALUE_RE.search(cleaned)
    if not match:
        return QuantitativeValue(value_text=raw)
    num_s = match.group("num").replace(",", "")
    try:
        value_num = float(num_s)
    except ValueError:
        return QuantitativeValue(value_text=raw)
    unit = (match.group("unit") or "").strip() or None
    # Drop units that are really the start of a reference range token noise.
    if unit and unit in {"-", "–", "—", "<", ">", "≤", "≥"}:
        unit = None
    reference_range = None
    after = cleaned[match.end() :]
    range_m = _RANGE_RE.search(after) or _RANGE_RE.search(cleaned)
    if range_m:
        low = range_m.group("low")
        high = range_m.group("high")
        reference_range = f"{low} - {high}"
    else:
        one = _ONE_SIDED_RANGE_RE.search(after)
        if one:
            reference_range = f"{one.group('op')} {one.group('bound')}"
    flag_m = _FLAG_RE.search(raw)
    flag = flag_m.group(1).upper()[:1] if flag_m else None
    return QuantitativeValue(
        value_num=value_num,
        value_text=raw,
        unit=unit,
        reference_range=reference_range,
        flag=flag,
    )


def parse_date_value(raw: str, *, dayfirst: bool = False) -> date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return date_parser.parse(raw, dayfirst=dayfirst, fuzzy=True).date()
    except (ValueError, OverflowError, TypeError):
        return None


def parse_datetime_value(raw: str, *, dayfirst: bool = False) -> datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return date_parser.parse(raw, dayfirst=dayfirst, fuzzy=True)
    except (ValueError, OverflowError, TypeError):
        return None


def parse_int_value(raw: str) -> int | None:
    match = re.search(r"-?\d+", raw or "")
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def parse_float_value(raw: str) -> float | None:
    match = re.search(r"-?\d+(?:[.,]\d+)?", (raw or "").replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


# Labels that may share a header line (stop value capture before these).
# Allow `` | Age: `` and `` (Age: `` style separators.
_INLINE_HEADER_STOP = re.compile(
    r"(?:\s*\|\s*|\s+)\(?(?:"
    r"Name|Patient(?:\s+Name)?|MRN|Medical\s+Record(?:\s+Number|\s+No)?|"
    r"Age(?:\s*\([^)]*\))?|Test(?:\s+Date|\s+ID|\s+Name|\s+No|\s+Number)?|"
    r"DOB|Date(?:\s+of\s+Birth)?|Sex|Gender|BSA|BMI|"
    r"Facility|Hospital|File\s+No|Patient\s+ID|"
    r"Referring(?:\s+Physician|\s+Doctor|\s+Dept|\s+Department)?|"
    r"Indication|Clinical\s+Indication|"
    r"Study\s+Date|Exam\s+Date|Collection\s+Date|Report\s+Date|"
    r"Report\s+ID|Page|Department|Printed"
    r")\s*[:\-–]",
    re.IGNORECASE,
)


def _line_value_after_label(line: str, synonym: str) -> str | None:
    """Match ``Label: value``, including mid-line pairs on dense headers.

    Value runs until the next known header label (``Age:``, ``Test Date:``, …)
    or end of line — so ``MRN: … Age: 55 Test Date: 01/04/2026`` works, while
    multi-word patient names are not truncated.
    """
    pattern = re.compile(
        rf"(?i)(?:^|(?<=[\s|(])){re.escape(synonym)}\s*[:\-–]\s*(?P<value>.+)$"
    )
    m = pattern.search(line)
    if not m:
        pattern_loose = re.compile(
            rf"(?i)(?:^|(?<=[\s|(])){re.escape(synonym)}\s+(?P<value>\S.+)$"
        )
        m = pattern_loose.search(line)
        if not m:
            return None
    raw = m.group("value").strip().rstrip(")")
    stop = _INLINE_HEADER_STOP.search(raw)
    if stop:
        raw = raw[: stop.start()].strip()
    return raw or None


def find_field(
    parsed: ParsedDocument,
    synonyms: list[str],
    *,
    value_kind: str = "text",
    exact_only: bool = False,
) -> ExtractedField:
    """Find a field by synonym labels in tables first, then text lines."""

    ordered = sorted(synonyms, key=lambda s: len(normalize_label(s)), reverse=True)

    # 1) Table rows: first cell = label, rest = value; also inline ``Label: value`` cells
    for table in parsed.tables:
        for row in table:
            if not row:
                continue
            label = row[0]
            hit = _match_synonym(label, synonyms, exact_only=exact_only)
            if hit:
                confidence, source = hit
                raw = " ".join(cell for cell in row[1:] if cell).strip()
                value = _coerce(raw, value_kind)
                if value is None and raw:
                    value = raw if value_kind == "text" else _coerce(raw, value_kind)
                if value is not None:
                    return ExtractedField(
                        value=value, confidence=confidence, source_label=source
                    )

            for cell in row:
                if not cell:
                    continue
                for syn in ordered:
                    raw = _line_value_after_label(cell.strip(), syn)
                    if raw is None:
                        continue
                    value = _coerce(raw, value_kind)
                    if value is not None:
                        return ExtractedField(
                            value=value, confidence=1.0, source_label=syn
                        )

    # 2) Text lines with synonym match (longest synonyms first)
    lines = parsed.text.splitlines()
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        for syn in ordered:
            raw = _line_value_after_label(stripped, syn)
            if raw is None:
                label_part = stripped.split(":")[0]
                hit = _match_synonym(label_part, [syn], exact_only=exact_only)
                if not hit:
                    continue
                confidence, source = hit
                parts = re.split(r"[:\-–]", stripped, maxsplit=1)
                if len(parts) < 2:
                    continue
                raw = parts[1].strip()
                stop = _INLINE_HEADER_STOP.search(raw)
                if stop:
                    raw = raw[: stop.start()].strip()
                value = _coerce(raw, value_kind)
                if value is not None:
                    return ExtractedField(
                        value=value, confidence=confidence, source_label=source
                    )
                continue

            value = _coerce(raw, value_kind)
            if value is not None:
                return ExtractedField(value=value, confidence=1.0, source_label=syn)

    # 3) Regex-only fallback: any synonym as label pattern anywhere
    if not exact_only:
        for syn in ordered:
            pattern = re.compile(
                rf"(?im){re.escape(syn)}\s*[:\-–]?\s*(.+?)(?:\n|$)"
            )
            m = pattern.search(parsed.text)
            if not m:
                continue
            raw = m.group(1).strip()
            value = _coerce(raw, value_kind)
            if value is not None:
                return ExtractedField(value=value, confidence=0.75, source_label=syn)

    return ExtractedField(value=None, confidence=0.0, source_label=None)


def _coerce(raw: str, value_kind: str) -> object | None:
    if value_kind == "quantitative":
        return parse_quantitative(raw)
    if value_kind == "date":
        return parse_date_value(raw)
    if value_kind == "datetime":
        return parse_datetime_value(raw)
    if value_kind == "int":
        return parse_int_value(raw)
    if value_kind == "float":
        return parse_float_value(raw)
    if value_kind == "text":
        text = (raw or "").strip()
        return text or None
    return (raw or "").strip() or None


def find_section_body(parsed: ParsedDocument, headings: list[str]) -> ExtractedField:
    """Capture narrative body following a section heading until the next heading-like line."""
    lines = parsed.text.splitlines()
    for i, line in enumerate(lines):
        hit = _match_synonym(line.strip().rstrip(":"), headings)
        if not hit:
            continue
        confidence, source = hit
        body_lines: list[str] = []
        for nxt in lines[i + 1 :]:
            nxt_s = nxt.strip()
            if not nxt_s:
                if body_lines:
                    break
                continue
            # Stop at another short ALL-CAPS / Title heading
            if len(nxt_s) < 40 and (
                nxt_s.isupper() or nxt_s.rstrip(":").istitle()
            ):
                break
            body_lines.append(nxt_s)
        body = " ".join(body_lines).strip()
        if body:
            return ExtractedField(value=body, confidence=confidence, source_label=source)
    return ExtractedField(value=None, confidence=0.0, source_label=None)


def impression_list(parsed: ParsedDocument, headings: list[str] | None = None) -> ExtractedField:
    headings = headings or ["Impression", "IMPRESSION", "Conclusion"]
    found = find_section_body(parsed, headings)
    if found.value is None:
        return ExtractedField(value=[], confidence=0.0, source_label=None)
    items = [
        part.strip(" -•\t")
        for part in re.split(r"[\n;]|•|\d+\.\s+", str(found.value))
        if part.strip(" -•\t")
    ]
    if not items:
        items = [str(found.value)]
    return ExtractedField(
        value=items, confidence=found.confidence, source_label=found.source_label
    )

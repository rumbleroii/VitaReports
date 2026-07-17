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


def _match_synonym(label: str, synonyms: list[str]) -> tuple[float, str] | None:
    norm = normalize_label(label)
    if not norm:
        return None
    for syn in synonyms:
        syn_norm = normalize_label(syn)
        if not syn_norm:
            continue
        if norm == syn_norm:
            return 1.0, syn
        if syn_norm in norm or norm in syn_norm:
            return 0.85, syn
    return None


_VALUE_RE = re.compile(
    r"(?P<num>-?\d+(?:[.,]\d+)?)\s*(?P<unit>[a-zA-Z%/µμ^0-9.]*)?"
)
_FLAG_RE = re.compile(r"\b([HLhl]|High|Low)\b")


def parse_quantitative(raw: str) -> QuantitativeValue | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    match = _VALUE_RE.search(raw.replace(",", ""))
    if not match:
        return QuantitativeValue(value_text=raw)
    num_s = match.group("num").replace(",", "")
    try:
        value_num = float(num_s)
    except ValueError:
        return QuantitativeValue(value_text=raw)
    unit = (match.group("unit") or "").strip() or None
    flag_m = _FLAG_RE.search(raw)
    flag = flag_m.group(1).upper()[:1] if flag_m else None
    return QuantitativeValue(value_num=value_num, value_text=raw, unit=unit, flag=flag)


def parse_date_value(raw: str) -> date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return date_parser.parse(raw, dayfirst=False, fuzzy=True).date()
    except (ValueError, OverflowError, TypeError):
        return None


def parse_datetime_value(raw: str) -> datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return date_parser.parse(raw, dayfirst=False, fuzzy=True)
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


def _line_value_after_label(line: str, synonym: str) -> str | None:
    # Match "Label: value" or "Label  value" on the same line.
    pattern = re.compile(
        rf"(?i)(?:^|[\s|]){re.escape(synonym)}\s*[:\-–]?\s*(.+)$"
    )
    m = pattern.search(line)
    if m:
        return m.group(1).strip()
    return None


def find_field(
    parsed: ParsedDocument,
    synonyms: list[str],
    *,
    value_kind: str = "text",
) -> ExtractedField:
    """Find a field by synonym labels in tables first, then text lines."""

    # 1) Table rows: first cell = label, rest = value
    for table in parsed.tables:
        for row in table:
            if not row:
                continue
            label = row[0]
            hit = _match_synonym(label, synonyms)
            if not hit:
                continue
            confidence, source = hit
            raw = " ".join(cell for cell in row[1:] if cell).strip()
            value = _coerce(raw, value_kind)
            if value is None and raw:
                value = raw if value_kind == "text" else _coerce(raw, value_kind)
            if value is not None:
                return ExtractedField(value=value, confidence=confidence, source_label=source)

    # 2) Text lines with synonym match
    lines = parsed.text.splitlines()
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        for syn in synonyms:
            raw = _line_value_after_label(stripped, syn)
            if raw is None:
                # Also try normalized containment on the line start
                hit = _match_synonym(stripped.split(":")[0], [syn])
                if not hit:
                    continue
                confidence, source = hit
                parts = re.split(r"[:\-–]", stripped, maxsplit=1)
                if len(parts) < 2:
                    continue
                raw = parts[1].strip()
                value = _coerce(raw, value_kind)
                if value is not None:
                    return ExtractedField(
                        value=value, confidence=confidence, source_label=source
                    )
                continue

            hit = _match_synonym(syn, synonyms)
            confidence = 1.0 if hit and hit[0] == 1.0 else 0.85
            # Prefer exact synonym used in the regex
            exact = normalize_label(syn) == normalize_label(
                stripped[: len(syn)] if len(stripped) >= len(syn) else stripped
            )
            if exact:
                confidence = 1.0
            elif confidence < 0.85:
                confidence = 0.85
            value = _coerce(raw, value_kind)
            if value is not None:
                return ExtractedField(value=value, confidence=confidence, source_label=syn)

    # 3) Regex-only fallback: any synonym as label pattern anywhere
    for syn in synonyms:
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

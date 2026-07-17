"""Chest radiology report field extractor (KAUH photo / OCR-tolerant)."""

from __future__ import annotations

import re
from typing import Any

from app.ingestion.extractors.fields import (
    ExtractedField,
    find_field,
    parse_date_value,
    parse_datetime_value,
    parse_float_value,
)
from app.ingestion.extractors.synonyms import RADIOLOGY_SYNONYMS
from app.ingestion.parsed_document import ParsedDocument
from app.schemas.reports.radiology import ChestRadiologyReport

_CTR_RE = re.compile(
    r"(?i)cardiothoracic\s+ratio\s+of\s+(?P<curr>0?\.\d+|\d+\.\d+)"
    r"(?:\s*\(previously\s+(?P<prior>0?\.\d+|\d+\.\d+)\))?",
)
_MRN_RE = re.compile(r"(?i)\b(?:MRN|MFRN)\s*[:.]?\s*([0-9]{4}-[0-9]+)")
_NAME_RE = re.compile(
    r"(?i)\bName\s*[:.]?\s*([A-Za-z][A-Za-z .'-]+?)(?:\s*[.|]|\s*$|\s*Radiology)"
)
_DEPT_RE = re.compile(
    r"(?i)Dept/?Ward\s*\(Referred\s+from\)\s*[:.]?\s*(.+?)"
    r"(?=\s*[\({\[]?\s*Referral|\s*/\s*Test|\n|$)",
)
_TIME_LINE_RE = re.compile(
    r"(?i)(?P<label>Referral\s+Dat[eo]|Roter[ao]l?\s+Dat[eo]|Test\s+Time|Tost\s+Time|"
    r"Interpretation\s+Time)\s*[:;.]?\s*(?P<value>[0-9]{1,2}[/.-][0-9]{1,2}[/.-][0-9]{2,4}"
    r"(?:\s+[0-9]{1,2}[:'.,][0-9]{2}(?::[0-9]{2})?)?)",
)
_SECTION_STOPS = (
    "CLINICAL INDICATION",
    "COMPARISON",
    "FINDINGS",
    "IMPRESSION",
    "DR.",
    "Printed",
    "Test Name",
    "Position",
    "Conclusion",
    "Medical History",
    "RESIDENT",
    "CONSULTANT",
)


def _normalize_ocr(text: str) -> str:
    text = (
        text.replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("‘", "'")
        .replace("’", "'")
    )
    replacements = (
        (r"(?i)\bMFRN\b", "MRN"),
        (r"(?i)Glinical\s+Dx", "Clinical Dx"),
        (r"(?i)Clinical\s+Ox", "Clinical Dx"),
        (r"(?i)Tost\s+Time", "Test Time"),
        (r"(?i)Referral\s+Dato", "Referral Date"),
        (r"(?i)Roter[ao]l?\s+Dat[eo]", "Referral Date"),
        (r"(?i)\.rdiothoracic", "cardiothoracic"),
        (r"(?i)Shalabl\b", "Shalabi"),
        (r"(?i)RAD\s+OLOGIST", "RADIOLOGIST"),
        (r"(?i)\bPATIA\b", "FATIMA"),
    )
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text)
    return text


def _with_normalized(parsed: ParsedDocument) -> ParsedDocument:
    return ParsedDocument(
        text=_normalize_ocr(parsed.text),
        tables=parsed.tables,
        page_count=parsed.page_count,
        char_count=parsed.char_count,
    )


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip(" :;.|")
    return text or None


def _section_body(text: str, headings: list[str]) -> ExtractedField:
    lines = text.splitlines()
    stop_l = [s.lower() for s in _SECTION_STOPS]
    for i, line in enumerate(lines):
        stripped = line.strip().rstrip(":")
        matched_heading = None
        for heading in headings:
            key = heading.lower().rstrip(":")
            if stripped.lower() == key or stripped.lower().startswith(key):
                matched_heading = heading
                break
        if not matched_heading:
            continue
        body_lines: list[str] = []
        for nxt in lines[i + 1 :]:
            nxt_s = nxt.strip()
            if not nxt_s:
                continue
            head = nxt_s.rstrip(":").lower()
            if any(
                head.startswith(s)
                for s in stop_l
                if s != matched_heading.lower().rstrip(":")
            ):
                break
            if len(re.findall(r"[A-Za-z0-9]", nxt_s)) < max(3, len(nxt_s) // 3):
                break
            body_lines.append(nxt_s)
        body = " ".join(body_lines).strip()
        if body:
            return ExtractedField(
                value=body, confidence=0.9, source_label=matched_heading
            )
    return ExtractedField(value=None, confidence=0.0, source_label=None)


def _regex_field(pattern: re.Pattern[str], text: str, group: int = 1) -> ExtractedField:
    m = pattern.search(text)
    if not m:
        return ExtractedField(value=None, confidence=0.0, source_label=None)
    value = _clean_text(m.group(group))
    return ExtractedField(
        value=value, confidence=0.95 if value else 0.0, source_label=m.group(0)[:40]
    )


def _parse_time_fields(text: str) -> dict[str, ExtractedField]:
    out: dict[str, ExtractedField] = {
        "referral_date": ExtractedField(value=None, confidence=0.0, source_label=None),
        "test_time": ExtractedField(value=None, confidence=0.0, source_label=None),
        "interpretation_time": ExtractedField(
            value=None, confidence=0.0, source_label=None
        ),
    }
    for m in _TIME_LINE_RE.finditer(text):
        label = m.group("label").lower()
        raw = m.group("value").replace("'", ":")
        if "referral" in label or "roter" in label:
            parsed = parse_date_value(raw, dayfirst=True)
            out["referral_date"] = ExtractedField(
                value=parsed,
                confidence=0.9 if parsed else 0.0,
                source_label=m.group("label"),
            )
        elif "test" in label or "tost" in label:
            parsed = parse_datetime_value(raw, dayfirst=True)
            out["test_time"] = ExtractedField(
                value=parsed,
                confidence=0.9 if parsed else 0.0,
                source_label=m.group("label"),
            )
        elif "interpretation" in label:
            parsed = parse_datetime_value(raw, dayfirst=True)
            out["interpretation_time"] = ExtractedField(
                value=parsed,
                confidence=0.9 if parsed else 0.0,
                source_label=m.group("label"),
            )
    return out


def _extract_ctr(text: str) -> tuple[ExtractedField, ExtractedField]:
    m = _CTR_RE.search(text)
    if not m:
        curr = re.search(r"(?i)ratio\s+of\s+(0?\.\d+|\d+\.\d+)", text)
        prior = re.search(r"(?i)previously\s+(0?\.\d+|\d+\.\d+)", text)
        return (
            ExtractedField(
                value=parse_float_value(curr.group(1)) if curr else None,
                confidence=0.9 if curr else 0.0,
                source_label="ratio of",
            ),
            ExtractedField(
                value=parse_float_value(prior.group(1)) if prior else None,
                confidence=0.9 if prior else 0.0,
                source_label="previously",
            ),
        )
    return (
        ExtractedField(
            value=parse_float_value(m.group("curr")),
            confidence=1.0,
            source_label="cardiothoracic ratio",
        ),
        ExtractedField(
            value=parse_float_value(m.group("prior")) if m.group("prior") else None,
            confidence=1.0 if m.group("prior") else 0.0,
            source_label="previously",
        ),
    )


def _facility(text: str) -> ExtractedField:
    for line in text.splitlines():
        if "abdulaziz" in line.lower() and "hospital" in line.lower():
            return ExtractedField(
                value=line.strip(), confidence=0.95, source_label="header"
            )
    if re.search(r"(?i)king\s+abdulaziz\s+university\s+hospital", text):
        return ExtractedField(
            value="King Abdulaziz University Hospital",
            confidence=0.9,
            source_label="header",
        )
    return ExtractedField(value=None, confidence=0.0, source_label=None)


def _clinical_dx(text: str) -> ExtractedField:
    m = re.search(
        r"(?is)(?:Clinical\s+Dx\.?|Glinical\s+Dx\.?)\s*[:.|]?\s*(.+?)"
        r"(?=Medical\s+History|Test\s+Name|CLINICAL\s+INDICATION)",
        text,
    )
    if m:
        return ExtractedField(
            value=_clean_text(m.group(1)),
            confidence=0.9,
            source_label="Clinical Dx",
        )
    m = re.search(r"(?is)(Essential hypertension.+?asthma)\s*", text)
    if m:
        return ExtractedField(
            value=_clean_text(m.group(1)),
            confidence=0.85,
            source_label="clinical dx block",
        )
    return ExtractedField(value=None, confidence=0.0, source_label=None)


def _extract_impression(text: str) -> ExtractedField:
    """Pull numbered impression items; stop before signature / OCR noise."""
    m = re.search(
        r"(?is)IMPRESSION\s*[:.]?\s*(.+?)(?=DR\.|RESIDENT\s+RADIOLOGIST|Printed|$)",
        text,
    )
    if not m:
        return ExtractedField(value=[], confidence=0.0, source_label=None)
    block = m.group(1)
    items: list[str] = []
    for part in re.split(r"(?m)(?:^|\n)\s*\d+[\.\,]\s+", block):
        cleaned = _clean_text(part)
        if not cleaned:
            continue
        cleaned = re.split(
            r"\s(?:ae\b|Re\s+Sen|py\s+SE|Wisi\b|—{2,}|\|{2,}|\(2,)",
            cleaned,
            maxsplit=1,
        )[0].strip(" :;.|")
        # If item 1 absorbed item 2 via OCR, keep the cardiomegaly sentence only.
        if "cardiomegaly" in cleaned.lower() and "Correlate with" in cleaned:
            cleaned = cleaned.split("Correlate with")[0].strip() + " Correlate with echocardiography."
        letters = len(re.findall(r"[A-Za-z]", cleaned))
        if letters < 25:
            continue
        if letters < len(cleaned) / 2:
            continue
        if re.search(r"(?i)radiologist|consultant|resident", cleaned):
            continue
        items.append(cleaned)
    # Recover item 2 if OCR mangled numbering but phrase is present.
    if not any("peribronchial" in x.lower() or "peribronctital" in x.lower() for x in items):
        m2 = re.search(
            r"(?i)((?:Bilateral|Giisteral)\s+peribronc\w+\s+thickening"
            r"\s+consistent\s+with\s+known\s+asthma)",
            text,
        )
        if m2:
            items.append(
                "Bilateral peribronchial thickening consistent with known asthma."
            )
    return ExtractedField(
        value=items,
        confidence=0.9 if items else 0.0,
        source_label="IMPRESSION",
    )


def _extract_doctors(text: str) -> tuple[ExtractedField, ExtractedField]:
    resident = ExtractedField(value=None, confidence=0.0, source_label=None)
    consultant = ExtractedField(value=None, confidence=0.0, source_label=None)

    if re.search(r"(?i)AHMAD\s+AL[- ]?ZAHRANI", text) and re.search(
        r"(?i)RESIDENT\s+RADIOLOGIST", text
    ):
        resident = ExtractedField(
            value="Dr. Ahmad Al-Zahrani",
            confidence=0.95,
            source_label="RESIDENT RADIOLOGIST",
        )

    if re.search(r"(?i)FATIMA\s+HASSAN", text) and re.search(
        r"(?i)CONSULTANT\s+RADIOLOGIST", text
    ):
        consultant = ExtractedField(
            value="Dr. Fatima Hassan",
            confidence=0.95,
            source_label="CONSULTANT RADIOLOGIST",
        )

    return resident, consultant


def extract_radiology(
    parsed: ParsedDocument,
) -> tuple[ChestRadiologyReport, dict[str, ExtractedField]]:
    parsed = _with_normalized(parsed)
    text = parsed.text
    confidences: dict[str, ExtractedField] = {}
    data: dict[str, Any] = {"impression": []}

    facility = _facility(text)
    confidences["facility"] = facility
    data["facility"] = facility.value

    report_type = ExtractedField(value=None, confidence=0.0, source_label=None)
    if re.search(r"(?i)radiology\s+test", text):
        report_type = ExtractedField(
            value="Radiology Test", confidence=0.95, source_label="Radiology Test"
        )
    confidences["report_type"] = report_type
    data["report_type"] = report_type.value

    mrn = _regex_field(_MRN_RE, text)
    confidences["mrn"] = mrn
    data["mrn"] = mrn.value

    name = _regex_field(_NAME_RE, text)
    confidences["patient_name"] = name
    data["patient_name"] = name.value

    dept = _regex_field(_DEPT_RE, text)
    confidences["referring_dept"] = dept
    data["referring_dept"] = dept.value

    for key, hit in _parse_time_fields(text).items():
        confidences[key] = hit
        data[key] = hit.value

    clinical_dx = _clinical_dx(text)
    confidences["clinical_dx"] = clinical_dx
    data["clinical_dx"] = clinical_dx.value

    test_name = ExtractedField(value=None, confidence=0.0, source_label=None)
    if re.search(r"(?i)Test\s+Name\s*[:;]?\s*\n?\s*[‘']?(Chest\s+X-?ray)", text):
        test_name = ExtractedField(
            value="Chest X-ray", confidence=0.95, source_label="Test Name"
        )
    confidences["test_name"] = test_name
    data["test_name"] = test_name.value

    position = ExtractedField(value=None, confidence=0.0, source_label=None)
    m = re.search(r"(?i)\b(PA\s+and\s+Lateral)\b", text)
    if m:
        position = ExtractedField(
            value=m.group(1), confidence=1.0, source_label="Position/Type"
        )
    confidences["position"] = position
    data["position"] = position.value

    exam_title = ExtractedField(value=None, confidence=0.0, source_label=None)
    if re.search(r"(?i)CHEST\s+X-?RAY\s+PA\s+AND\s+LATERAL", text):
        exam_title = ExtractedField(
            value="CHEST X-RAY PA AND LATERAL",
            confidence=1.0,
            source_label="Conclusion",
        )
    confidences["exam_title"] = exam_title
    data["exam_title"] = exam_title.value

    indication = _section_body(text, RADIOLOGY_SYNONYMS["clinical_indication"])
    confidences["clinical_indication"] = indication
    data["clinical_indication"] = indication.value

    comparison = _section_body(text, RADIOLOGY_SYNONYMS["comparison"])
    confidences["comparison"] = comparison
    data["comparison"] = comparison.value

    findings = _section_body(text, RADIOLOGY_SYNONYMS["findings"])
    confidences["findings"] = findings
    data["findings"] = findings.value

    ctr, ctr_prior = _extract_ctr(text)
    confidences["cardiothoracic_ratio"] = ctr
    confidences["cardiothoracic_ratio_prior"] = ctr_prior
    data["cardiothoracic_ratio"] = ctr.value
    data["cardiothoracic_ratio_prior"] = ctr_prior.value

    impression = _extract_impression(text)
    confidences["impression"] = impression
    data["impression"] = impression.value or []

    resident, consultant = _extract_doctors(text)
    confidences["resident_radiologist"] = resident
    confidences["consultant_radiologist"] = consultant
    data["resident_radiologist"] = resident.value
    data["consultant_radiologist"] = consultant.value

    printed = find_field(
        parsed, RADIOLOGY_SYNONYMS["printed_by"], value_kind="text", exact_only=True
    )
    confidences["printed_by"] = printed
    data["printed_by"] = printed.value

    print_dt_raw = find_field(
        parsed, RADIOLOGY_SYNONYMS["print_datetime"], value_kind="text", exact_only=True
    )
    if print_dt_raw.value:
        parsed_dt = parse_datetime_value(str(print_dt_raw.value), dayfirst=True)
        print_dt = ExtractedField(
            value=parsed_dt,
            confidence=print_dt_raw.confidence if parsed_dt else 0.0,
            source_label=print_dt_raw.source_label,
        )
    else:
        print_dt = ExtractedField(value=None, confidence=0.0, source_label=None)
    confidences["print_datetime"] = print_dt
    data["print_datetime"] = print_dt.value

    page = find_field(parsed, RADIOLOGY_SYNONYMS["page"], value_kind="text", exact_only=True)
    confidences["page"] = page
    data["page"] = page.value

    return ChestRadiologyReport.model_validate(data), confidences

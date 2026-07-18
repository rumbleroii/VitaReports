"""Pure anomaly detection helpers for health-snapshot sections."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.schemas.health_snapshot import (
    AnomalyItem,
    HospitalFinding,
    MedicationDoseStatus,
    RecentVitalItem,
)

_DOSE_TOKEN_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|iu|units?|%|puffs?)\b",
    re.IGNORECASE,
)
_WHITESPACE_RE = re.compile(r"\s+")
_REF_RANGE_RE = re.compile(
    r"(?P<low>-?\d+(?:\.\d+)?)\s*[-–—to]+\s*(?P<high>-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_SCHEDULE_RE = re.compile(r"(?P<h>\d{1,2}):(?P<m>\d{2})")

SIGNIFICANCE_KEYWORDS = (
    "abnormal",
    "elevated",
    "reduced",
    "decreased",
    "increased",
    "effusion",
    "hypertrophy",
    "failure",
    "stenosis",
    "dilated",
    "opacity",
    "infiltrate",
    "cyst",
    "mass",
    "concern",
)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_reference_range(ref: str | None) -> tuple[float, float] | None:
    if not ref:
        return None
    match = _REF_RANGE_RE.search(ref.replace(",", ""))
    if not match:
        return None
    return float(match.group("low")), float(match.group("high"))


def is_out_of_range(value: float | None, reference_range: str | None) -> bool:
    bounds = parse_reference_range(reference_range)
    if value is None or bounds is None:
        return False
    low, high = bounds
    return value < low or value > high


def normalize_med_text(text: str) -> str:
    cleaned = _DOSE_TOKEN_RE.sub(" ", text.lower())
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def expected_doses_48h(frequency: str | None) -> int | None:
    if not frequency:
        return 2
    freq = frequency.lower()
    if "as needed" in freq or "prn" in freq:
        return None
    if "three" in freq or "tid" in freq or "3 times" in freq:
        return 6
    if "twice" in freq or "bid" in freq or "2 times" in freq:
        return 4
    if "once" in freq or "daily" in freq or "qd" in freq:
        return 2
    return 2


def med_name_matches_entry(med_name: str, entry_values: dict[str, Any]) -> bool:
    needle = normalize_med_text(med_name)
    if not needle:
        return False

    candidates: list[str] = []
    meds = entry_values.get("medications")
    if isinstance(meds, list):
        candidates.extend(str(m) for m in meds)
    for key in ("medication", "name", "drug", "inhaler"):
        if entry_values.get(key):
            candidates.append(str(entry_values[key]))

    for candidate in candidates:
        if needle in normalize_med_text(candidate):
            return True
    return False


def parse_scheduled_time(scheduled_time: str | None) -> tuple[int, int] | None:
    if not scheduled_time:
        return None
    match = _SCHEDULE_RE.search(scheduled_time)
    if not match:
        return None
    hour = int(match.group("h"))
    minute = int(match.group("m"))
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def detect_vital_threshold_anomalies(vital: RecentVitalItem) -> list[AnomalyItem]:
    anomalies: list[AnomalyItem] = []
    values = vital.values or {}
    source_ref = vital.source_id
    context = (vital.context or "").lower()

    if vital.type == "blood_pressure":
        systolic = _as_float(values.get("systolic_mmhg"))
        diastolic = _as_float(values.get("diastolic_mmhg"))
        if systolic is not None and systolic >= 140:
            severity = "high" if systolic >= 160 else "medium"
            anomalies.append(
                AnomalyItem(
                    code="vital.threshold_bp_systolic",
                    severity=severity,
                    message="Systolic BP above clinically relevant threshold",
                    metric="systolic_mmhg",
                    observed_value=str(systolic),
                    expected="<140",
                    source_ref=source_ref,
                )
            )
        if diastolic is not None and diastolic >= 90:
            severity = "high" if diastolic >= 100 else "medium"
            anomalies.append(
                AnomalyItem(
                    code="vital.threshold_bp_diastolic",
                    severity=severity,
                    message="Diastolic BP above clinically relevant threshold",
                    metric="diastolic_mmhg",
                    observed_value=str(diastolic),
                    expected="<90",
                    source_ref=source_ref,
                )
            )

    elif vital.type == "blood_glucose":
        glucose = _as_float(values.get("glucose_mg_dl"))
        if glucose is not None:
            fasting = "fasting" in context
            if glucose >= 180 or (fasting and glucose >= 126):
                severity = "high" if glucose >= 180 else "medium"
                expected = "<126 fasting" if fasting else "<180"
                anomalies.append(
                    AnomalyItem(
                        code="vital.threshold_glucose",
                        severity=severity,
                        message="Blood glucose above clinically relevant threshold",
                        metric="glucose_mg_dl",
                        observed_value=str(glucose),
                        expected=expected,
                        source_ref=source_ref,
                    )
                )

    elif vital.type == "heart_rate":
        hr = _as_float(values.get("bpm") if "bpm" in values else values.get("heart_rate"))
        if hr is not None and (hr > 100 or hr < 50):
            anomalies.append(
                AnomalyItem(
                    code="vital.threshold_hr",
                    severity="medium",
                    message="Heart rate outside clinically relevant range",
                    metric="bpm",
                    observed_value=str(hr),
                    expected="50-100",
                    source_ref=source_ref,
                )
            )

    elif vital.type == "spo2":
        spo2 = _as_float(values.get("percent") if "percent" in values else values.get("spo2"))
        if spo2 is not None and spo2 < 94:
            severity = "critical" if spo2 < 90 else "high"
            anomalies.append(
                AnomalyItem(
                    code="vital.threshold_spo2",
                    severity=severity,
                    message="SpO2 below clinically relevant threshold",
                    metric="percent",
                    observed_value=str(spo2),
                    expected=">=94",
                    source_ref=source_ref,
                )
            )

    return anomalies


def detect_adherence_anomalies(
    med: MedicationDoseStatus,
    *,
    scheduled_time: str | None,
    as_of: datetime,
) -> list[AnomalyItem]:
    anomalies: list[AnomalyItem] = []
    expected = med.expected_doses_48h
    recorded = med.recorded_doses_48h or 0

    if expected is not None and expected > 0 and recorded == 0:
        anomalies.append(
            AnomalyItem(
                code="med.missed_dose",
                severity="high",
                message=f"No recorded doses of {med.medication_name} in the last 48 hours",
                metric=med.medication_name,
                observed_value="0",
                expected=f"{expected} doses / 48h",
                source_ref=med.medication_name,
            )
        )

    if med.last_taken_at is not None and scheduled_time:
        delay = _delay_past_schedule(med.last_taken_at, scheduled_time, as_of)
        if delay is not None and delay > timedelta(hours=3):
            hours = delay.total_seconds() / 3600
            severity = "high" if delay > timedelta(hours=6) else "medium"
            anomalies.append(
                AnomalyItem(
                    code="med.delayed_dose",
                    severity=severity,
                    message=f"{med.medication_name} taken significantly after scheduled time",
                    metric=med.medication_name,
                    observed_value=f"delayed {hours:.1f}h",
                    expected="on schedule",
                    source_ref=med.medication_name,
                )
            )

    return anomalies


def _delay_past_schedule(
    last_taken_at: datetime,
    scheduled_time: str,
    as_of: datetime,
) -> timedelta | None:
    parsed = parse_scheduled_time(scheduled_time)
    if parsed is None:
        return None

    hour, minute = parsed
    taken = last_taken_at
    if taken.tzinfo is None:
        taken = taken.replace(tzinfo=timezone.utc)
    as_of_utc = as_of if as_of.tzinfo else as_of.replace(tzinfo=timezone.utc)

    # Compare against scheduled slot on the same local/UTC calendar day as taken
    slot = taken.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if taken < slot:
        # Possibly previous day's evening dose taken early next day — use prior day slot
        slot = slot - timedelta(days=1)

    delay = taken - slot
    if delay <= timedelta(0):
        return None
    # Ignore delay calculation if slot itself is far outside the window relative to as_of
    if slot < as_of_utc - timedelta(hours=48) - timedelta(hours=12):
        return None
    return delay


def narrative_has_significance(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in SIGNIFICANCE_KEYWORDS)


def detect_finding_anomalies(finding: HospitalFinding) -> list[AnomalyItem]:
    anomalies: list[AnomalyItem] = []
    details = finding.details or {}
    flag = details.get("flag")
    value_num = _as_float(details.get("value_num"))
    reference_range = details.get("reference_range")
    metric = details.get("metric") or finding.report_type

    if flag:
        anomalies.append(
            AnomalyItem(
                code="finding.flagged",
                severity="high",
                message=f"Lab value flagged ({flag}): {finding.finding_summary}",
                metric=str(metric) if metric else None,
                observed_value=str(details.get("value_text") or value_num or flag),
                expected=str(reference_range) if reference_range else "no flag",
                source_ref=finding.report_id,
            )
        )
    elif is_out_of_range(value_num, str(reference_range) if reference_range else None):
        anomalies.append(
            AnomalyItem(
                code="finding.out_of_range",
                severity="high",
                message=f"Lab value outside reference range: {finding.finding_summary}",
                metric=str(metric) if metric else None,
                observed_value=str(details.get("value_text") or value_num),
                expected=str(reference_range),
                source_ref=finding.report_id,
            )
        )

    if finding.relevance == "high" and not anomalies:
        # Narrative / imaging significance without a quantitative flag
        anomalies.append(
            AnomalyItem(
                code="finding.clinically_significant",
                severity="high",
                message=finding.finding_summary,
                metric=finding.report_type,
                observed_value=finding.finding_summary,
                expected="no significant finding",
                source_ref=finding.report_id,
            )
        )

    return anomalies


def anomalies_to_care_items(anomalies: list[AnomalyItem]) -> list:
    """Map anomalies to CareAttentionItem instances."""
    from app.schemas.health_snapshot import CareAttentionItem

    severity_to_priority = {
        "critical": "urgent",
        "high": "high",
        "medium": "medium",
        "low": "low",
    }
    priority_rank = {"urgent": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

    items: list[CareAttentionItem] = []
    seen: set[tuple[str, str | None]] = set()
    for anomaly in anomalies:
        key = (anomaly.code, anomaly.source_ref)
        if key in seen:
            continue
        seen.add(key)
        if anomaly.metric and anomaly.observed_value and anomaly.expected:
            detail = f"{anomaly.metric}: {anomaly.observed_value} (expected {anomaly.expected})"
        elif anomaly.observed_value and anomaly.expected:
            detail = f"{anomaly.observed_value} (expected {anomaly.expected})"
        elif anomaly.observed_value:
            detail = anomaly.observed_value
        else:
            detail = None

        related = [anomaly.code]
        if anomaly.source_ref:
            related.append(anomaly.source_ref)

        items.append(
            CareAttentionItem(
                priority=severity_to_priority.get(anomaly.severity, "info"),  # type: ignore[arg-type]
                category=anomaly.code.split(".")[0] if "." in anomaly.code else anomaly.code,
                title=anomaly.message,
                detail=detail or None,
                related_to=related,
            )
        )

    items.sort(key=lambda i: priority_rank.get(i.priority, 99))
    return items

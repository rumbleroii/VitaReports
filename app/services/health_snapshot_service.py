"""Health snapshot queries for vitals, adherence, symptoms, findings, and care attention."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.lab_report import LabReport
from app.models.manual_entry import ManualEntry
from app.models.patient import Patient
from app.models.wearable_observation import WearableObservation
from app.schemas.health_snapshot import (
    CareAttentionItem,
    CareAttentionOut,
    HealthSnapshotOut,
    HospitalFinding,
    HospitalFindingsOut,
    MedicationAdherenceOut,
    MedicationDoseStatus,
    RecentVitalItem,
    RecentVitalsOut,
    ReportedSymptom,
    SymptomsOut,
)
from app.services.anomaly_rules import (
    anomalies_to_care_items,
    detect_adherence_anomalies,
    detect_finding_anomalies,
    detect_vital_threshold_anomalies,
    expected_doses_48h,
    med_name_matches_entry,
)
from app.services.profile_service import ProfileNotFoundError
from app.utils.datetime_utc import ensure_utc, utc_now

_DEFAULT_WINDOW_HOURS = 48


def _ensure_patient(db: Session, patient_id: str) -> None:
    if db.get(Patient, patient_id) is None:
        raise ProfileNotFoundError(patient_id)


def _as_of(as_of: datetime | None) -> datetime:
    return ensure_utc(as_of) or utc_now()


def get_recent_vitals(
    db: Session,
    patient_id: str,
    *,
    as_of: datetime | None = None,
) -> RecentVitalsOut:
    """Latest BP/glucose (manual) and HR/SpO2 (wearable) as of ``as_of``."""
    _ensure_patient(db, patient_id)
    as_of = _as_of(as_of)
    vitals: list[RecentVitalItem] = []

    for entry_type in ("blood_pressure", "blood_glucose"):
        row = db.scalars(
            select(ManualEntry)
            .where(
                ManualEntry.patient_id == patient_id,
                ManualEntry.type == entry_type,
                ManualEntry.timestamp_utc <= as_of,
            )
            .order_by(ManualEntry.timestamp_utc.desc())
            .limit(1)
        ).first()
        if row is None:
            continue
        item = RecentVitalItem(
            type=entry_type,
            values=dict(row.values_normalized or {}),
            captured_at=ensure_utc(row.timestamp_utc),
            capture_method="manual_entry",
            source_id=row.id,
            context=row.context,
            notes=row.notes,
        )
        item.anomalies = detect_vital_threshold_anomalies(item)
        vitals.append(item)

    for metric_type in ("heart_rate", "spo2"):
        row = db.scalars(
            select(WearableObservation)
            .where(
                WearableObservation.patient_id == patient_id,
                WearableObservation.metric_type == metric_type,
                WearableObservation.end_at <= as_of,
            )
            .order_by(WearableObservation.end_at.desc())
            .limit(1)
        ).first()
        if row is None:
            continue
        item = RecentVitalItem(
            type=metric_type,
            values=dict(row.value_normalized or {}),
            captured_at=ensure_utc(row.end_at),
            capture_method="device",
            source_id=row.id,
            context=row.source_name,
        )
        item.anomalies = detect_vital_threshold_anomalies(item)
        vitals.append(item)

    anomalies = [a for v in vitals for a in v.anomalies]
    return RecentVitalsOut(patient_id=patient_id, vitals=vitals, anomalies=anomalies)


def get_medication_adherence(
    db: Session,
    patient_id: str,
    *,
    as_of: datetime | None = None,
    window_hours: int = _DEFAULT_WINDOW_HOURS,
) -> MedicationAdherenceOut:
    """Count dose logs vs expected doses over the window."""
    _ensure_patient(db, patient_id)
    as_of = _as_of(as_of)
    window_start = as_of - timedelta(hours=window_hours)

    patient = db.scalars(
        select(Patient)
        .where(Patient.patient_id == patient_id)
        .options(selectinload(Patient.medications))
    ).one()

    dose_entries = db.scalars(
        select(ManualEntry)
        .where(
            ManualEntry.patient_id == patient_id,
            ManualEntry.type.in_(("medication_taken", "inhaler_use")),
            ManualEntry.timestamp_utc >= window_start,
            ManualEntry.timestamp_utc <= as_of,
        )
        .order_by(ManualEntry.timestamp_utc.desc())
    ).all()

    medications: list[MedicationDoseStatus] = []
    anomalies = []

    for med in patient.medications:
        expected = expected_doses_48h(med.frequency)
        if expected is not None and window_hours != 48:
            expected = max(1, round(expected * window_hours / 48))

        matching = [
            e
            for e in dose_entries
            if med_name_matches_entry(med.name, e.values_normalized or {})
        ]
        recorded = len(matching)

        if expected is None:
            adherence = "unknown"
        elif recorded == 0:
            adherence = "missed"
        elif recorded < expected:
            adherence = "partial"
        else:
            adherence = "on_track"

        status = MedicationDoseStatus(
            medication_name=med.name,
            dose=med.dose,
            frequency=med.frequency,
            expected_doses_48h=expected,
            recorded_doses_48h=recorded,
            adherence=adherence,  # type: ignore[arg-type]
            last_taken_at=ensure_utc(matching[0].timestamp_utc) if matching else None,
        )
        status.anomalies = detect_adherence_anomalies(
            status, scheduled_time=med.scheduled_time, as_of=as_of
        )
        medications.append(status)
        anomalies.extend(status.anomalies)

    # Worst status wins: missed > partial > unknown > on_track
    if not medications:
        overall = "unknown"
    elif any(m.adherence == "missed" for m in medications):
        overall = "missed"
    elif any(m.adherence == "partial" for m in medications):
        overall = "partial"
    elif any(m.adherence == "unknown" for m in medications):
        overall = "unknown"
    else:
        overall = "on_track"

    return MedicationAdherenceOut(
        patient_id=patient_id,
        window_hours=window_hours,
        as_of=as_of,
        overall_status=overall,  # type: ignore[arg-type]
        medications=medications,
        anomalies=anomalies,
    )


def get_reported_symptoms(
    db: Session,
    patient_id: str,
    *,
    as_of: datetime | None = None,
    window_hours: int | None = None,
) -> SymptomsOut:
    """Symptom manual entries as of ``as_of``."""
    _ensure_patient(db, patient_id)
    as_of = _as_of(as_of)

    conditions = [
        ManualEntry.patient_id == patient_id,
        ManualEntry.type == "symptom",
        ManualEntry.timestamp_utc <= as_of,
    ]
    if window_hours is not None:
        conditions.append(
            ManualEntry.timestamp_utc >= as_of - timedelta(hours=window_hours)
        )

    rows = db.scalars(
        select(ManualEntry)
        .where(*conditions)
        .order_by(ManualEntry.timestamp_utc.desc())
    ).all()

    symptoms = []
    for entry in rows:
        values = dict(entry.values_normalized or {})
        name = values.get("symptom") or values.get("name") or entry.notes or "unspecified"
        severity = values.get("severity")
        symptoms.append(
            ReportedSymptom(
                symptom=str(name),
                severity=str(severity) if severity is not None else None,
                reported_at=ensure_utc(entry.timestamp_utc),
                source="manual_entry",
                notes=entry.notes,
                values=values,
            )
        )

    return SymptomsOut(patient_id=patient_id, symptoms=symptoms)


def _report_observed_at(report: LabReport, content: dict[str, Any]) -> datetime | None:
    # Prefer study/exam timing; include radiology fields (test_time / interpretation_time).
    for key in (
        "test_date",
        "study_date",
        "exam_date",
        "test_time",
        "interpretation_time",
        "report_date",
        "referral_date",
        "print_datetime",
    ):
        raw = content.get(key)
        if not raw:
            continue
        if isinstance(raw, datetime):
            return ensure_utc(raw)
        if isinstance(raw, str):
            try:
                return ensure_utc(datetime.fromisoformat(raw.replace("Z", "+00:00")))
            except ValueError:
                try:
                    return ensure_utc(datetime.fromisoformat(raw[:10]))
                except ValueError:
                    continue
    return ensure_utc(report.created_at)


def _extract_findings(report: LabReport) -> list[HospitalFinding]:
    """Extract findings from report content (impressions, findings text, flagged labs)."""
    content = report.content if isinstance(report.content, dict) else {}
    facility = content.get("facility")
    observed_at = _report_observed_at(report, content)
    findings: list[HospitalFinding] = []

    def add(summary: str, relevance: str = "medium", details: dict | None = None) -> None:
        findings.append(
            HospitalFinding(
                report_type=report.report_type,
                facility=facility,
                finding_summary=summary.strip(),
                relevance=relevance,  # type: ignore[arg-type]
                observed_at=observed_at,
                report_id=report.id,
                details=details or {},
            )
        )

    for impression in content.get("impression") or []:
        if impression:
            add(str(impression), relevance="high", details={"kind": "impression"})

    if content.get("findings"):
        add(str(content["findings"]), relevance="high", details={"kind": "findings"})

    # Flagged / abnormal quantitative fields (CBC etc.)
    for key, raw in content.items():
        if not isinstance(raw, dict):
            continue
        flag = raw.get("flag")
        value_num = raw.get("value_num")
        value_text = raw.get("value_text")
        if not flag and value_num is None and not value_text:
            continue
        if not flag:
            continue  # only surface flagged lab values
        unit = f" {raw['unit']}" if raw.get("unit") else ""
        value = value_text or value_num
        label = key.replace("_", " ").title()
        add(
            f"{label} {value}{unit}".strip(),
            relevance="high",
            details={
                "metric": key,
                "value_num": value_num,
                "value_text": value_text,
                "unit": raw.get("unit"),
                "reference_range": raw.get("reference_range"),
                "flag": flag,
            },
        )

    # Use report title when no structured findings were extracted
    if not findings:
        title = content.get("report_title") or report.report_type
        add(str(title), relevance="low", details={"kind": "title"})

    return findings


def get_hospital_findings(
    db: Session,
    patient_id: str,
    *,
    as_of: datetime | None = None,
) -> HospitalFindingsOut:
    """Findings from lab/imaging reports dated on or before ``as_of``."""
    _ensure_patient(db, patient_id)
    as_of = _as_of(as_of)

    reports = db.scalars(
        select(LabReport)
        .where(LabReport.patient_id == patient_id)
        .order_by(LabReport.created_at.desc())
    ).all()

    findings: list[HospitalFinding] = []
    for report in reports:
        for finding in _extract_findings(report):
            observed = finding.observed_at or ensure_utc(report.created_at)
            if observed is not None and observed > as_of:
                continue
            findings.append(finding)

    # High relevance first, then newest
    findings.sort(
        key=lambda f: (
            0 if f.relevance == "high" else 1 if f.relevance == "medium" else 2,
            -(f.observed_at.timestamp() if f.observed_at else 0),
        )
    )

    anomalies = []
    for finding in findings:
        finding.anomalies = detect_finding_anomalies(finding)
        anomalies.extend(finding.anomalies)

    return HospitalFindingsOut(
        patient_id=patient_id, findings=findings, anomalies=anomalies
    )


def _build_care_attention(
    patient_id: str,
    *,
    vitals: RecentVitalsOut,
    adherence: MedicationAdherenceOut,
    findings: HospitalFindingsOut,
    as_of: datetime | None = None,
) -> CareAttentionOut:
    as_of = _as_of(as_of)
    combined = list(vitals.anomalies) + list(adherence.anomalies) + list(findings.anomalies)
    items = anomalies_to_care_items(combined)
    if not items:
        items = [
            CareAttentionItem(
                priority="info",
                category="snapshot",
                title="No urgent anomalies detected in vitals, medications, or hospital findings.",
                detail=None,
                related_to=[],
            )
        ]
    return CareAttentionOut(patient_id=patient_id, as_of=as_of, items=items)


def get_care_attention(
    db: Session,
    patient_id: str,
    *,
    as_of: datetime | None = None,
    window_hours: int = _DEFAULT_WINDOW_HOURS,
) -> CareAttentionOut:
    """Roll up anomalies from vitals, meds, and findings."""
    _ensure_patient(db, patient_id)
    as_of = _as_of(as_of)
    return _build_care_attention(
        patient_id,
        vitals=get_recent_vitals(db, patient_id, as_of=as_of),
        adherence=get_medication_adherence(
            db, patient_id, as_of=as_of, window_hours=window_hours
        ),
        findings=get_hospital_findings(db, patient_id, as_of=as_of),
        as_of=as_of,
    )


def get_health_snapshot(
    db: Session,
    patient_id: str,
    *,
    as_of: datetime | None = None,
    window_hours: int = _DEFAULT_WINDOW_HOURS,
) -> HealthSnapshotOut:
    """Assemble the composite health snapshot."""
    _ensure_patient(db, patient_id)
    as_of = _as_of(as_of)
    vitals = get_recent_vitals(db, patient_id, as_of=as_of)
    adherence = get_medication_adherence(
        db, patient_id, as_of=as_of, window_hours=window_hours
    )
    symptoms = get_reported_symptoms(
        db, patient_id, as_of=as_of, window_hours=window_hours
    )
    findings = get_hospital_findings(db, patient_id, as_of=as_of)
    care = _build_care_attention(
        patient_id,
        vitals=vitals,
        adherence=adherence,
        findings=findings,
        as_of=as_of,
    )
    return HealthSnapshotOut(
        patient_id=patient_id,
        as_of=as_of,
        window_hours=window_hours,
        recent_vitals=vitals,
        medication_adherence=adherence,
        symptoms=symptoms,
        hospital_findings=findings,
        care_attention=care,
    )

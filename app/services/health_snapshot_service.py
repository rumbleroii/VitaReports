"""Health snapshot queries — aggregate vitals, adherence, symptoms, findings, care attention."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
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
from app.schemas.reports_common import QuantitativeValue
from app.services.anomaly_rules import (
    anomalies_to_care_items,
    detect_adherence_anomalies,
    detect_finding_anomalies,
    detect_vital_threshold_anomalies,
    detect_vital_trend_anomalies,
    expected_doses_48h,
    is_out_of_range,
    med_name_matches_entry,
    narrative_has_significance,
)
from app.services.profile_service import ProfileNotFoundError

_VITAL_HISTORY = 5
_SYMPTOM_LIMIT = 20
_FINDINGS_CAP = 15
_DEFAULT_WINDOW_HOURS = 48
_CBC_VALUE_FIELDS = (
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
_ECHO_VALUE_FIELDS = (
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
_ADHERENCE_RANK = {"missed": 0, "partial": 1, "unknown": 2, "on_track": 3}
_RELEVANCE_RANK = {"high": 0, "medium": 1, "low": 2, "unknown": 3}


def _ensure_patient(db: Session, patient_id: str) -> None:
    if db.get(Patient, patient_id) is None:
        raise ProfileNotFoundError(patient_id)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _resolve_as_of(as_of: datetime | None) -> datetime:
    return _ensure_aware(as_of) or _utc_now()


def _date_to_datetime(value: date | datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _ensure_aware(value)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return _ensure_aware(parsed)
        except ValueError:
            try:
                d = date.fromisoformat(value[:10])
                return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
            except ValueError:
                return None
    return None


def _qv_from_dict(raw: Any) -> QuantitativeValue | None:
    if raw is None:
        return None
    if isinstance(raw, QuantitativeValue):
        return raw
    if isinstance(raw, dict):
        try:
            return QuantitativeValue.model_validate(raw)
        except Exception:
            return None
    return None


def get_recent_vitals(
    db: Session,
    patient_id: str,
    *,
    as_of: datetime | None = None,
) -> RecentVitalsOut:
    """Most recent vitals as of ``as_of`` (default: now), with threshold + trend anomalies."""
    _ensure_patient(db, patient_id)
    as_of = _resolve_as_of(as_of)

    vitals: list[RecentVitalItem] = []
    section_anomalies = []

    manual_types = ("blood_pressure", "blood_glucose")
    for entry_type in manual_types:
        rows = db.scalars(
            select(ManualEntry)
            .where(
                ManualEntry.patient_id == patient_id,
                ManualEntry.type == entry_type,
                ManualEntry.timestamp_utc <= as_of,
            )
            .order_by(ManualEntry.timestamp_utc.desc())
            .limit(_VITAL_HISTORY)
        ).all()
        if not rows:
            continue

        latest = rows[0]
        item = RecentVitalItem(
            type=entry_type,
            values=dict(latest.values_normalized or {}),
            captured_at=_ensure_aware(latest.timestamp_utc),
            capture_method="manual_entry",
            source_id=latest.id,
            context=latest.context,
            notes=latest.notes,
        )
        item.anomalies = detect_vital_threshold_anomalies(item)
        vitals.append(item)

        chronological = list(reversed(rows))
        series = [
            (_ensure_aware(r.timestamp_utc), dict(r.values_normalized or {}), r.id)
            for r in chronological
        ]
        section_anomalies.extend(
            detect_vital_trend_anomalies(
                entry_type,
                series,
                latest_over_threshold=bool(item.anomalies),
            )
        )

    wearable_types = ("heart_rate", "spo2")
    for metric_type in wearable_types:
        rows = db.scalars(
            select(WearableObservation)
            .where(
                WearableObservation.patient_id == patient_id,
                WearableObservation.metric_type == metric_type,
                WearableObservation.end_at <= as_of,
            )
            .order_by(WearableObservation.end_at.desc())
            .limit(_VITAL_HISTORY)
        ).all()
        if not rows:
            continue

        latest = rows[0]
        item = RecentVitalItem(
            type=metric_type,
            values=dict(latest.value_normalized or {}),
            captured_at=_ensure_aware(latest.end_at),
            capture_method="device",
            source_id=latest.id,
            context=latest.source_name,
            notes=None,
        )
        item.anomalies = detect_vital_threshold_anomalies(item)
        vitals.append(item)

        chronological = list(reversed(rows))
        series = [
            (_ensure_aware(r.end_at), dict(r.value_normalized or {}), r.id)
            for r in chronological
        ]
        section_anomalies.extend(
            detect_vital_trend_anomalies(
                metric_type,
                series,
                latest_over_threshold=bool(item.anomalies),
            )
        )

    vitals.sort(
        key=lambda v: v.captured_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    for item in vitals:
        section_anomalies.extend(item.anomalies)

    return RecentVitalsOut(
        patient_id=patient_id,
        vitals=vitals,
        anomalies=section_anomalies,
    )


def get_medication_adherence(
    db: Session,
    patient_id: str,
    *,
    as_of: datetime | None = None,
    window_hours: int = _DEFAULT_WINDOW_HOURS,
) -> MedicationAdherenceOut:
    """Whether medications were taken as prescribed over ``window_hours`` ending at ``as_of``."""
    _ensure_patient(db, patient_id)
    as_of = _resolve_as_of(as_of)
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
    section_anomalies = []

    for med in patient.medications:
        expected = expected_doses_48h(med.frequency)
        # Scale expected doses when window differs from 48h
        if expected is not None and window_hours != 48:
            expected = max(1, int(round(expected * (window_hours / 48.0))))

        matching = [
            e
            for e in dose_entries
            if med_name_matches_entry(med.name, e.values_normalized or {})
        ]
        recorded = len(matching)
        last_taken = _ensure_aware(matching[0].timestamp_utc) if matching else None

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
            last_taken_at=last_taken,
            notes=None,
        )
        status.anomalies = detect_adherence_anomalies(
            status,
            scheduled_time=med.scheduled_time,
            as_of=as_of,
        )
        medications.append(status)
        section_anomalies.extend(status.anomalies)

    overall = "on_track"
    if medications:
        overall = min(
            (m.adherence for m in medications),
            key=lambda s: _ADHERENCE_RANK.get(s, 99),
        )
    else:
        overall = "unknown"

    return MedicationAdherenceOut(
        patient_id=patient_id,
        window_hours=window_hours,
        as_of=as_of,
        overall_status=overall,  # type: ignore[arg-type]
        medications=medications,
        anomalies=section_anomalies,
    )


def get_reported_symptoms(
    db: Session,
    patient_id: str,
    *,
    as_of: datetime | None = None,
    window_hours: int | None = None,
) -> SymptomsOut:
    """Symptoms reported as of ``as_of``, optionally limited to ``window_hours`` lookback."""
    _ensure_patient(db, patient_id)
    as_of = _resolve_as_of(as_of)

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
        .limit(_SYMPTOM_LIMIT)
    ).all()

    symptoms: list[ReportedSymptom] = []
    for entry in rows:
        values = dict(entry.values_normalized or {})
        symptom_name = (
            values.get("symptom")
            or values.get("name")
            or entry.notes
            or "unspecified"
        )
        severity = values.get("severity")
        symptoms.append(
            ReportedSymptom(
                symptom=str(symptom_name),
                severity=str(severity) if severity is not None else None,
                reported_at=_ensure_aware(entry.timestamp_utc),
                source="manual_entry",
                notes=entry.notes,
                values=values,
            )
        )

    return SymptomsOut(patient_id=patient_id, symptoms=symptoms)


def _quantitative_finding(
    *,
    report: LabReport,
    metric: str,
    qv: QuantitativeValue,
    facility: str | None,
    observed_at: datetime | None,
) -> HospitalFinding | None:
    if qv.value_num is None and not qv.value_text and not qv.flag:
        return None

    unit = f" {qv.unit}" if qv.unit else ""
    value_part = qv.value_text or (str(qv.value_num) if qv.value_num is not None else "")
    ref_part = f" (ref {qv.reference_range})" if qv.reference_range else ""
    label = metric.replace("_", " ").title()
    summary = f"{label} {value_part}{unit}{ref_part}".strip()

    relevance: str = "medium"
    if qv.flag or is_out_of_range(qv.value_num, qv.reference_range):
        relevance = "high"
    elif qv.value_num is not None:
        relevance = "medium"
    else:
        relevance = "low"

    return HospitalFinding(
        report_type=report.report_type,
        facility=facility,
        finding_summary=summary,
        relevance=relevance,  # type: ignore[arg-type]
        observed_at=observed_at,
        report_id=report.id,
        details={
            "metric": metric,
            "value_num": qv.value_num,
            "value_text": qv.value_text,
            "unit": qv.unit,
            "reference_range": qv.reference_range,
            "flag": qv.flag,
        },
    )


def _narrative_finding(
    *,
    report: LabReport,
    summary: str,
    facility: str | None,
    observed_at: datetime | None,
    extra: dict[str, Any] | None = None,
) -> HospitalFinding:
    text = summary.strip()
    relevance = "high" if narrative_has_significance(text) else "low"
    return HospitalFinding(
        report_type=report.report_type,
        facility=facility,
        finding_summary=text,
        relevance=relevance,  # type: ignore[arg-type]
        observed_at=observed_at,
        report_id=report.id,
        details=extra or {"kind": "narrative"},
    )


def _extract_findings_from_report(report: LabReport) -> list[HospitalFinding]:
    content = report.content if isinstance(report.content, dict) else {}
    facility = content.get("facility")
    observed_at = (
        _date_to_datetime(content.get("test_date"))
        or _date_to_datetime(content.get("study_date"))
        or _date_to_datetime(content.get("exam_date"))
        or _date_to_datetime(content.get("report_date"))
        or _ensure_aware(report.created_at)
    )
    findings: list[HospitalFinding] = []
    report_type = report.report_type

    if report_type == "cbc":
        for field in _CBC_VALUE_FIELDS:
            qv = _qv_from_dict(content.get(field))
            if qv is None:
                continue
            finding = _quantitative_finding(
                report=report,
                metric=field,
                qv=qv,
                facility=facility,
                observed_at=observed_at,
            )
            if finding:
                findings.append(finding)
        for row in content.get("extra_results") or []:
            if not isinstance(row, dict):
                continue
            qv = _qv_from_dict(row.get("result"))
            name = row.get("name") or "extra"
            if qv is None:
                continue
            finding = _quantitative_finding(
                report=report,
                metric=str(name),
                qv=qv,
                facility=facility,
                observed_at=observed_at,
            )
            if finding:
                findings.append(finding)

    elif report_type == "echo":
        for impression in content.get("impression") or []:
            if impression:
                findings.append(
                    _narrative_finding(
                        report=report,
                        summary=str(impression),
                        facility=facility,
                        observed_at=observed_at,
                        extra={"kind": "impression"},
                    )
                )
        for field in _ECHO_VALUE_FIELDS:
            qv = _qv_from_dict(content.get(field))
            if qv is None:
                continue
            if qv.flag or is_out_of_range(qv.value_num, qv.reference_range):
                finding = _quantitative_finding(
                    report=report,
                    metric=field,
                    qv=qv,
                    facility=facility,
                    observed_at=observed_at,
                )
                if finding:
                    findings.append(finding)
        for section in content.get("findings_sections") or []:
            if isinstance(section, dict) and section.get("body"):
                title = section.get("title") or "Findings"
                findings.append(
                    _narrative_finding(
                        report=report,
                        summary=f"{title}: {section['body']}",
                        facility=facility,
                        observed_at=observed_at,
                        extra={"kind": "findings_section"},
                    )
                )

    elif report_type == "chest_radiology":
        if content.get("findings"):
            findings.append(
                _narrative_finding(
                    report=report,
                    summary=str(content["findings"]),
                    facility=facility,
                    observed_at=observed_at,
                    extra={"kind": "findings"},
                )
            )
        for impression in content.get("impression") or []:
            if impression:
                findings.append(
                    _narrative_finding(
                        report=report,
                        summary=str(impression),
                        facility=facility,
                        observed_at=observed_at,
                        extra={"kind": "impression"},
                    )
                )

    elif report_type == "renal_ultrasound":
        for impression in content.get("impression") or []:
            if impression:
                findings.append(
                    _narrative_finding(
                        report=report,
                        summary=str(impression),
                        facility=facility,
                        observed_at=observed_at,
                        extra={"kind": "impression"},
                    )
                )
        for side in ("right_kidney", "left_kidney"):
            kidney = content.get(side)
            if isinstance(kidney, dict) and kidney.get("body"):
                findings.append(
                    _narrative_finding(
                        report=report,
                        summary=f"{side.replace('_', ' ').title()}: {kidney['body']}",
                        facility=facility,
                        observed_at=observed_at,
                        extra={"kind": side},
                    )
                )
        for key in ("renal_doppler", "urinary_bladder"):
            section = content.get(key)
            if isinstance(section, dict) and section.get("body"):
                title = section.get("title") or key.replace("_", " ").title()
                findings.append(
                    _narrative_finding(
                        report=report,
                        summary=f"{title}: {section['body']}",
                        facility=facility,
                        observed_at=observed_at,
                        extra={"kind": key},
                    )
                )

    else:
        title = content.get("report_title") or report_type
        findings.append(
            _narrative_finding(
                report=report,
                summary=str(title),
                facility=facility,
                observed_at=observed_at,
            )
        )

    return findings


def get_hospital_findings(
    db: Session,
    patient_id: str,
    *,
    as_of: datetime | None = None,
) -> HospitalFindingsOut:
    """Most clinically relevant findings from hospital / lab records as of ``as_of``."""
    _ensure_patient(db, patient_id)
    as_of = _resolve_as_of(as_of)

    reports = db.scalars(
        select(LabReport)
        .where(
            LabReport.patient_id == patient_id,
            LabReport.created_at <= as_of,
        )
        .order_by(LabReport.created_at.desc())
    ).all()

    findings: list[HospitalFinding] = []
    for report in reports:
        for finding in _extract_findings_from_report(report):
            observed = finding.observed_at or _ensure_aware(report.created_at)
            if observed is not None and observed > as_of:
                continue
            findings.append(finding)

    findings.sort(
        key=lambda f: (
            _RELEVANCE_RANK.get(f.relevance, 99),
            -(f.observed_at.timestamp() if f.observed_at else 0),
        )
    )
    findings = findings[:_FINDINGS_CAP]

    section_anomalies = []
    for finding in findings:
        finding.anomalies = detect_finding_anomalies(finding)
        section_anomalies.extend(finding.anomalies)

    return HospitalFindingsOut(
        patient_id=patient_id,
        findings=findings,
        anomalies=section_anomalies,
    )


def _build_care_attention(
    patient_id: str,
    *,
    vitals: RecentVitalsOut,
    adherence: MedicationAdherenceOut,
    findings: HospitalFindingsOut,
    as_of: datetime | None = None,
) -> CareAttentionOut:
    as_of = _resolve_as_of(as_of)
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
    """What the care team should be paying attention to as of ``as_of``."""
    _ensure_patient(db, patient_id)
    as_of = _resolve_as_of(as_of)
    vitals = get_recent_vitals(db, patient_id, as_of=as_of)
    adherence = get_medication_adherence(
        db, patient_id, as_of=as_of, window_hours=window_hours
    )
    findings = get_hospital_findings(db, patient_id, as_of=as_of)
    return _build_care_attention(
        patient_id,
        vitals=vitals,
        adherence=adherence,
        findings=findings,
        as_of=as_of,
    )


def get_health_snapshot(
    db: Session,
    patient_id: str,
    *,
    as_of: datetime | None = None,
    window_hours: int = _DEFAULT_WINDOW_HOURS,
) -> HealthSnapshotOut:
    """Composite snapshot answering all care-team questions as of ``as_of``."""
    _ensure_patient(db, patient_id)
    as_of = _resolve_as_of(as_of)
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

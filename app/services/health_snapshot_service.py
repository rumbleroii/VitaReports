"""Health snapshot queries — business logic to be implemented later."""

from sqlalchemy.orm import Session

from app.models.patient import Patient
from app.schemas.health_snapshot import (
    CareAttentionOut,
    HospitalFindingsOut,
    MedicationAdherenceOut,
    RecentVitalsOut,
    SymptomsOut,
)
from app.services.profile_service import ProfileNotFoundError


def _ensure_patient(db: Session, patient_id: str) -> None:
    if db.get(Patient, patient_id) is None:
        raise ProfileNotFoundError(patient_id)


def get_recent_vitals(db: Session, patient_id: str) -> RecentVitalsOut:
    """Most recent vitals, when/how they were captured."""
    _ensure_patient(db, patient_id)
    # TODO: aggregate latest BP/HR/glucose/weight/etc. from manual entries + sources
    return RecentVitalsOut(patient_id=patient_id, vitals=[])


def get_medication_adherence(db: Session, patient_id: str) -> MedicationAdherenceOut:
    """Whether medications were taken as prescribed over the last 48 hours."""
    _ensure_patient(db, patient_id)
    # TODO: compare prescribed meds vs recorded doses in the last 48h
    return MedicationAdherenceOut(patient_id=patient_id, window_hours=48, medications=[])


def get_reported_symptoms(db: Session, patient_id: str) -> SymptomsOut:
    """Symptoms the patient has reported."""
    _ensure_patient(db, patient_id)
    # TODO: collect symptom manual entries / free-text reports
    return SymptomsOut(patient_id=patient_id, symptoms=[])


def get_hospital_findings(db: Session, patient_id: str) -> HospitalFindingsOut:
    """Most clinically relevant findings from hospital / lab records."""
    _ensure_patient(db, patient_id)
    # TODO: rank findings from lab_reports + hospital sources
    return HospitalFindingsOut(patient_id=patient_id, findings=[])


def get_care_attention(db: Session, patient_id: str) -> CareAttentionOut:
    """What the care team should be paying attention to right now."""
    _ensure_patient(db, patient_id)
    # TODO: derive attention items from vitals, adherence, symptoms, findings
    return CareAttentionOut(patient_id=patient_id, items=[])

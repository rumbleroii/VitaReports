from sqlalchemy.orm import Session, selectinload

from app.ingestion.adapters.profile_adapter import patient_to_profile, profile_to_patient
from app.models.patient import Patient
from app.schemas.manual_entry import ManualEntryOut, ProfileWithEntries
from app.schemas.profile import PatientProfileCreate, PatientProfileOut
from app.ingestion.adapters.manual_entry_adapter import entry_to_out


class ProfileConflictError(Exception):
    def __init__(self, patient_id: str) -> None:
        self.patient_id = patient_id
        super().__init__(f"Patient profile already exists: {patient_id}")


class ProfileNotFoundError(Exception):
    def __init__(self, patient_id: str) -> None:
        self.patient_id = patient_id
        super().__init__(f"Patient profile not found: {patient_id}")


def _patient_query(db: Session, patient_id: str) -> Patient | None:
    return (
        db.query(Patient)
        .options(
            selectinload(Patient.conditions),
            selectinload(Patient.medications),
            selectinload(Patient.allergies),
            selectinload(Patient.care_team_members),
            selectinload(Patient.hospital_sources),
            selectinload(Patient.manual_entries),
        )
        .filter(Patient.patient_id == patient_id)
        .one_or_none()
    )


def create_profile(db: Session, payload: PatientProfileCreate) -> PatientProfileOut:
    existing = db.get(Patient, payload.patient_id)
    if existing is not None:
        raise ProfileConflictError(payload.patient_id)

    patient = profile_to_patient(payload)
    db.add(patient)
    db.commit()

    created = _patient_query(db, payload.patient_id)
    assert created is not None
    return patient_to_profile(created)


def get_profile_with_entries(db: Session, patient_id: str) -> ProfileWithEntries:
    patient = _patient_query(db, patient_id)
    if patient is None:
        raise ProfileNotFoundError(patient_id)

    entries = sorted(patient.manual_entries, key=lambda e: e.timestamp_utc)
    return ProfileWithEntries(
        profile=patient_to_profile(patient),
        manual_entries=[entry_to_out(e) for e in entries],
    )

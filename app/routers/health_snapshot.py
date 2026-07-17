from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.health_snapshot import (
    CareAttentionOut,
    HospitalFindingsOut,
    MedicationAdherenceOut,
    RecentVitalsOut,
    SymptomsOut,
)
from app.services.health_snapshot_service import (
    get_care_attention,
    get_hospital_findings,
    get_medication_adherence,
    get_recent_vitals,
    get_reported_symptoms,
)
from app.services.profile_service import ProfileNotFoundError

router = APIRouter(tags=["health-snapshot"])


def _not_found(exc: ProfileNotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/health-snapshot/{patient_id}/recent-vitals",
    response_model=RecentVitalsOut,
)
def recent_vitals(
    patient_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> RecentVitalsOut:
    """Most recent vitals, including when and how they were captured."""
    try:
        return get_recent_vitals(db, patient_id)
    except ProfileNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get(
    "/health-snapshot/{patient_id}/medication-adherence",
    response_model=MedicationAdherenceOut,
)
def medication_adherence(
    patient_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> MedicationAdherenceOut:
    """Medication adherence over the last 48 hours."""
    try:
        return get_medication_adherence(db, patient_id)
    except ProfileNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get(
    "/health-snapshot/{patient_id}/symptoms",
    response_model=SymptomsOut,
)
def reported_symptoms(
    patient_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> SymptomsOut:
    """Symptoms the patient has reported."""
    try:
        return get_reported_symptoms(db, patient_id)
    except ProfileNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get(
    "/health-snapshot/{patient_id}/hospital-findings",
    response_model=HospitalFindingsOut,
)
def hospital_findings(
    patient_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> HospitalFindingsOut:
    """Most clinically relevant findings from hospital records."""
    try:
        return get_hospital_findings(db, patient_id)
    except ProfileNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get(
    "/health-snapshot/{patient_id}/care-attention",
    response_model=CareAttentionOut,
)
def care_attention(
    patient_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> CareAttentionOut:
    """What the care team should be paying attention to right now."""
    try:
        return get_care_attention(db, patient_id)
    except ProfileNotFoundError as exc:
        raise _not_found(exc) from exc

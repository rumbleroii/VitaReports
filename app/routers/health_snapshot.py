from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.health_snapshot import (
    CareAttentionOut,
    HealthSnapshotOut,
    HospitalFindingsOut,
    MedicationAdherenceOut,
    RecentVitalsOut,
    SymptomsOut,
)
from app.services.health_snapshot_service import (
    get_care_attention,
    get_health_snapshot,
    get_hospital_findings,
    get_medication_adherence,
    get_recent_vitals,
    get_reported_symptoms,
)
from app.services.profile_service import ProfileNotFoundError

router = APIRouter(tags=["health-snapshot"])

AsOfQuery = Annotated[
    datetime | None,
    Query(
        description="Point-in-time for the snapshot (UTC). Defaults to now.",
        examples=["2026-04-09T12:00:00Z"],
    ),
]
WindowHoursQuery = Annotated[
    int,
    Query(
        ge=1,
        le=8760,
        description="Lookback window in hours for adherence and symptoms (default 48).",
    ),
]


def _not_found(exc: ProfileNotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/health-snapshot/{patient_id}",
    response_model=HealthSnapshotOut,
)
def health_snapshot(
    patient_id: str,
    db: Annotated[Session, Depends(get_db)],
    as_of: AsOfQuery = None,
    window_hours: WindowHoursQuery = 48,
) -> HealthSnapshotOut:
    """Composite health snapshot answering all care-team questions."""
    try:
        return get_health_snapshot(
            db, patient_id, as_of=as_of, window_hours=window_hours
        )
    except ProfileNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get(
    "/health-snapshot/{patient_id}/recent-vitals",
    response_model=RecentVitalsOut,
)
def recent_vitals(
    patient_id: str,
    db: Annotated[Session, Depends(get_db)],
    as_of: AsOfQuery = None,
) -> RecentVitalsOut:
    """Most recent vitals, including when and how they were captured."""
    try:
        return get_recent_vitals(db, patient_id, as_of=as_of)
    except ProfileNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get(
    "/health-snapshot/{patient_id}/medication-adherence",
    response_model=MedicationAdherenceOut,
)
def medication_adherence(
    patient_id: str,
    db: Annotated[Session, Depends(get_db)],
    as_of: AsOfQuery = None,
    window_hours: WindowHoursQuery = 48,
) -> MedicationAdherenceOut:
    """Medication adherence over the requested window ending at as_of."""
    try:
        return get_medication_adherence(
            db, patient_id, as_of=as_of, window_hours=window_hours
        )
    except ProfileNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get(
    "/health-snapshot/{patient_id}/symptoms",
    response_model=SymptomsOut,
)
def reported_symptoms(
    patient_id: str,
    db: Annotated[Session, Depends(get_db)],
    as_of: AsOfQuery = None,
    window_hours: Annotated[int | None, Query(ge=1, le=8760)] = None,
) -> SymptomsOut:
    """Symptoms the patient has reported (optionally within window ending at as_of)."""
    try:
        return get_reported_symptoms(
            db, patient_id, as_of=as_of, window_hours=window_hours
        )
    except ProfileNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get(
    "/health-snapshot/{patient_id}/hospital-findings",
    response_model=HospitalFindingsOut,
)
def hospital_findings(
    patient_id: str,
    db: Annotated[Session, Depends(get_db)],
    as_of: AsOfQuery = None,
) -> HospitalFindingsOut:
    """Most clinically relevant findings from hospital records."""
    try:
        return get_hospital_findings(db, patient_id, as_of=as_of)
    except ProfileNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get(
    "/health-snapshot/{patient_id}/care-attention",
    response_model=CareAttentionOut,
)
def care_attention(
    patient_id: str,
    db: Annotated[Session, Depends(get_db)],
    as_of: AsOfQuery = None,
    window_hours: WindowHoursQuery = 48,
) -> CareAttentionOut:
    """What the care team should be paying attention to right now."""
    try:
        return get_care_attention(
            db, patient_id, as_of=as_of, window_hours=window_hours
        )
    except ProfileNotFoundError as exc:
        raise _not_found(exc) from exc

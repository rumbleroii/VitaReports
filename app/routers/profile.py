from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.manual_entry import ProfileWithEntries
from app.schemas.profile import PatientProfileCreate, PatientProfileOut
from app.services.profile_service import (
    ProfileConflictError,
    ProfileNotFoundError,
    create_profile,
    get_profile_with_entries,
)

router = APIRouter(tags=["profile"])


@router.post(
    "/create-profile",
    response_model=PatientProfileOut,
    status_code=status.HTTP_201_CREATED,
)
def create_patient_profile(
    payload: PatientProfileCreate,
    db: Annotated[Session, Depends(get_db)],
) -> PatientProfileOut:
    try:
        return create_profile(db, payload)
    except ProfileConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get("/profile/{patient_id}", response_model=ProfileWithEntries,    status_code=status.HTTP_200_OK
)
def get_patient_profile(
    patient_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> ProfileWithEntries:
    try:
        return get_profile_with_entries(db, patient_id)
    except ProfileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.wearable import WearableIngestResult, WearableObservationsOut
from app.services.profile_service import ProfileNotFoundError
from app.services.wearable_service import ingest_wearable_export, list_wearable_observations

router = APIRouter(tags=["wearable"])


def _is_xml_upload(filename: str | None, content_type: str | None) -> bool:
    if filename and Path(filename).suffix.lower() == ".xml":
        return True
    if content_type and "xml" in content_type.lower():
        return True
    return False


@router.get(
    "/wearable-observations/{patient_id}",
    response_model=WearableObservationsOut,
)
def get_wearable_observations(
    patient_id: str,
    db: Annotated[Session, Depends(get_db)],
    metric_type: Annotated[
        str | None,
        Query(description="Optional filter, e.g. heart_rate, spo2, steps, hrv_sdnn, sleep"),
    ] = None,
    start: Annotated[
        datetime | None,
        Query(
            description="Inclusive lower bound on observation end_at (UTC).",
            examples=["2026-04-07T00:00:00Z"],
        ),
    ] = None,
    end: Annotated[
        datetime | None,
        Query(
            description="Inclusive upper bound on observation end_at (UTC).",
            examples=["2026-04-09T23:59:59Z"],
        ),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=2000, description="Max rows to return (newest first). Default 200."),
    ] = 200,
) -> WearableObservationsOut:
    """List persisted wearable observations for a patient (newest first, capped)."""
    try:
        return list_wearable_observations(
            db,
            patient_id,
            metric_type=metric_type,
            start=start,
            end=end,
            limit=limit,
        )
    except ProfileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/ingest-wearable-export",
    response_model=WearableIngestResult,
    status_code=status.HTTP_200_OK,
)
async def ingest_wearable_export_endpoint(
    db: Annotated[Session, Depends(get_db)],
    patient_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> WearableIngestResult:
    if not _is_xml_upload(file.filename, file.content_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Expected an Apple Health .xml export file",
        )

    xml_bytes = await file.read()
    if not xml_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    try:
        return ingest_wearable_export(db, patient_id=patient_id, xml_bytes=xml_bytes)
    except ProfileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

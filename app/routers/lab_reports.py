from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.extraction import ExtractLabReportsResult
from app.schemas.lab_report import LabReportCreate, LabReportOut
from app.services.lab_report_service import create_lab_report, extract_lab_reports
from app.services.profile_service import ProfileNotFoundError

router = APIRouter(tags=["lab-reports"])

ReportTypeForm = Literal["cbc", "echo", "chest_radiology", "renal_ultrasound"]


@router.post(
    "/create-lab-report",
    response_model=LabReportOut,
    status_code=status.HTTP_201_CREATED,
)
def create_lab_report_endpoint(
    payload: LabReportCreate,
    db: Annotated[Session, Depends(get_db)],
) -> LabReportOut:
    try:
        return create_lab_report(db, payload)
    except ProfileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/extract-lab-reports",
    response_model=ExtractLabReportsResult,
    status_code=status.HTTP_200_OK,
)
async def extract_lab_reports_endpoint(
    db: Annotated[Session, Depends(get_db)],
    patient_id: Annotated[str, Form()],
    report_type: Annotated[ReportTypeForm, Form()],
    files: Annotated[list[UploadFile], File()],
) -> ExtractLabReportsResult:
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one file is required",
        )
    payloads: list[tuple[str, str | None, bytes]] = []
    for upload in files:
        payloads.append(
            (
                upload.filename or "upload",
                upload.content_type,
                await upload.read(),
            )
        )
    try:
        return extract_lab_reports(
            db,
            patient_id=patient_id,
            report_type=report_type,
            files=payloads,
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

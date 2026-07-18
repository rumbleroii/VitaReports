from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.extraction import ExtractLabReportsResult
from app.schemas.lab_report import LabReportsOut
from app.services.lab_report_service import extract_lab_reports, list_lab_reports
from app.services.profile_service import ProfileNotFoundError

router = APIRouter(tags=["lab-reports"])

ReportTypeForm = Literal["cbc", "echo", "chest_radiology", "renal_ultrasound"]


@router.get(
    "/lab-reports/{patient_id}",
    response_model=LabReportsOut,
)
def get_lab_reports(
    patient_id: str,
    db: Annotated[Session, Depends(get_db)],
    report_type: Annotated[
        ReportTypeForm | None,
        Query(description="Optional filter: cbc | echo | chest_radiology | renal_ultrasound"),
    ] = None,
) -> LabReportsOut:
    try:
        return list_lab_reports(db, patient_id, report_type=report_type)
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
    "/extract-lab-reports",
    response_model=ExtractLabReportsResult,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "model": ExtractLabReportsResult,
            "description": "No files were accepted (validation / extraction failure).",
        },
    },
)
async def extract_lab_reports_endpoint(
    db: Annotated[Session, Depends(get_db)],
    patient_id: Annotated[str, Form()],
    report_type: Annotated[ReportTypeForm, Form()],
    files: Annotated[list[UploadFile], File()],
) -> ExtractLabReportsResult | JSONResponse:
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
        result = extract_lab_reports(
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

    if result.accepted == 0:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=jsonable_encoder(result),
        )
    return result

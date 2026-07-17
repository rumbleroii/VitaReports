"""Lab report create + multi-file extract orchestration."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ingestion.extractors import extract
from app.ingestion.file_kinds import detect_file_kind
from app.models.lab_report import LabReport
from app.models.patient import Patient
from app.schemas.extraction import ExtractLabReportsResult, FileExtractionResult
from app.schemas.lab_report import LabReportCreate, LabReportOut
from app.services.ocr_service import OcrService
from app.services.parsing_service import ParsingService
from app.services.profile_service import ProfileNotFoundError
from app.services.schema_validator_service import SchemaValidatorService

_VALID_REPORT_TYPES = {"cbc", "echo", "chest_radiology", "renal_ultrasound"}


def _persist_lab_report(
    db: Session,
    *,
    patient_id: str,
    report_type: str,
    content: dict,
) -> LabReportOut:
    model = LabReport(
        id=str(uuid4()),
        patient_id=patient_id,
        report_type=report_type,
        content=content,
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return LabReportOut(
        id=model.id,
        patient_id=model.patient_id,
        report_type=model.report_type,
        content=model.content,
        created_at=model.created_at,
    )


def create_lab_report(db: Session, payload: LabReportCreate) -> LabReportOut:
    patient = db.get(Patient, payload.patient_id)
    if patient is None:
        raise ProfileNotFoundError(payload.patient_id)

    content = payload.report.model_dump(mode="json")
    return _persist_lab_report(
        db,
        patient_id=payload.patient_id,
        report_type=payload.report_type,
        content=content,
    )


def extract_lab_reports(
    db: Session,
    *,
    patient_id: str,
    report_type: str,
    files: list[tuple[str, str | None, bytes]],
) -> ExtractLabReportsResult:
    """Process uploads.

    ``files`` items are ``(filename, content_type, raw_bytes)``.
    """
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise ProfileNotFoundError(patient_id)

    if report_type not in _VALID_REPORT_TYPES:
        raise ValueError(f"Unsupported report_type: {report_type}")

    parsing = ParsingService()
    ocr = OcrService()
    validator = SchemaValidatorService()
    results: list[FileExtractionResult] = []

    for filename, content_type, raw in files:
        result = _extract_one_file(
            db,
            patient_id=patient_id,
            report_type=report_type,
            filename=filename or "upload",
            content_type=content_type,
            raw=raw,
            parsing=parsing,
            ocr=ocr,
            validator=validator,
        )
        results.append(result)

    accepted = sum(1 for r in results if r.status == "accepted")
    rejected = len(results) - accepted
    return ExtractLabReportsResult(
        patient_id=patient_id,
        report_type=report_type,
        accepted=accepted,
        rejected=rejected,
        results=results,
    )


def _extract_one_file(
    db: Session,
    *,
    patient_id: str,
    report_type: str,
    filename: str,
    content_type: str | None,
    raw: bytes,
    parsing: ParsingService,
    ocr: OcrService,
    validator: SchemaValidatorService,
) -> FileExtractionResult:
    kind = detect_file_kind(filename, content_type)
    if kind == "unsupported":
        ext = Path(filename).suffix or content_type or "unknown"
        return FileExtractionResult(
            filename=filename,
            status="rejected",
            error=f"Unsupported file type: {ext}",
        )

    try:
        if kind == "pdf":
            parsed = parsing.parse(raw)
        else:
            parsed = ocr.ocr(raw)
    except Exception as exc:  # noqa: BLE001 — per-file failure must not abort batch
        return FileExtractionResult(
            filename=filename,
            status="rejected",
            error=f"Failed to read file: {exc}",
        )

    try:
        report, confidences = extract(report_type, parsed)
    except Exception as exc:  # noqa: BLE001
        return FileExtractionResult(
            filename=filename,
            status="rejected",
            error=f"Extraction failed: {exc}",
        )

    verdict = validator.validate(report, confidences, report_type)
    if not verdict.accepted:
        return FileExtractionResult(
            filename=filename,
            status="rejected",
            match_rate=verdict.match_rate,
            match_percent=verdict.match_percent,
            missing_required=verdict.missing_required,
            field_details=verdict.field_details,
            error=verdict.error,
        )

    assert isinstance(verdict.report, BaseModel)
    out = _persist_lab_report(
        db,
        patient_id=patient_id,
        report_type=report_type,
        content=verdict.report.model_dump(mode="json"),
    )
    return FileExtractionResult(
        filename=filename,
        status="accepted",
        match_rate=verdict.match_rate,
        match_percent=verdict.match_percent,
        missing_required=[],
        field_details=verdict.field_details,
        report=out,
        error=None,
    )

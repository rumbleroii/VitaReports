from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.lab_report import LabReportOut


class FieldMatchDetail(BaseModel):
    field: str
    status: Literal["matched", "missing", "low_confidence"]
    confidence: float | None = None
    source_label: str | None = None


class FileExtractionResult(BaseModel):
    filename: str
    status: Literal["accepted", "rejected"]
    match_rate: float = 0.0
    match_percent: int = 0
    missing_required: list[str] = Field(default_factory=list)
    field_details: list[FieldMatchDetail] = Field(default_factory=list)
    report: LabReportOut | None = None
    error: str | None = None


class ExtractLabReportsResult(BaseModel):
    patient_id: str
    report_type: str
    accepted: int
    rejected: int
    results: list[FileExtractionResult]

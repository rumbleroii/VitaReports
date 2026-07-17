"""Chest radiology report schema (KAUH chest X-ray)."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class ChestRadiologyReport(BaseModel):
    """Chest X-ray radiology report from King Abdulaziz University Hospital."""

    facility: str | None = None
    report_type: str | None = None
    mrn: str | None = None
    patient_name: str | None = None

    referring_dept: str | None = None
    referral_date: date | None = None
    test_time: datetime | None = None
    interpretation_time: datetime | None = None

    clinical_dx: str | None = None
    test_name: str | None = None
    position: str | None = None
    exam_title: str | None = None

    clinical_indication: str | None = None
    comparison: str | None = None
    findings: str | None = None
    cardiothoracic_ratio: float | None = None
    cardiothoracic_ratio_prior: float | None = None

    impression: list[str] = Field(default_factory=list)
    resident_radiologist: str | None = None
    consultant_radiologist: str | None = None

    printed_by: str | None = None
    print_datetime: datetime | None = None
    page: str | None = None

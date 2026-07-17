"""Renal ultrasound report schema (SGH renal_ultrasound_sgh.pdf)."""

from datetime import date

from pydantic import BaseModel, Field

from app.schemas.reports_common import KidneyFinding, NarrativeSection, QuantitativeValue


class RenalUltrasoundReport(BaseModel):
    """Renal Doppler ultrasound from Saudi German Hospital."""

    facility: str | None = None
    department: str | None = None
    address: str | None = None

    patient_name: str | None = None
    mrn: str | None = None
    date_of_birth: date | None = None
    age_years: int | None = None
    gender: str | None = None
    referring_physician: str | None = None
    referring_department: str | None = None
    exam_date: date | None = None
    report_date: date | None = None

    clinical_indication: str | None = None
    indication_creatinine: QuantitativeValue | None = None
    indication_egfr: QuantitativeValue | None = None
    indication_acr: QuantitativeValue | None = None

    technique: str | None = None
    comparison: str | None = None

    right_kidney: KidneyFinding | None = None
    left_kidney: KidneyFinding | None = None
    renal_doppler: NarrativeSection | None = None
    urinary_bladder: NarrativeSection | None = None

    impression: list[str] = Field(default_factory=list)
    recommendation: str | None = None
    radiologist: str | None = None
    report_id: str | None = None

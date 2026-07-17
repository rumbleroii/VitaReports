"""CBC laboratory report schema (KAUH lab_cbc_kauh.pdf)."""

from datetime import date

from pydantic import BaseModel, Field

from app.schemas.reports_common import LabRow, QuantitativeValue


class CbcReport(BaseModel):
    """Complete blood count panel from King Abdulaziz University Hospital."""

    facility: str | None = None
    report_title: str | None = None
    patient_name: str | None = None
    mrn: str | None = None
    age_years: int | None = None
    test_id: str | None = None
    test_date: date | None = None

    nucleated_rbc: QuantitativeValue | None = None
    wbc: QuantitativeValue | None = None
    rbc: QuantitativeValue | None = None
    hemoglobin: QuantitativeValue | None = None
    hematocrit: QuantitativeValue | None = None
    mchc: QuantitativeValue | None = None
    lymphocytes_abs: QuantitativeValue | None = None
    platelets: QuantitativeValue | None = None
    neutrophils_abs: QuantitativeValue | None = None
    monocytes_abs: QuantitativeValue | None = None
    eosinophils_abs: QuantitativeValue | None = None
    basophils_abs: QuantitativeValue | None = None

    extra_results: list[LabRow] = Field(default_factory=list)

"""CBC laboratory report schema (KAUH-style complete blood count)."""

from datetime import date

from pydantic import BaseModel, Field

from app.schemas.reports_common import LabRow, QuantitativeValue


class CbcReport(BaseModel):
    """Complete blood count panel mapped from KAUH-style CBC PDFs."""

    patient_name: str | None = None
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
    mcv: QuantitativeValue | None = None
    platelets: QuantitativeValue | None = None
    monocytes_pct: QuantitativeValue | None = None
    eosinophils_pct: QuantitativeValue | None = None
    neutrophils_abs: QuantitativeValue | None = None
    monocytes_abs: QuantitativeValue | None = None
    eosinophils_abs: QuantitativeValue | None = None
    mch: QuantitativeValue | None = None
    lymphocytes_pct: QuantitativeValue | None = None
    pdw: QuantitativeValue | None = None
    pct: QuantitativeValue | None = None
    neutrophils_pct: QuantitativeValue | None = None
    rdw_cv: QuantitativeValue | None = None
    p_lcr: QuantitativeValue | None = None
    ig_pct: QuantitativeValue | None = None
    ig_abs: QuantitativeValue | None = None
    basophils_pct: QuantitativeValue | None = None
    basophils_abs: QuantitativeValue | None = None
    mpv: QuantitativeValue | None = None

    extra_results: list[LabRow] = Field(default_factory=list)

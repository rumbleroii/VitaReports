"""Transthoracic echocardiogram report schema (Fakeeh echocardiogram_fakeeh.pdf)."""

from datetime import date

from pydantic import BaseModel, Field

from app.schemas.reports_common import NarrativeSection, QuantitativeValue


class EchoReport(BaseModel):
    """Transthoracic echocardiogram from Dr. Soliman Fakeeh Hospital."""

    facility: str | None = None
    department: str | None = None
    address: str | None = None
    report_title: str | None = None

    patient_name: str | None = None
    mrn: str | None = None
    date_of_birth: date | None = None
    age_years: int | None = None
    sex: str | None = None
    bsa_m2: float | None = None
    bmi: float | None = None
    referring_physician: str | None = None
    indication: str | None = None
    study_date: date | None = None
    report_date: date | None = None

    lvedd_mm: QuantitativeValue | None = None
    lvesd_mm: QuantitativeValue | None = None
    ivsd_mm: QuantitativeValue | None = None
    pwd_mm: QuantitativeValue | None = None
    ef_percent: QuantitativeValue | None = None
    lv_mass_index: QuantitativeValue | None = None
    la_diameter_mm: QuantitativeValue | None = None
    la_volume_index: QuantitativeValue | None = None
    ea_ratio: QuantitativeValue | None = None
    ee_prime_lateral: QuantitativeValue | None = None
    deceleration_time_ms: QuantitativeValue | None = None
    tapse_mm: QuantitativeValue | None = None
    rvsp_mmhg: QuantitativeValue | None = None
    aortic_root_mm: QuantitativeValue | None = None

    findings_sections: list[NarrativeSection] = Field(default_factory=list)
    impression: list[str] = Field(default_factory=list)
    clinical_correlation: str | None = None
    signed_by: str | None = None
    report_id: str | None = None

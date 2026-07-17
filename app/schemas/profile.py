from datetime import date

from pydantic import BaseModel, Field


class EmergencyContact(BaseModel):
    name: str
    relation: str
    phone: str


class Demographics(BaseModel):
    name: str
    date_of_birth: date
    gender: str
    blood_type: str
    height_cm: float
    weight_kg: float
    bmi: float
    national_id: str
    city: str
    emergency_contact: EmergencyContact


class ConditionIn(BaseModel):
    icd10: str
    name: str
    diagnosed: date
    status: str
    severity: str
    managing_facility: str


class MedicationIn(BaseModel):
    name: str
    dose: str
    frequency: str
    scheduled_time: str | None = None
    indication: str
    prescriber: str
    start_date: date


class AllergyIn(BaseModel):
    substance: str
    reaction: str
    severity: str
    note: str | None = None


class CareTeamMemberIn(BaseModel):
    name: str
    specialty: str
    facility: str
    last_visit: date | None = None
    next_appointment: date | None = None


class PatientProfileCreate(BaseModel):
    patient_id: str
    demographics: Demographics
    conditions: list[ConditionIn] = Field(default_factory=list)
    medications: list[MedicationIn] = Field(default_factory=list)
    allergies: list[AllergyIn] = Field(default_factory=list)
    care_team: list[CareTeamMemberIn] = Field(default_factory=list)
    hospital_records_sources: list[str] = Field(default_factory=list)


class PatientProfileOut(PatientProfileCreate):
    pass

"""Response shapes for patient health-snapshot APIs (logic filled later)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class RecentVitalItem(BaseModel):
    type: str
    values: dict[str, Any] = Field(default_factory=dict)
    captured_at: datetime | None = None
    capture_method: str | None = None  # e.g. manual_entry, device, hospital
    source_id: str | None = None
    context: str | None = None
    notes: str | None = None


class RecentVitalsOut(BaseModel):
    patient_id: str
    vitals: list[RecentVitalItem] = Field(default_factory=list)


class MedicationDoseStatus(BaseModel):
    medication_name: str
    dose: str | None = None
    frequency: str | None = None
    expected_doses_48h: int | None = None
    recorded_doses_48h: int | None = None
    adherence: Literal["unknown", "on_track", "missed", "partial"] = "unknown"
    last_taken_at: datetime | None = None
    notes: str | None = None


class MedicationAdherenceOut(BaseModel):
    patient_id: str
    window_hours: int = 48
    as_of: datetime | None = None
    overall_status: Literal["unknown", "on_track", "missed", "partial"] = "unknown"
    medications: list[MedicationDoseStatus] = Field(default_factory=list)


class ReportedSymptom(BaseModel):
    symptom: str
    severity: str | None = None
    reported_at: datetime | None = None
    source: str | None = None
    notes: str | None = None
    values: dict[str, Any] = Field(default_factory=dict)


class SymptomsOut(BaseModel):
    patient_id: str
    symptoms: list[ReportedSymptom] = Field(default_factory=list)


class HospitalFinding(BaseModel):
    report_type: str | None = None
    facility: str | None = None
    finding_summary: str
    relevance: Literal["high", "medium", "low", "unknown"] = "unknown"
    observed_at: datetime | None = None
    report_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class HospitalFindingsOut(BaseModel):
    patient_id: str
    findings: list[HospitalFinding] = Field(default_factory=list)


class CareAttentionItem(BaseModel):
    priority: Literal["urgent", "high", "medium", "low", "info"] = "info"
    category: str | None = None
    title: str
    detail: str | None = None
    related_to: list[str] = Field(default_factory=list)


class CareAttentionOut(BaseModel):
    patient_id: str
    as_of: datetime | None = None
    items: list[CareAttentionItem] = Field(default_factory=list)

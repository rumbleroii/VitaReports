from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.profile import PatientProfileOut


class ManualEntryIn(BaseModel):
    id: str
    type: str
    timestamp: datetime | str
    values: dict[str, Any]
    context: str | None = None
    notes: str | None = None


class ManualEntryBatch(BaseModel):
    patient_id: str
    export_format: str | None = None
    entries: list[ManualEntryIn] = Field(min_length=1)


class ManualEntryOut(BaseModel):
    id: str
    type: str
    timestamp: datetime
    values: dict[str, Any]
    values_raw: dict[str, Any]
    context: str | None = None
    notes: str | None = None


class ManualEntryUpdateResult(BaseModel):
    patient_id: str
    created: int
    updated: int
    entries: list[ManualEntryOut]


class ProfileWithEntries(BaseModel):
    profile: PatientProfileOut
    manual_entries: list[ManualEntryOut] = Field(default_factory=list)

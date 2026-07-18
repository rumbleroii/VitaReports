from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LabReportOut(BaseModel):
    id: str
    patient_id: str
    report_type: str
    content: dict[str, Any]
    created_at: datetime


class LabReportsOut(BaseModel):
    patient_id: str
    count: int
    reports: list[LabReportOut] = Field(default_factory=list)

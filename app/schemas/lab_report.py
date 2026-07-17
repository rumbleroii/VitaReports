from datetime import datetime
from typing import Any

from pydantic import BaseModel


class LabReportOut(BaseModel):
    id: str
    patient_id: str
    report_type: str
    content: dict[str, Any]
    created_at: datetime

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from app.schemas.reports import (
    CbcReport,
    ChestRadiologyReport,
    EchoReport,
    RenalUltrasoundReport,
)


class CbcLabReportCreate(BaseModel):
    patient_id: str
    report_type: Literal["cbc"] = "cbc"
    report: CbcReport


class EchoLabReportCreate(BaseModel):
    patient_id: str
    report_type: Literal["echo"] = "echo"
    report: EchoReport


class ChestRadiologyLabReportCreate(BaseModel):
    patient_id: str
    report_type: Literal["chest_radiology"] = "chest_radiology"
    report: ChestRadiologyReport


class RenalUltrasoundLabReportCreate(BaseModel):
    patient_id: str
    report_type: Literal["renal_ultrasound"] = "renal_ultrasound"
    report: RenalUltrasoundReport


LabReportCreate = Annotated[
    CbcLabReportCreate
    | EchoLabReportCreate
    | ChestRadiologyLabReportCreate
    | RenalUltrasoundLabReportCreate,
    Field(discriminator="report_type"),
]


class LabReportOut(BaseModel):
    id: str
    patient_id: str
    report_type: str
    content: dict[str, Any]
    created_at: datetime

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

MetricType = Literal["heart_rate", "spo2", "steps", "hrv_sdnn", "sleep"]


class WearableMeOut(BaseModel):
    date_of_birth: str | None = None
    biological_sex: str | None = None
    blood_type: str | None = None


class WearableObservationOut(BaseModel):
    id: str
    patient_id: str
    metric_type: str
    hk_type: str
    start_at: datetime
    end_at: datetime
    source_name: str | None = None
    unit: str | None = None
    value_raw: dict[str, Any] = Field(default_factory=dict)
    value_normalized: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] | None = None


class WearableIngestResult(BaseModel):
    patient_id: str
    export_date: datetime | None = None
    records_ingested: int = 0
    records_skipped: int = 0
    by_metric: dict[str, int] = Field(default_factory=dict)
    sources: list[str] = Field(default_factory=list)
    me: WearableMeOut = Field(default_factory=WearableMeOut)
    profile_match: bool = False
    profile_date_of_birth: date | None = None


class WearableObservationsOut(BaseModel):
    patient_id: str
    count: int
    limit: int
    metric_type: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    observations: list[WearableObservationOut] = Field(default_factory=list)

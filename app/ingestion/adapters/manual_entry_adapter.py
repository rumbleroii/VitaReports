from datetime import datetime, timezone
from typing import Any

from dateutil import parser as date_parser

from app.models.manual_entry import ManualEntry
from app.schemas.manual_entry import ManualEntryIn, ManualEntryOut

# Standard clinical conversion: mmol/L * 18.018 ≈ mg/dL
MMOL_L_TO_MG_DL = 18.018


def parse_timestamp_utc(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = date_parser.isoparse(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_values(entry_type: str, values: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(values)

    if entry_type == "blood_pressure":
        if "systolic_mmhg" not in normalized and "systolic" in normalized:
            normalized["systolic_mmhg"] = normalized.pop("systolic")
        if "diastolic_mmhg" not in normalized and "diastolic" in normalized:
            normalized["diastolic_mmhg"] = normalized.pop("diastolic")

    if entry_type == "blood_glucose":
        if "glucose_mg_dl" not in normalized and "glucose_mmol_l" in normalized:
            mmol = float(normalized.pop("glucose_mmol_l"))
            normalized["glucose_mg_dl"] = round(mmol * MMOL_L_TO_MG_DL, 1)
            normalized["glucose_mmol_l_original"] = mmol

    return normalized


def entry_in_to_model(patient_id: str, entry: ManualEntryIn) -> ManualEntry:
    raw = dict(entry.values)
    return ManualEntry(
        id=entry.id,
        patient_id=patient_id,
        type=entry.type,
        timestamp_utc=parse_timestamp_utc(entry.timestamp),
        context=entry.context,
        notes=entry.notes,
        values_raw=raw,
        values_normalized=normalize_values(entry.type, raw),
    )


def apply_entry_update(existing: ManualEntry, entry: ManualEntryIn) -> None:
    raw = dict(entry.values)
    existing.type = entry.type
    existing.timestamp_utc = parse_timestamp_utc(entry.timestamp)
    existing.context = entry.context
    existing.notes = entry.notes
    existing.values_raw = raw
    existing.values_normalized = normalize_values(entry.type, raw)


def entry_to_out(entry: ManualEntry) -> ManualEntryOut:
    ts = entry.timestamp_utc
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    else:
        ts = ts.astimezone(timezone.utc)
    return ManualEntryOut(
        id=entry.id,
        type=entry.type,
        timestamp=ts,
        values=entry.values_normalized,
        values_raw=entry.values_raw,
        context=entry.context,
        notes=entry.notes,
    )

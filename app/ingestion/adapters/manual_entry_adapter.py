from app.models.manual_entry import ManualEntry
from app.schemas.manual_entry import ManualEntryIn, ManualEntryOut
from app.utils.datetime_utc import ensure_utc, parse_timestamp_utc
from app.utils.manual_entry_normalize import normalize_manual_entry_values


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
        values_normalized=normalize_manual_entry_values(entry.type, raw),
    )


def apply_entry_update(existing: ManualEntry, entry: ManualEntryIn) -> None:
    raw = dict(entry.values)
    existing.type = entry.type
    existing.timestamp_utc = parse_timestamp_utc(entry.timestamp)
    existing.context = entry.context
    existing.notes = entry.notes
    existing.values_raw = raw
    existing.values_normalized = normalize_manual_entry_values(entry.type, raw)


def entry_to_out(entry: ManualEntry) -> ManualEntryOut:
    return ManualEntryOut(
        id=entry.id,
        type=entry.type,
        timestamp=ensure_utc(entry.timestamp_utc),
        values=entry.values_normalized,
        values_raw=entry.values_raw,
        context=entry.context,
        notes=entry.notes,
    )

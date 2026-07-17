from sqlalchemy.orm import Session

from app.ingestion.adapters.manual_entry_adapter import (
    apply_entry_update,
    entry_in_to_model,
    entry_to_out,
)
from app.models.manual_entry import ManualEntry
from app.models.patient import Patient
from app.schemas.manual_entry import ManualEntryBatch, ManualEntryUpdateResult
from app.services.profile_service import ProfileNotFoundError


def upsert_manual_entries(db: Session, payload: ManualEntryBatch) -> ManualEntryUpdateResult:
    patient = db.get(Patient, payload.patient_id)
    if patient is None:
        raise ProfileNotFoundError(payload.patient_id)

    created = 0
    updated = 0
    results: list[ManualEntry] = []

    for entry in payload.entries:
        existing = db.get(ManualEntry, entry.id)
        if existing is None:
            model = entry_in_to_model(payload.patient_id, entry)
            db.add(model)
            results.append(model)
            created += 1
        else:
            if existing.patient_id != payload.patient_id:
                raise ValueError(
                    f"Entry {entry.id} belongs to patient {existing.patient_id}, "
                    f"not {payload.patient_id}"
                )
            apply_entry_update(existing, entry)
            results.append(existing)
            updated += 1

    db.commit()
    for model in results:
        db.refresh(model)

    return ManualEntryUpdateResult(
        patient_id=payload.patient_id,
        created=created,
        updated=updated,
        entries=[entry_to_out(e) for e in results],
    )

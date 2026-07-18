"""Apple Health wearable export ingest orchestration."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.ingestion.adapters.apple_health_adapter import parse_apple_health_export
from app.models.patient import Patient
from app.models.wearable_observation import WearableObservation
from app.schemas.wearable import (
    WearableIngestResult,
    WearableMeOut,
    WearableObservationOut,
    WearableObservationsOut,
)
from app.services.profile_service import ProfileNotFoundError

_DEFAULT_WEARABLE_LIMIT = 200
_MAX_WEARABLE_LIMIT = 2000


def _ensure_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _ensure_patient(db: Session, patient_id: str) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise ProfileNotFoundError(patient_id)
    return patient


def _profile_match(patient: Patient, me_dob: str | None) -> bool:
    if not me_dob:
        return False
    try:
        export_dob = date.fromisoformat(me_dob)
    except ValueError:
        return False
    return export_dob == patient.date_of_birth


def _observation_to_out(row: WearableObservation) -> WearableObservationOut:
    return WearableObservationOut(
        id=row.id,
        patient_id=row.patient_id,
        metric_type=row.metric_type,
        hk_type=row.hk_type,
        start_at=row.start_at,
        end_at=row.end_at,
        source_name=row.source_name,
        unit=row.unit,
        value_raw=row.value_raw,
        value_normalized=row.value_normalized,
        metadata_json=row.metadata_json,
    )


def list_wearable_observations(
    db: Session,
    patient_id: str,
    *,
    metric_type: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = _DEFAULT_WEARABLE_LIMIT,
) -> WearableObservationsOut:
    _ensure_patient(db, patient_id)

    start = _ensure_aware(start)
    end = _ensure_aware(end)
    if start is not None and end is not None and start > end:
        raise ValueError("`start` must be <= `end`")

    capped = max(1, min(limit, _MAX_WEARABLE_LIMIT))
    query = db.query(WearableObservation).filter(
        WearableObservation.patient_id == patient_id
    )
    if metric_type is not None:
        query = query.filter(WearableObservation.metric_type == metric_type)
    # Window on observation end time (same clock used for "latest" ordering).
    if start is not None:
        query = query.filter(WearableObservation.end_at >= start)
    if end is not None:
        query = query.filter(WearableObservation.end_at <= end)

    rows = (
        query.order_by(WearableObservation.end_at.desc()).limit(capped).all()
    )
    observations = [_observation_to_out(row) for row in rows]
    return WearableObservationsOut(
        patient_id=patient_id,
        count=len(observations),
        limit=capped,
        metric_type=metric_type,
        start=start,
        end=end,
        observations=observations,
    )


def ingest_wearable_export(
    db: Session,
    *,
    patient_id: str,
    xml_bytes: bytes,
) -> WearableIngestResult:
    patient = _ensure_patient(db, patient_id)
    parsed = parse_apple_health_export(xml_bytes)

    db.query(WearableObservation).filter(
        WearableObservation.patient_id == patient_id
    ).delete()

    by_metric: Counter[str] = Counter()
    sources: set[str] = set()

    for obs in parsed.observations:
        db.add(
            WearableObservation(
                id=str(uuid4()),
                patient_id=patient_id,
                metric_type=obs.metric_type,
                hk_type=obs.hk_type,
                start_at=obs.start_at,
                end_at=obs.end_at,
                source_name=obs.source_name,
                unit=obs.unit,
                value_raw=obs.value_raw,
                value_normalized=obs.value_normalized,
                metadata_json=obs.metadata_json,
            )
        )
        by_metric[obs.metric_type] += 1
        if obs.source_name:
            sources.add(obs.source_name)

    db.commit()

    me_out = WearableMeOut(
        date_of_birth=parsed.me.date_of_birth,
        biological_sex=parsed.me.biological_sex,
        blood_type=parsed.me.blood_type,
    )

    return WearableIngestResult(
        patient_id=patient_id,
        export_date=parsed.export_date,
        records_ingested=len(parsed.observations),
        records_skipped=parsed.records_skipped,
        by_metric=dict(by_metric),
        sources=sorted(sources),
        me=me_out,
        profile_match=_profile_match(patient, parsed.me.date_of_birth),
        profile_date_of_birth=patient.date_of_birth,
    )

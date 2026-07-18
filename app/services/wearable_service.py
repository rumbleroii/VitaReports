"""Wearable export ingest orchestration."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date, datetime
from typing import Any
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
from app.utils.datetime_utc import ensure_utc, utc_now

_DEFAULT_WEARABLE_LIMIT = 200
_MAX_WEARABLE_LIMIT = 2000
_VALID_SOURCE_TYPES = {"apple_health"}


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


def observation_fingerprint(
    *,
    patient_id: str,
    metric_type: str,
    hk_type: str,
    start_at: datetime,
    end_at: datetime,
    source_name: str | None,
    value_normalized: dict[str, Any],
) -> str:
    """Stable id for an exact sample (idempotent re-ingest / within-file dupes)."""
    payload = {
        "patient_id": patient_id,
        "metric_type": metric_type,
        "hk_type": hk_type,
        "start_at": ensure_utc(start_at).isoformat(),
        "end_at": ensure_utc(end_at).isoformat(),
        "source_name": source_name or "",
        "value": value_normalized,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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

    start = ensure_utc(start)
    end = ensure_utc(end)
    if start is not None and end is not None and start > end:
        raise ValueError("`start` must be <= `end`")

    capped = max(1, min(limit, _MAX_WEARABLE_LIMIT))
    query = db.query(WearableObservation).filter(
        WearableObservation.patient_id == patient_id
    )
    if metric_type is not None:
        query = query.filter(WearableObservation.metric_type == metric_type)
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
    file_bytes: bytes,
    source_type: str = "apple_health",
) -> WearableIngestResult:
    if source_type not in _VALID_SOURCE_TYPES:
        raise ValueError(f"Unsupported source_type: {source_type}")

    patient = _ensure_patient(db, patient_id)

    if source_type == "apple_health":
        parsed = parse_apple_health_export(file_bytes)
    else:
        raise ValueError(f"Unsupported source_type: {source_type}")

    # Append + fingerprint dedupe (no wipe). Exact sample twice → skip;
    # same time / different value or source → new fingerprint → insert.
    known = {
        fp
        for (fp,) in db.query(WearableObservation.fingerprint)
        .filter(WearableObservation.patient_id == patient_id)
        .all()
    }

    by_metric: Counter[str] = Counter()
    sources: set[str] = set()
    ingested = 0
    duplicates = 0
    future_skipped = 0
    now = utc_now()

    for obs in parsed.observations:
        start_at = ensure_utc(obs.start_at)
        end_at = ensure_utc(obs.end_at)
        assert start_at is not None and end_at is not None

        if end_at > now:
            future_skipped += 1
            continue

        fp = observation_fingerprint(
            patient_id=patient_id,
            metric_type=obs.metric_type,
            hk_type=obs.hk_type,
            start_at=start_at,
            end_at=end_at,
            source_name=obs.source_name,
            value_normalized=obs.value_normalized,
        )
        if fp in known:
            duplicates += 1
            continue

        known.add(fp)
        db.add(
            WearableObservation(
                id=str(uuid4()),
                patient_id=patient_id,
                fingerprint=fp,
                metric_type=obs.metric_type,
                hk_type=obs.hk_type,
                start_at=start_at,
                end_at=end_at,
                source_name=obs.source_name,
                unit=obs.unit,
                value_raw=obs.value_raw,
                value_normalized=obs.value_normalized,
                metadata_json=obs.metadata_json,
            )
        )
        ingested += 1
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
        source_type=source_type,
        export_date=parsed.export_date,
        records_ingested=ingested,
        records_skipped=parsed.records_skipped,
        records_duplicate=duplicates,
        records_future_skipped=future_skipped,
        by_metric=dict(by_metric),
        sources=sorted(sources),
        me=me_out,
        profile_match=_profile_match(patient, parsed.me.date_of_birth),
        profile_date_of_birth=patient.date_of_birth,
    )

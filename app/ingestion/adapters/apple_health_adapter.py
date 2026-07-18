"""Parse Apple Health export XML into normalized wearable observations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from xml.etree import ElementTree as ET

from dateutil import parser as date_parser

from app.utils.datetime_utc import ensure_utc


HK_TYPE_TO_METRIC: dict[str, str] = {
    "HKQuantityTypeIdentifierHeartRate": "heart_rate",
    "HKQuantityTypeIdentifierOxygenSaturation": "spo2",
    "HKQuantityTypeIdentifierStepCount": "steps",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "hrv_sdnn",
    "HKCategoryTypeIdentifierSleepAnalysis": "sleep",
}

SLEEP_STAGE_MAP: dict[str, str] = {
    "HKCategoryValueSleepAnalysisAsleepCore": "core",
    "HKCategoryValueSleepAnalysisAsleepDeep": "deep",
    "HKCategoryValueSleepAnalysisAsleepREM": "rem",
    "HKCategoryValueSleepAnalysisAwake": "awake",
    "HKCategoryValueSleepAnalysisAsleepUnspecified": "unspecified",
    "HKCategoryValueSleepAnalysisInBed": "in_bed",
}


@dataclass
class ParsedMe:
    date_of_birth: str | None = None
    biological_sex: str | None = None
    blood_type: str | None = None


@dataclass
class ParsedObservation:
    metric_type: str
    hk_type: str
    start_at: datetime
    end_at: datetime
    source_name: str | None
    unit: str | None
    value_raw: dict[str, Any]
    value_normalized: dict[str, Any]
    metadata_json: dict[str, Any] | None


@dataclass
class AppleHealthParseResult:
    export_date: datetime | None = None
    me: ParsedMe = field(default_factory=ParsedMe)
    observations: list[ParsedObservation] = field(default_factory=list)
    records_skipped: int = 0


def _parse_hk_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return ensure_utc(date_parser.parse(value))


def _metadata_from_record(elem: ET.Element) -> dict[str, Any] | None:
    meta: dict[str, Any] = {}
    for child in elem:
        if child.tag == "MetadataEntry":
            key = child.get("key")
            if key:
                meta[key] = child.get("value")
    return meta or None


def _normalize_quantity(
    metric_type: str,
    raw_value: str,
    unit: str | None,
) -> tuple[dict[str, Any], dict[str, Any], str | None] | None:
    try:
        numeric = float(raw_value)
    except (TypeError, ValueError):
        return None

    value_raw: dict[str, Any] = {"value": numeric, "unit": unit}

    if metric_type == "heart_rate":
        resolved_unit = unit or "count/min"
        return value_raw, {"bpm": numeric}, resolved_unit

    if metric_type == "spo2":
        percent = numeric * 100.0 if unit == "%" and numeric <= 1.0 else numeric
        return value_raw, {"percent": percent}, "%"

    if metric_type == "steps":
        return value_raw, {"count": int(numeric) if numeric == int(numeric) else numeric}, unit or "count"

    if metric_type == "hrv_sdnn":
        return value_raw, {"ms": numeric}, unit or "ms"

    return None


def _normalize_sleep(
    raw_value: str,
    start_at: datetime,
    end_at: datetime,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    stage = SLEEP_STAGE_MAP.get(raw_value)
    if stage is None:
        # Strip common prefix if present for unknown variants
        prefix = "HKCategoryValueSleepAnalysis"
        if raw_value.startswith(prefix):
            stage = raw_value[len(prefix) :].lstrip("_").lower() or None
        else:
            stage = None
    if stage is None:
        return None

    duration_minutes = (end_at - start_at).total_seconds() / 60.0
    value_raw = {"value": raw_value}
    value_normalized = {"stage": stage, "duration_minutes": duration_minutes}
    return value_raw, value_normalized


def parse_apple_health_export(xml_bytes: bytes) -> AppleHealthParseResult:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid Apple Health XML: {exc}") from exc

    if root.tag != "HealthData":
        raise ValueError(f"Expected HealthData root element, got {root.tag}")

    result = AppleHealthParseResult()

    export_elem = root.find("ExportDate")
    if export_elem is not None:
        result.export_date = _parse_hk_timestamp(export_elem.get("value"))

    me_elem = root.find("Me")
    if me_elem is not None:
        result.me = ParsedMe(
            date_of_birth=me_elem.get("HKCharacteristicTypeIdentifierDateOfBirth"),
            biological_sex=me_elem.get("HKCharacteristicTypeIdentifierBiologicalSex"),
            blood_type=me_elem.get("HKCharacteristicTypeIdentifierBloodType"),
        )

    for record in root.findall("Record"):
        hk_type = record.get("type")
        if not hk_type or hk_type not in HK_TYPE_TO_METRIC:
            result.records_skipped += 1
            continue

        metric_type = HK_TYPE_TO_METRIC[hk_type]
        raw_value = record.get("value")
        if raw_value is None or raw_value == "":
            result.records_skipped += 1
            continue

        start_at = _parse_hk_timestamp(record.get("startDate"))
        end_at = _parse_hk_timestamp(record.get("endDate"))
        if start_at is None or end_at is None:
            result.records_skipped += 1
            continue

        unit = record.get("unit")
        source_name = record.get("sourceName")
        metadata_json = _metadata_from_record(record)

        if metric_type == "sleep":
            sleep_norm = _normalize_sleep(raw_value, start_at, end_at)
            if sleep_norm is None:
                result.records_skipped += 1
                continue
            value_raw, value_normalized = sleep_norm
            resolved_unit = None
        else:
            qty = _normalize_quantity(metric_type, raw_value, unit)
            if qty is None:
                result.records_skipped += 1
                continue
            value_raw, value_normalized, resolved_unit = qty

        result.observations.append(
            ParsedObservation(
                metric_type=metric_type,
                hk_type=hk_type,
                start_at=start_at,
                end_at=end_at,
                source_name=source_name,
                unit=resolved_unit,
                value_raw=value_raw,
                value_normalized=value_normalized,
                metadata_json=metadata_json,
            )
        )

    return result

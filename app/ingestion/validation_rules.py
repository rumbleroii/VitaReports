"""Required-field rules and match thresholds for report extraction."""

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel

from app.schemas.reports_common import KidneyFinding, QuantitativeValue

MATCH_THRESHOLD = 0.85
FIELD_CONFIDENCE_MIN = 0.70

ReportType = str


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _has_list(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0


def _has_quant(value: Any) -> bool:
    if not isinstance(value, QuantitativeValue):
        return False
    return value.value_num is not None or bool(value.value_text and value.value_text.strip())


def _has_kidney(value: Any) -> bool:
    if not isinstance(value, KidneyFinding):
        return False
    return bool(
        (value.body and value.body.strip())
        or (value.size_text and value.size_text.strip())
        or (value.bosniak_category and value.bosniak_category.strip())
    )


def _get(report: BaseModel, name: str) -> Any:
    return getattr(report, name, None)


def _identity_ok(report: BaseModel) -> bool:
    return _has_text(_get(report, "mrn")) or _has_text(_get(report, "patient_name"))


def _cbc_missing(report: BaseModel) -> list[str]:
    missing: list[str] = []
    if not _has_text(_get(report, "patient_name")):
        missing.append("patient_name")
    if _get(report, "test_date") is None:
        missing.append("test_date")
    for name in ("hemoglobin", "wbc", "platelets"):
        if not _has_quant(_get(report, name)):
            missing.append(name)
    return missing


def _echo_missing(report: BaseModel) -> list[str]:
    missing: list[str] = []
    if not _has_text(_get(report, "patient_name")):
        missing.append("patient_name")
    if _get(report, "study_date") is None:
        missing.append("study_date")
    if not _has_quant(_get(report, "ef_percent")):
        missing.append("ef_percent")
    if not _has_list(_get(report, "impression")):
        missing.append("impression")
    return missing


def _radiology_missing(report: BaseModel) -> list[str]:
    missing: list[str] = []
    if not (_has_text(_get(report, "patient_name")) or _has_text(_get(report, "mrn"))):
        missing.append("patient_name|mrn")
    if not _has_text(_get(report, "findings")):
        missing.append("findings")
    if not _has_list(_get(report, "impression")):
        missing.append("impression")
    return missing


def _ultrasound_missing(report: BaseModel) -> list[str]:
    missing: list[str] = []
    if not _has_text(_get(report, "patient_name")):
        missing.append("patient_name")
    if _get(report, "exam_date") is None:
        missing.append("exam_date")
    if not (_has_kidney(_get(report, "right_kidney")) or _has_kidney(_get(report, "left_kidney"))):
        missing.append("right_kidney|left_kidney")
    if not _has_list(_get(report, "impression")):
        missing.append("impression")
    return missing


REQUIRED_CHECKS: dict[str, Callable[[BaseModel], list[str]]] = {
    "cbc": _cbc_missing,
    "echo": _echo_missing,
    "chest_radiology": _radiology_missing,
    "renal_ultrasound": _ultrasound_missing,
}


def field_has_usable_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, QuantitativeValue):
        return _has_quant(value)
    if isinstance(value, KidneyFinding):
        return _has_kidney(value)
    if isinstance(value, list):
        return _has_list(value)
    if isinstance(value, str):
        return _has_text(value)
    if isinstance(value, BaseModel):
        # NarrativeSection etc. — any non-empty dumped field
        dumped = value.model_dump()
        return any(
            (isinstance(v, str) and v.strip()) or v not in (None, [], {})
            for v in dumped.values()
        )
    return True

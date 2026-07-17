"""Validate extracted reports: required hard-fail + match-rate gate."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel

from app.ingestion.extractors.fields import ExtractedField
from app.ingestion.validation_rules import (
    FIELD_CONFIDENCE_MIN,
    MATCH_THRESHOLD,
    REQUIRED_CHECKS,
    field_has_usable_value,
)
from app.schemas.extraction import FieldMatchDetail


@dataclass
class ValidationVerdict:
    accepted: bool
    match_rate: float
    match_percent: int
    missing_required: list[str] = field(default_factory=list)
    field_details: list[FieldMatchDetail] = field(default_factory=list)
    error: str | None = None
    report: BaseModel | None = None


class SchemaValidatorService:
    def validate(
        self,
        report: BaseModel,
        confidences: dict[str, ExtractedField],
        report_type: str,
    ) -> ValidationVerdict:
        check = REQUIRED_CHECKS.get(report_type)
        if check is None:
            return ValidationVerdict(
                accepted=False,
                match_rate=0.0,
                match_percent=0,
                error=f"Unsupported report_type: {report_type}",
            )

        missing_required = check(report)
        field_details = self._build_field_details(report, confidences)

        matched = sum(1 for d in field_details if d.status == "matched")
        total = len(field_details) or 1
        match_rate = matched / total
        match_percent = int(round(match_rate * 100))

        if missing_required:
            return ValidationVerdict(
                accepted=False,
                match_rate=match_rate,
                match_percent=match_percent,
                missing_required=missing_required,
                field_details=field_details,
                error=f"Missing required fields: {', '.join(missing_required)}",
            )

        if match_rate < MATCH_THRESHOLD:
            return ValidationVerdict(
                accepted=False,
                match_rate=match_rate,
                match_percent=match_percent,
                missing_required=[],
                field_details=field_details,
                error=(
                    f"Field match {match_percent}% below "
                    f"{int(MATCH_THRESHOLD * 100)}% threshold"
                ),
            )

        return ValidationVerdict(
            accepted=True,
            match_rate=match_rate,
            match_percent=match_percent,
            missing_required=[],
            field_details=field_details,
            report=report,
        )

    def _build_field_details(
        self,
        report: BaseModel,
        confidences: dict[str, ExtractedField],
    ) -> list[FieldMatchDetail]:
        details: list[FieldMatchDetail] = []
        for name in report.model_fields:
            value = getattr(report, name, None)
            extracted = confidences.get(name)
            confidence = extracted.confidence if extracted else 0.0
            source_label = extracted.source_label if extracted else None
            usable = field_has_usable_value(value)

            if usable and confidence >= FIELD_CONFIDENCE_MIN:
                status = "matched"
            elif usable and 0 < confidence < FIELD_CONFIDENCE_MIN:
                status = "low_confidence"
            elif not usable and confidence > 0:
                status = "low_confidence"
            else:
                status = "missing"

            details.append(
                FieldMatchDetail(
                    field=name,
                    status=status,
                    confidence=confidence if confidence > 0 else None,
                    source_label=source_label,
                )
            )
        return details

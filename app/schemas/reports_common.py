"""Shared building blocks for typed hospital report schemas."""

from pydantic import BaseModel


class QuantitativeValue(BaseModel):
    """A numeric (or text) lab/measurement value with optional reference range."""

    value_num: float | None = None
    value_text: str | None = None
    unit: str | None = None
    reference_range: str | None = None
    flag: str | None = None


class LabRow(BaseModel):
    """A CBC table row whose English label was ambiguous or font-encoded."""

    name: str
    result: QuantitativeValue


class NarrativeSection(BaseModel):
    """A titled narrative block (Findings, Impression subsection, etc.)."""

    title: str
    body: str


class KidneyFinding(BaseModel):
    """Structured kidney observation from a renal ultrasound."""

    size_text: str | None = None
    body: str | None = None
    bosniak_category: str | None = None

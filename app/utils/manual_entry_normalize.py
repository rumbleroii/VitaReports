"""Normalize manual-entry value payloads into canonical field names / units.

Use this at ingest boundaries for manual entries (create/update). Downstream
readers should consume already-normalized `values_normalized` from the DB.

This is not for Apple Health quantities, OCR labels, or medication text —
those have their own domain-specific normalizers.
"""

from __future__ import annotations

from typing import Any

# Standard clinical conversion: mmol/L * 18.018 ≈ mg/dL
MMOL_L_TO_MG_DL = 18.018


def normalize_manual_entry_values(entry_type: str, values: dict[str, Any]) -> dict[str, Any]:
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

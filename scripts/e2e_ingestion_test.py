"""E2E collection runner using reassignmentcheckin fixtures.

Mirrors thunder-tests/thunder-collection_VitaReports.json suggested order:
create-profile → update-manual-entry → extract-lab-reports / ingest-wearable-export
→ GET profile → health-snapshot GETs (composite + granular).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = REPO_ROOT.parent / "reassignmentcheckin"


def main() -> int:
    if not DATA.is_dir():
        print(f"Fixture dir not found: {DATA}")
        return 1

    results: list[tuple[str, bool, str]] = []

    def log(name: str, ok: bool, detail: str = "") -> None:
        status = "PASS" if ok else "FAIL"
        results.append((name, ok, detail))
        print(f"[{status}] {name}")
        if detail:
            print(f"       {detail}")

    client = httpx.Client(base_url=BASE, timeout=120.0)

    r = client.get("/health")
    log("GET /health", r.status_code == 200, f"status={r.status_code}")

    profile = json.loads((DATA / "patient_profile.json").read_text(encoding="utf-8"))
    pid = profile["patient_id"]
    r = client.post("/create-profile", json=profile)
    if r.status_code == 201:
        log(
            "POST /create-profile",
            True,
            f"patient={pid} name={r.json()['demographics']['name']}",
        )
    elif r.status_code == 409:
        log("POST /create-profile", True, f"patient={pid} already exists (409)")
    else:
        log("POST /create-profile", False, f"status={r.status_code} {r.text[:300]}")

    entries = json.loads((DATA / "manual_entries.json").read_text(encoding="utf-8"))
    r = client.post("/update-manual-entry", json=entries)
    if r.status_code == 200:
        body = r.json()
        log(
            "POST /update-manual-entry",
            True,
            f"created={body['created']} updated={body['updated']} total={len(body['entries'])}",
        )
    else:
        log("POST /update-manual-entry", False, f"status={r.status_code} {r.text[:300]}")

    lab_files = [
        ("cbc", DATA / "lab_cbc_kauh.pdf"),
        ("echo", DATA / "echocardiogram_fakeeh.pdf"),
        ("chest_radiology", DATA / "PHOTO-2026-05-25-18-43-01.jpg"),
        ("renal_ultrasound", DATA / "renal_ultrasound_sgh.pdf"),
    ]

    for report_type, path in lab_files:
        if not path.is_file():
            log(f"POST /extract-lab-reports ({report_type})", False, f"missing file {path}")
            continue
        with path.open("rb") as handle:
            response = client.post(
                "/extract-lab-reports",
                data={"patient_id": pid, "report_type": report_type},
                files=[("files", (path.name, handle, "application/octet-stream"))],
            )
        if response.status_code != 200:
            log(
                f"POST /extract-lab-reports ({report_type})",
                False,
                f"status={response.status_code} {response.text[:300]}",
            )
            continue

        file_result = response.json()["results"][0]
        ok = file_result["status"] == "accepted"
        detail = (
            f"status={file_result['status']} "
            f"match={file_result.get('match_percent')}% "
            f"error={file_result.get('error')}"
        )
        if ok and file_result.get("report"):
            content = file_result["report"].get("content", {})
            detail += f" sample_fields={list(content.keys())[:8]}"
        log(f"POST /extract-lab-reports ({report_type})", ok, detail)

    wearable_path = DATA / "wearable_export.xml"
    if wearable_path.is_file():
        with wearable_path.open("rb") as handle:
            response = client.post(
                "/ingest-wearable-export",
                data={"patient_id": pid, "source_type": "apple_health"},
                files=[("file", (wearable_path.name, handle, "application/xml"))],
            )
        if response.status_code == 200:
            body = response.json()
            log(
                "POST /ingest-wearable-export",
                True,
                f"records_ingested={body.get('records_ingested')} "
                f"skipped={body.get('records_skipped')} "
                f"duplicate={body.get('records_duplicate')} "
                f"future={body.get('records_future_skipped')} "
                f"by_metric={body.get('by_metric')}",
            )
        else:
            log(
                "POST /ingest-wearable-export",
                False,
                f"status={response.status_code} {response.text[:300]}",
            )
    else:
        log("POST /ingest-wearable-export", False, f"missing file {wearable_path}")

    r = client.get(f"/profile/{pid}")
    if r.status_code == 200:
        body = r.json()
        log(
            "GET /profile/{id}",
            True,
            f"conditions={len(body['profile']['conditions'])} "
            f"meds={len(body['profile']['medications'])} "
            f"manual_entries={len(body['manual_entries'])}",
        )
    else:
        log("GET /profile/{id}", False, f"status={r.status_code} {r.text[:200]}")

    # --- Health Snapshot collection ---
    r = client.get(f"/health-snapshot/{pid}")
    if r.status_code == 200:
        snap = r.json()
        ok = (
            snap.get("patient_id") == pid
            and "recent_vitals" in snap
            and "medication_adherence" in snap
            and "symptoms" in snap
            and "hospital_findings" in snap
            and "care_attention" in snap
        )
        log(
            "GET /health-snapshot/{id}",
            ok,
            f"vitals={len(snap.get('recent_vitals', {}).get('vitals', []))} "
            f"meds={len(snap.get('medication_adherence', {}).get('medications', []))} "
            f"symptoms={len(snap.get('symptoms', {}).get('symptoms', []))} "
            f"findings={len(snap.get('hospital_findings', {}).get('findings', []))} "
            f"care={len(snap.get('care_attention', {}).get('items', []))} "
            f"vital_anoms={len(snap.get('recent_vitals', {}).get('anomalies', []))} "
            f"med_anoms={len(snap.get('medication_adherence', {}).get('anomalies', []))} "
            f"finding_anoms={len(snap.get('hospital_findings', {}).get('anomalies', []))}",
        )
    else:
        log("GET /health-snapshot/{id}", False, f"status={r.status_code} {r.text[:300]}")

    # Point-in-time window aligned to fixture manual-entry timestamps (2026-04-08)
    as_of = "2026-04-09T12:00:00Z"
    window_hours = 48
    r = client.get(
        f"/health-snapshot/{pid}",
        params={"as_of": as_of, "window_hours": window_hours},
    )
    if r.status_code == 200:
        snap = r.json()
        meds = snap.get("medication_adherence", {}).get("medications", [])
        recorded_any = any((m.get("recorded_doses_48h") or 0) > 0 for m in meds)
        vitals = snap.get("recent_vitals", {}).get("vitals", [])
        ok = (
            snap.get("patient_id") == pid
            and snap.get("window_hours") == window_hours
            and len(vitals) >= 1
            and recorded_any
        )
        log(
            "GET /health-snapshot/{id}?as_of&window_hours",
            ok,
            f"as_of={as_of} window={window_hours} "
            f"vitals={len(vitals)} "
            f"meds_with_doses={sum(1 for m in meds if (m.get('recorded_doses_48h') or 0) > 0)} "
            f"symptoms={len(snap.get('symptoms', {}).get('symptoms', []))} "
            f"overall={snap.get('medication_adherence', {}).get('overall_status')}",
        )
    else:
        log(
            "GET /health-snapshot/{id}?as_of&window_hours",
            False,
            f"status={r.status_code} {r.text[:300]}",
        )

    snapshot_paths = [
        ("recent-vitals", "vitals", "anomalies"),
        ("medication-adherence", "medications", "anomalies"),
        ("symptoms", "symptoms", None),
        ("hospital-findings", "findings", "anomalies"),
        ("care-attention", "items", None),
    ]
    for path_suffix, list_key, anom_key in snapshot_paths:
        name = f"GET /health-snapshot/.../{path_suffix}"
        r = client.get(f"/health-snapshot/{pid}/{path_suffix}")
        if r.status_code != 200:
            log(name, False, f"status={r.status_code} {r.text[:200]}")
            continue
        body = r.json()
        items = body.get(list_key, [])
        detail = f"{list_key}={len(items)}"
        if anom_key is not None:
            detail += f" anomalies={len(body.get(anom_key, []))}"
        ok = body.get("patient_id") == pid and isinstance(items, list)
        log(name, ok, detail)

    print("\n=== SUMMARY ===")
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"{passed}/{len(results)} passed")
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':4} {name}" + (f" — {detail}" if detail else ""))

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())

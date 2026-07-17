"""Quick e2e ingestion test using reassignmentcheckin fixtures."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
DATA = Path(r"C:\Users\mrith\Desktop\VitaRC Assignment\reassignmentcheckin")


def main() -> int:
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
    r = client.post("/create-profile", json=profile)
    if r.status_code == 201:
        log(
            "POST /create-profile",
            True,
            f"patient={profile['patient_id']} name={r.json()['demographics']['name']}",
        )
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

    pid = profile["patient_id"]
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

    lab_files = [
        ("cbc", DATA / "lab_cbc_kauh.pdf"),
        ("echo", DATA / "echocardiogram_fakeeh.pdf"),
        ("chest_radiology", DATA / "PHOTO-2026-05-25-18-43-01.jpg"),
        ("renal_ultrasound", DATA / "renal_ultrasound_sgh.pdf"),
    ]

    for report_type, path in lab_files:
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

    print("\n=== SUMMARY ===")
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"{passed}/{len(results)} passed")
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':4} {name}" + (f" — {detail}" if detail else ""))

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())

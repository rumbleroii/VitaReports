# VitaReports

Backend service for the Vitarc take-home: ingest heterogeneous patient data (profile, wearables, manual entries, hospital PDFs/images), store it in a unified patient-centric model, and expose a health-snapshot API with anomaly detection.

FastAPI layout follows the [bigger applications guide](https://fastapi.tiangolo.com/tutorial/bigger-applications/).

**Design write-up:** [WRITEUP.md](./WRITEUP.md) (architecture decisions, tradeoffs, scale note, LLM path).

## Layout

```
app/
  main.py
  db.py / dependencies.py
  routers/          # HTTP surface
  services/         # orchestration + snapshot + anomaly rules
  models/           # SQLAlchemy persistence
  schemas/          # Pydantic API / report contracts
  ingestion/
    adapters/       # profile, manual entry, Apple Health
    extractors/     # CBC / echo / radiology / ultrasound
postman/            # Postman collection + local environment
scripts/
  e2e_ingestion_test.py   # end-to-end against fixture pack
```

## Prerequisites

- Python 3.11+
- Fixture data directory (sibling of this repo): `../reassignmentcheckin/`
  - `patient_profile.json`, `manual_entries.json`, `wearable_export.xml`
  - `lab_cbc_kauh.pdf`, `echocardiogram_fakeeh.pdf`, `renal_ultrasound_sgh.pdf`
  - chest imaging as `PHOTO-2026-05-25-18-43-01.jpg` (OCR path; no `chest_xray_kauh.pdf` in the pack)

### System dependency (image OCR)

Image uploads require [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) on `PATH`.

- Windows: [UB Mannheim builds](https://github.com/UB-Mannheim/tesseract/wiki) or `winget install UB-Mannheim.TesseractOCR`
- PDFs use text parsing (`pdfplumber`) only — no OCR on PDFs

## Setup

```bash
cd VitaReports
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
```

SQLite database is created automatically at `data/vitarc.db` on first start.

## Run

```bash
uvicorn app.main:app --reload
```

- Health: `GET http://127.0.0.1:8000/health`
- OpenAPI docs: `http://127.0.0.1:8000/docs`

## Exercise the API (Sara Shalabi flow)

Suggested order matches the fixture pack and Postman collection.

### 1. Create profile

```http
POST /create-profile
Content-Type: application/json
```

Body: contents of `reassignmentcheckin/patient_profile.json`.

### 2. Manual entries

```http
POST /update-manual-entry
Content-Type: application/json
```

Body: contents of `reassignmentcheckin/manual_entries.json`.

### 3. Lab / imaging reports

```http
POST /extract-lab-reports
Content-Type: multipart/form-data
```

Form fields:

| Field | Values |
|---|---|
| `patient_id` | from profile |
| `report_type` | `cbc` \| `echo` \| `chest_radiology` \| `renal_ultrasound` |
| `files` | one or more PDFs and/or images |

Example mapping:

| `report_type` | Fixture file |
|---|---|
| `cbc` | `lab_cbc_kauh.pdf` |
| `echo` | `echocardiogram_fakeeh.pdf` |
| `chest_radiology` | `PHOTO-2026-05-25-18-43-01.jpg` |
| `renal_ultrasound` | `renal_ultrasound_sgh.pdf` |

Validation: required fields hard-fail; otherwise accept only if field match ≥ 85%.

- **200** — at least one file accepted (partial rejects still listed in `results`)
- **422** — every file rejected (`accepted: 0`); body still includes per-file detail

### 4. Wearable export

```http
POST /ingest-wearable-export
Content-Type: multipart/form-data
```

- `patient_id`
- `file`: `wearable_export.xml` (Apple Health)

Re-ingest replaces that patient’s wearable observations (full-export semantics).

### 5. Health snapshot

```http
GET /health-snapshot/{patient_id}
GET /health-snapshot/{patient_id}?as_of=2026-04-09T12:00:00Z&window_hours=48
```

Also available as granular routes:

- `/recent-vitals`
- `/medication-adherence`
- `/symptoms`
- `/hospital-findings`
- `/care-attention`

The composite response answers: most recent vitals (when/how), medication adherence over the window, reported symptoms, clinically relevant hospital findings, and what the care team should pay attention to (anomalies).

### Automated smoke test

With the server running:

```bash
python scripts/e2e_ingestion_test.py
```

### Postman

Import `postman/VitaReports.postman_collection.json` and `postman/Local.postman_environment.json`.

## API surface (summary)

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness |
| POST | `/create-profile` | Ingest patient profile |
| GET | `/profile/{patient_id}` | Profile + manual entries |
| POST | `/update-manual-entry` | Upsert manual entries |
| POST | `/extract-lab-reports` | Parse/persist hospital documents |
| POST | `/ingest-wearable-export` | Parse/persist Apple Health XML |
| GET | `/health-snapshot/{patient_id}` | Composite snapshot + anomalies |
| GET | `/health-snapshot/{patient_id}/…` | Section endpoints |

## Assumptions worth knowing

- All timestamps are normalized to UTC at ingest.
- Anomaly thresholds are global clinical defaults (see `app/services/anomaly_rules.py`), not patient-specific.
- Cross-source anomaly correlation is deferred; see [WRITEUP.md](./WRITEUP.md).
- Profile facility lists (`hospital_records_sources` / `lab_records_sources`) are JSON on `patients`, not separate tables and not linked to ingested `lab_reports`.
- Schema is created with SQLAlchemy `create_all`. After model changes, delete `data/vitarc.db` and re-ingest (no migration layer in this take-home).

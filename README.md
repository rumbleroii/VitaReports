# VitaReports

FastAPI backend structured per the [official bigger applications guide](https://fastapi.tiangolo.com/tutorial/bigger-applications/).

## Layout

```
app/
  main.py           # FastAPI app + include_router
  dependencies.py   # Shared deps (settings)
  routers/
    health.py
    profile.py
    manual_entries.py
    lab_reports.py
  services/
    parsing_service.py      # PDF text/tables (pdfplumber)
    ocr_service.py          # Image OCR (Pillow + pytesseract)
    schema_validator_service.py
  ingestion/
    extractors/             # Synonym/regex field extractors
```

## Setup

```bash
cd VitaReports
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### System dependency (image OCR)

Image uploads require [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed on the host and available on `PATH`.

- Windows: install from [UB Mannheim builds](https://github.com/UB-Mannheim/tesseract/wiki) or `winget install UB-Mannheim.TesseractOCR`
- PDFs use text parsing only (`pdfplumber`) — no OCR on PDFs

## Run

```bash
uvicorn app.main:app --reload
```

- Root: `GET http://127.0.0.1:8000/`
- Health: `GET http://127.0.0.1:8000/health`
- Docs: `http://127.0.0.1:8000/docs`

### Lab report extraction

`POST /extract-lab-reports` (multipart):

- `patient_id`, `report_type` (`cbc` | `echo` | `chest_radiology` | `renal_ultrasound`)
- `files`: one or more PDFs and/or images (png/jpg/jpeg/webp/tif/tiff)

Per file: required fields hard-fail; otherwise accept only if field match ≥ 85% (scored against fields found in the document). Rejected files do not fail the whole batch.

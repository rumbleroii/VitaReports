# VitaReports

FastAPI backend for the Vitarc take-home: ingest patient data and expose a health-snapshot API.

## Setup

```bash
cd VitaReports
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
```

Image OCR (chest X-ray JPG) needs [Tesseract](https://github.com/tesseract-ocr/tesseract) on `PATH`.

## Run

```bash
uvicorn app.main:app --reload
```

- API: http://127.0.0.1:8000
- Docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

SQLite DB is created at `data/vitarc.db` on first start.

Fixture pack lives next to this repo: `../reassignmentcheckin/`.

## Postman

Import:

- `postman/VitaReports.postman_collection.json`
- `postman/Local.postman_environment.json`

Run the collection in order (profile → manual entries → labs → wearable → health snapshot).

## Layout

```
app/
  main.py
  routers/       # HTTP endpoints
  services/      # business logic + anomaly rules
  models/        # SQLAlchemy tables
  schemas/       # Pydantic contracts
  ingestion/     # adapters + lab extractors
postman/         # collection + local env
```

# VitaReports

FastAPI backend structured per the [official bigger applications guide](https://fastapi.tiangolo.com/tutorial/bigger-applications/).

## Layout

```
app/
  main.py           # FastAPI app + include_router
  dependencies.py   # Shared deps (settings)
  routers/
    health.py       # Health path operations
```

## Setup

```bash
cd VitaReports
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload
```

- Root: `GET http://127.0.0.1:8000/`
- Health: `GET http://127.0.0.1:8000/health`
- Docs: `http://127.0.0.1:8000/docs`

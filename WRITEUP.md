# VitaReports — Design Write-up

## Problem framing

Sara Shalabi’s data arrives from three hospitals, an Apple Watch export, and self-reported app entries. The job is not to build a medical product UI — it is to ingest heterogeneous inputs into a coherent store and expose a care-team-facing health snapshot with anomaly detection. Ambiguity is intentional; the decisions below are the ones I made under a five-hour budget.

## Architecture

**Stack.** FastAPI + SQLAlchemy + SQLite (local). Pydantic models define API contracts; SQLAlchemy models own persistence. Routers stay thin; services own orchestration; `app/ingestion/` owns parse/normalize/extract logic.

**Data model.** Heterogeneous sources do not share one row shape. I used a patient-centric relational model with typed source tables rather than a single generic event log:

- `patients` + related profile tables (conditions, medications, allergies, care team, hospital/lab source registries)
- `manual_entries` — app-reported vitals, meds, symptoms (normalized JSON payload + UTC timestamp)
- `wearable_observations` — Apple Health metrics with raw + normalized values
- `lab_reports` — structured report JSON keyed by report type (CBC, echo, chest radiology, renal ultrasound)

A “unified timeline” is a **query concern**, not a storage concern. The health-snapshot service joins these tables at read time, always carrying source id, capture time, and capture modality. That keeps write paths simple and lets each source keep the fidelity it needs (e.g. sleep stages vs CBC differentials).

**Ingestion pipeline.**

```
source file → adapter/parser → normalize units/time → validate → persist
                                      ↓
                              (labs) synonym/regex extractors
                                      ↓
                              schema + required-field gate (≥85% match)
```

Adapters are the extension point for a new source. Profile and manual entries are JSON-in; wearables go through an Apple Health XML adapter; hospital PDFs/images go through pdfplumber or Tesseract OCR, then report-type-specific extractors that tolerate bilingual headers and layout variation via synonyms rather than fixed coordinates.

**Health snapshot.** `GET /health-snapshot/{patient_id}` answers the five required questions: recent vitals (what/when/how), 48h medication adherence, reported symptoms, clinically relevant hospital findings, and care-attention items. Granular sub-routes exist for the same sections. `as_of` / `window_hours` support point-in-time evaluation against the fixture window.

**Anomaly detection.** Pure rule helpers (`anomaly_rules.py`) attached to snapshot sections:

| Class | Approach |
|---|---|
| Vital thresholds | Global clinical defaults (e.g. BP ≥140/90, SpO₂ &lt;94, HR outside 50–100, glucose with fasting context) |
| Trends | Directional movement across recent readings when the latest value is already over threshold |
| Medications | Expected dose count from frequency + scheduled-time delay windows |
| Document findings | Keyword / out-of-reference-range / high-relevance signals from structured reports |

Severity maps into care-attention priority. I deliberately kept rules transparent and attributable rather than opaque scoring.

## Key judgment calls

1. **Normalize at the edge.** Timestamps → UTC. Glucose mmol/L → mg/dL. SpO₂ fractional Apple values → percent. Downstream logic should not re-learn source quirks.
2. **Conservative lab persistence.** Required fields hard-fail; otherwise accept only if field match ≥85%. A bad extract is worse than a missing report. Batch semantics: one rejected file does not fail siblings; all-reject returns 422 with per-file detail.
3. **Global thresholds first.** Patient-specific ranges would be better long-term, but need longitudinal history and clinician override UX we do not have. Thresholds are centralized so they are easy to specialize later.
4. **Wearable re-ingest replaces the patient’s wearable set.** Safer for a full Apple export than inventing partial-merge dedup without a stable record id. Duplicate Apple records within one export are left as-is (snapshot uses latest / short history).
5. **Chest imaging fixture.** The data pack provides a JPG (`PHOTO-…jpg`) rather than `chest_xray_kauh.pdf`. The pipeline accepts images via OCR for that path — same extractor contract as PDF radiology.

## What I chose not to build

- **Cross-source correlation engine** (e.g. “high BP + missed ACE inhibitor + rising HR”). Architecture can host it; the snapshot already aggregates anomalies. Building a reliable correlator without clinician review would overclaim.
- **True event deduplication** across re-uploads and overlapping wearable windows.
- **PDF OCR fallback** for scanned-only PDFs (text-layer PDFs only via pdfplumber).
- **Auth, multi-tenancy, async workers, polished clinical terminology** — explicitly out of scope or not worth the timebox vs. a working end-to-end path.

## LLM / agentic integration (if this were production)

I would keep deterministic extraction as the default for structured labs and use an LLM as a **bounded assist**, not the system of record:

1. **Document understanding.** When synonym extractors miss fields or confidence is low, send OCR/text + a typed JSON schema (existing Pydantic report models) to a model with strict structured output. Validate with the same ≥85% / required-field gate before persist. Never write free-form model text into clinical tables.
2. **Narrative findings.** Use the model to propose candidate findings with citations back to source spans; a human or rule layer still decides relevance.
3. **Care-attention summarization.** An agent can rank and explain anomalies in plain language for the care team, but the underlying codes/severities remain rule-generated for auditability.
4. **Safety.** Prompt versioning, output schema validation, source attribution, and an “LLM-assisted” provenance flag on every derived field.

## Note on scale (1 patient → 10k concurrent)

Today: single-process FastAPI, SQLite, synchronous ingest. That is correct for the exercise dataset.

To serve thousands of concurrent patients I would evolve along these lines:

```
                    ┌─────────────┐
  clients ─────────►│ API (stateless) │──► Postgres (partitioned by patient_id)
                    └──────┬──────┘
                           │ enqueue
                    ┌──────▼──────┐
                    │ ingest workers│──► object store (raw PDFs/XML)
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ anomaly / snapshot│◄── Redis (hot snapshot cache)
                    │  materialization  │
                    └─────────────┘
```

- **Postgres** (or similar) with patient-scoped indexes; SQLite does not survive write concurrency.
- **Async ingestion** via a queue: uploads return a job id; workers parse/OCR/extract off the request path.
- **Idempotent writes** with source content hashes / Apple record keys to stop duplicate timelines.
- **Materialized snapshots** refreshed on ingest or on a short TTL, so care-team GETs are cheap reads.
- **Horizontal API replicas** behind a load balancer; keep business logic in services so workers and APIs share the same rules modules.
- Later: per-tenant isolation, audit log, and patient-specific threshold tables without changing the snapshot contract.

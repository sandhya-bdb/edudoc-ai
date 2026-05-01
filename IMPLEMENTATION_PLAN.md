# EduDoc AI AI Document Classification — Implementation Plan

## Workflow Diagram

```
                        ┌─────────────────────────────────┐
                        │        Uploaded Image            │
                        └──────────────┬──────────────────┘
                                       │
                        ┌──────────────▼──────────────────┐
                        │   Stage 1: Rules Engine          │
                        │   regex: ^transcript_                  │
                        └──────────────┬──────────────────┘
                                       │
                     ┌─────────────────┴──────────────────┐
               transcript_ match?                           no match
                     │                                     │
          ┌──────────▼──────────┐          ┌──────────────▼──────────────┐
          │  doc_type = "transcript"   │          │   Stage 2: EDU OCR           │
          │  method   = "rules"  │          │   easyocr → keyword regex    │
          │  ✓ DONE              │          └──────────────┬──────────────┘
          └─────────────────────┘                         │
                                          ┌──────────────┴──────────────┐
                                    EDU match?                     no match
                                          │                              │
                             ┌────────────▼────────┐   ┌───────────────▼─────────────┐
                             │  doc_type = "edu"   │   │  Stage 3: Gemini LLM         │
                             │  method   = "ocr"   │   │  gemma-4-31b-it              │
                             │  ✓ DONE             │   │  → Transcripts             │
                             └─────────────────────┘   │  → Claim Forms               │
                                                        │  → Certificates           │
                                                        │  → Student IDs             │
                                                        │  → Unknown                   │
                                                        └──────────────────────────────┘
                                                                     │
                                                        ┌────────────▼────────────────┐
                                                        │  doc_type = "image"          │
                                                        │  sub_type = <category>       │
                                                        │  method   = "llm"            │
                                                        │  ✓ DONE                      │
                                                        └─────────────────────────────┘

All stages emit @traceable spans → LangSmith (traces · tokens · latency)
All results served via FastAPI → Drag & Drop UI
Container deployed on Azure Container Apps via GitHub Actions CI/CD
```

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   Frontend UI                        │
│         Drag & Drop  ·  frontend/index.html          │
│  - Batch upload (all files in one POST)              │
│  - Concurrent server processing (asyncio.gather)     │
│  - Live progress bar + per-file status rows          │
│  - Color-coded badges: transcript/edu/image                │
└───────────────────┬─────────────────────────────────┘
                    │ POST /classify (multipart)
                    ▼
┌─────────────────────────────────────────────────────┐
│           FastAPI  ·  src/api.py  ·  Port 8000       │
│  POST /classify  ·  GET /health  ·  GET /metrics     │
│  asyncio.gather + run_in_executor (concurrent files) │
└────────────────────┬────────────────────────────────┘
                     │
          ┌──────────▼──────────┐
          │   src/classifier.py  │  (orchestrator)
          └──┬──────┬──────┬────┘
             │      │      │
    rules    │  ocr │  llm │
    engine   │      │      │
             ▼      ▼      ▼
┌────────────────────────────────────────────────────┐
│  src/monitoring.py  — LangSmith @traceable spans   │
│  trace_rules_engine · trace_edu_ocr                │
│  trace_llm_classify · trace_classify               │
└────────────────────────────────────────────────────┘
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
   LangSmith               Azure Monitor
   (traces/tokens)         (container logs)
```

## Decision Rules

| Condition | doc_type | method | Sent to LLM? |
|---|---|---|---|
| filename matches `^transcript_` (regex) | `transcript` | `rules` | No |
| OCR text contains EDU keywords | `edu` | `ocr` | No |
| Everything else | `image` | `llm` | Yes |

## Final File Layout

```
multimodal-ai/
├── src/
│   ├── rules_engine.py       # Step 1 ✅
│   ├── edu_detector.py       # Step 2 ✅
│   ├── llm_classifier.py     # Step 3 ✅
│   ├── classifier.py         # Step 4 ✅
│   ├── api.py                # Step 5 ✅
│   └── monitoring.py         # Step 7 ✅
├── frontend/
│   └── index.html            # Step 6 ✅
├── tests/
│   ├── test_rules_engine.py  # 11 tests  ✅
│   ├── test_edu_detector.py  # 21 tests  ✅
│   ├── test_llm_classifier.py # 32 tests ✅
│   ├── test_classifier.py    # 29 tests  ✅
│   ├── test_api.py           # 11 tests  ✅
│   └── test_monitoring.py    # 13 tests  ✅  (117 total)
├── infra/
│   ├── deploy.sh             # Step 9 ✅ Azure Container Apps
│   └── teardown.sh           # ✅
├── .github/workflows/
│   ├── ci.yml                # Step 10 ✅ test on every push
│   └── deploy.yml            # Step 10 ✅ deploy on merge to main
├── Dockerfile                # Step 8 ✅ two-stage build
├── .dockerignore             # Step 8 ✅
├── README.md                 # Step 10 ✅
├── pyproject.toml
└── .env.example
```

---

## Steps

### Phase 1 — Core Classification Engine

- [x] **Step 1 — Rules Engine** (`src/rules_engine.py`)
  - Compiled regex `re.compile(r"^transcript_")` — case-sensitive, anchored to start of filename
  - Strips directory prefix so full paths work (`dataset/transcript_x.png`)
  - Returns `RulesResult(filename, doc_type, send_to_llm)`
  - **Changed from plan:** Used `re.compile` regex instead of `str.startswith()` as requested
  - ✅ **11/11 tests passing**

- [x] **Step 2 — KYC Detector** (`src/edu_detector.py`)
  - 11 compiled regex patterns covering Aadhaar, PAN, Passport, Govt of India, DOB, 12-digit Aadhaar number, PAN card format
  - easyocr `Reader` is a lazy singleton — loaded once on first use, not at import time
  - `reader` is injectable (passed as parameter) so tests never load the real model
  - Returns `EduResult(filename, doc_type, send_to_llm, ocr_text)`
  - ✅ **21/21 tests passing**

- [x] **Step 3 — LLM Classifier** (`src/llm_classifier.py`)
  - Sends image bytes + structured prompt to `gemma-4-31b-it` via `google-genai`
  - Prompt instructs model to return exactly one category name
  - `_parse_category()` does case-insensitive match + strips whitespace, falls back to `"Unknown"`
  - Captures `input_tokens` and `output_tokens` from `response.usage_metadata`
  - `client` is injectable for testing — zero live API calls in test suite
  - Returns `LLMResult(filename, doc_type, sub_type, method, input_tokens, output_tokens, raw_response)`
  - ✅ **32/32 tests passing**

- [x] **Step 4 — Pipeline Orchestrator** (`src/classifier.py`)
  - `classify(filename, image_bytes, ocr_reader, llm_client)` — single document
  - `classify_dataset(dataset_dir, ...)` — scans all PNGs in a directory
  - Returns `ClassificationResult(filename, doc_type, sub_type, method, latency_ms, input_tokens, output_tokens)`
  - Each stage emits a LangSmith trace span (added in Step 7)
  - ✅ **29/29 tests passing**

---

### Phase 2 — FastAPI Server

- [x] **Step 5 — API Server** (`src/api.py`)
  - `POST /classify` — multipart file upload, returns JSON array
  - `GET /health` — liveness probe
  - `GET /metrics` — in-memory counters per method/doc_type/token usage
  - `GET /docs` — auto Swagger UI
  - **Changed from plan:** `asyncio.gather` + `run_in_executor` runs all uploaded files concurrently — `transcript_` files return in < 10 ms without waiting behind OCR/LLM calls
  - easyocr `Reader` and Gemini `Client` loaded once at startup via FastAPI `lifespan`
  - CORS middleware enabled for browser UI
  - ✅ **11/11 tests passing** (patched at `src.api.classify`)

---

### Phase 3 — Frontend UI

- [x] **Step 6 — Drag & Drop UI** (`frontend/index.html`)
  - Self-contained single HTML file, no external dependencies
  - Drag & drop + click-to-browse, deduplicates files by name
  - **Changed from plan (sequential → batch):** Sends all files in ONE `POST /classify` — server processes concurrently so `transcript_` files don't wait behind slow OCR/LLM calls
  - Results table appears immediately with `queued…` rows; fills in as server responds
  - Live progress bar + `Processing file N of M` text
  - Color-coded badges: transcript=blue, edu=orange, image=green, rules=purple, ocr=red, llm=teal
  - All controls (classify, clear, remove buttons, drop zone) disabled during processing
  - Summary bar: counts per type + average latency
  - Error banner for API failures and unsupported file types

---

### Phase 4 — Monitoring (LangSmith)

- [x] **Step 7 — LangSmith Integration** (`src/monitoring.py`)
  - Four `@traceable` functions forming a parent/child span tree:
    - `trace_classify` — top-level `chain` span per document
    - `trace_rules_engine` — `tool` span for Stage 1
    - `trace_edu_ocr` — `tool` span for Stage 2; records `ocr_text_length` not raw text (PII safety)
    - `trace_llm_classify` — `llm` span for Stage 3; records token breakdown
  - `record_token_usage()` extracts `input/output/total_tokens` from Gemini `usage_metadata`
  - Tracing is a **no-op** when `LANGCHAIN_TRACING_V2` is not set — CI safe
  - **Required env vars:**
    ```
    LANGCHAIN_TRACING_V2=true
    LANGCHAIN_API_KEY=<key>
    LANGCHAIN_PROJECT=edudoc-ai-classification
    ```
  - ✅ **13/13 tests passing**

---

### Phase 5 — Docker

- [x] **Step 8 — Dockerfile**
  - Two-stage build: `uv` builder → `python:3.12-slim` runtime
  - Installs OS libs for easyocr/opencv/weasyprint in runtime stage
  - **Pre-downloads easyocr models at build time** as `appuser` — container starts in ~10s not 60s
  - Runs as non-root `appuser` (with home dir so easyocr can write model cache)
  - `HEALTHCHECK` polls `/health` every 30s, 60s start period
  - 2 uvicorn workers for concurrency
  - **Fix applied during build:** Created home dir for `appuser` and set `EASYOCR_MODULE_PATH` to fix permission error on model cache write
  - ✅ **Build verified, `/classify` tested inside container**

---

### Phase 6 — Azure Deployment

- [x] **Step 9 — Azure Container Apps** (`infra/deploy.sh`)
  - **Changed from plan:** Azure instead of AWS (simpler setup, no separate load balancer, built-in HTTPS)
  - Provisions: Resource Group → ACR → Log Analytics → Container Apps Environment → Container App
  - Container App: 0.5 vCPU / 2 GB RAM, min 1 replica, max 3, public HTTPS ingress
  - Secrets (`GOOGLE_API_KEY`, `LANGCHAIN_API_KEY`) injected via Container Apps secret references
  - `infra/teardown.sh` for full cleanup
  - **CI/CD via `.github/workflows/deploy.yml`:**
    - Tests gate deploy (deploy only runs if tests pass)
    - `az acr build` builds in Azure cloud (no local Docker in CI)
    - `az containerapp update` rolling deploy
    - Smoke tests live `/health` endpoint post-deploy
    - OIDC login (no long-lived secrets in GitHub)

---

### Phase 7 — Documentation

- [x] **Step 10 — README + CI** (`README.md`, `.github/workflows/ci.yml`)
  - Professional README with ASCII architecture diagram, workflow diagram, full API reference, setup guide, deployment guide, test matrix, environment variable table
  - `ci.yml` runs all 117 tests on every push/PR — no real API keys needed

---

## Build Order Summary

| # | Deliverable | Test Gate | Status |
|---|---|---|---|
| 1 | Rules Engine | `pytest tests/test_rules_engine.py` — 11 passed | ✅ |
| 2 | KYC Detector | `pytest tests/test_edu_detector.py` — 21 passed | ✅ |
| 3 | LLM Classifier | `pytest tests/test_llm_classifier.py` — 32 passed | ✅ |
| 4 | Orchestrator | `pytest tests/test_classifier.py` — 29 passed | ✅ |
| 5 | FastAPI Server | `pytest tests/test_api.py` — 11 passed + Swagger check | ✅ |
| 6 | Frontend UI | Batch POST, live progress, controls locked during processing | ✅ |
| 7 | LangSmith Monitoring | `pytest tests/test_monitoring.py` — 13 passed | ✅ |
| 8 | Docker | `docker build` + `/classify` tested inside container | ✅ |
| 9 | Azure Deploy | `infra/deploy.sh` + GitHub Actions CI/CD pipeline | ✅ |
| 10 | README + CI | `ci.yml` + `deploy.yml` + `README.md` | ✅ |

**Total: 117 tests · 10 steps · all complete ✅**

## Key Changes vs Original Plan

| Area | Original Plan | What We Actually Built |
|---|---|---|
| Rules matching | `str.startswith("transcript_")` | `re.compile(r"^transcript_")` regex |
| API concurrency | Sequential file loop | `asyncio.gather` + `run_in_executor` |
| UI upload strategy | One request per file (sequential) | One batch request, server concurrent |
| Cloud provider | AWS ECS Fargate | Azure Container Apps |
| Metrics | OpenTelemetry + CloudWatch | LangSmith + Azure Monitor |
| Docker user | Root | Non-root `appuser` with home dir |
| easyocr models | Downloaded at runtime | Pre-baked into image at build time |

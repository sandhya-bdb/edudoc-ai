# EduDoc AI — Architecture & Design

Complete technical architecture documentation for the educational document classification system.

---

## 🔄 Three-Stage Classification Pipeline

### Stage 1: Rules Engine (src/rules_engine.py)

**Trigger:** Filename analysis  
**Method:** Regex pattern matching  
**Cost:** $0  
**Speed:** <1ms  

**Patterns matched:**
- `transcript_*` → doc_type = "transcript"
- `cert_*` → doc_type = "certificate"

---

### Stage 2: Educational OCR Detection (src/edu_detector.py)

**Trigger:** Documents unmatched at Stage 1  
**Method:** easyOCR text extraction + keyword matching  

**Document types detected:**
- Matches keywords like "University", "College", "Degree", "Transcript"

---

### Stage 3: Gemini LLM Classification (src/llm_classifier.py)

**Trigger:** All documents unmatched at Stages 1 & 2  
**Method:** Gemini API (gemma-4-31b-it)  

**Document types classified:**
- Transcripts
- Certificates
- Student IDs
- Admission Letters
- Assignment Papers

---

## ⚡ Async Concurrency Architecture

The FastAPI server uses `asyncio.gather` with a thread pool to process documents in parallel.

## 📊 Monitoring & Observability

### LangSmith Tracing (@traceable decorator)

Each stage emits structured spans to LangSmith.

## 🚀 Deployment Architecture

Built to run on Azure Container Apps with automated deployment via GitHub Actions (`.github/workflows/deploy.yml`).

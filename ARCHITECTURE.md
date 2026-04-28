# MediShield AI Document Classifier — Architecture & Design

Complete technical architecture documentation for the insurance document classification system.

---

## 📐 System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Browser / Client                                 │
│              Drag & Drop UI · frontend/index.html                        │
└────────────────────────────────┬──────────────────────────────────────────┘
                                 │ POST /classify (multipart/form-data)
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│              FastAPI Server · src/api.py · Port 8000                     │
│                                                                          │
│   ┌──────────────────────────────────────────────────────────────────┐  │
│   │              asyncio.gather → Concurrent Processing             │  │
│   │                                                                  │  │
│   │  ┌─────────────────────────────────────────────────────────┐    │  │
│   │  │     Orchestrator: src/classifier.py                      │    │  │
│   │  │                                                          │    │  │
│   │  │  ┌──────────────┐  bill_*   ┌──────────────────────┐   │    │  │
│   │  │  │ Stage 1      │──────────▶│  doc_type = "bill"   │   │    │  │
│   │  │  │ Rules Engine │           │  method   = "rules"  │   │    │  │
│   │  │  │              │           └──────────────────────┘   │    │  │
│   │  │  └──────┬───────┘                                       │    │  │
│   │  │         │ others                                        │    │  │
│   │  │         ▼                                               │    │  │
│   │  │  ┌──────────────┐  KYC kw   ┌──────────────────────┐   │    │  │
│   │  │  │ Stage 2      │──────────▶│  doc_type = "kyc"    │   │    │  │
│   │  │  │ KYC OCR      │           │  method   = "ocr"    │   │    │  │
│   │  │  │ (easyocr)    │           └──────────────────────┘   │    │  │
│   │  │  └──────┬───────┘                                       │    │  │
│   │  │         │ no KYC match                                  │    │  │
│   │  │         ▼                                               │    │  │
│   │  │  ┌──────────────┐           ┌──────────────────────┐   │    │  │
│   │  │  │ Stage 3      │──────────▶│  doc_type = "image"  │   │    │  │
│   │  │  │ Gemini LLM   │           │  sub_type = category │   │    │  │
│   │  │  │              │           │  method   = "llm"    │   │    │  │
│   │  │  └──────────────┘           └──────────────────────┘   │    │  │
│   │  │                                                          │    │  │
│   │  └─────────────────────────────────────────────────────────┘    │  │
│   │                                                                  │  │
│   │  ┌─────────────────────────────────────────────────────────┐    │  │
│   │  │           Monitoring: src/monitoring.py                │    │  │
│   │  │   @traceable spans · token counts · latency metrics     │    │  │
│   │  └─────────────────────────────────────────────────────────┘    │  │
│   │                                                                  │  │
│   └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │         Response JSON: {                                       │   │
│  │           filename, doc_type, sub_type, method,               │   │
│  │           latency_ms, tokens_used, confidence_score            │   │
│  │         }                                                       │   │
│  └──────────────────────────────────────────────────────────────┬──┘   │
└──────────────────────────────────────────────────────────────────┼──────┘
                                                                    │
                                                                    ▼
                                                    ┌──────────────────────┐
                                                    │   Frontend UI        │
                                                    │ Results table with   │
                                                    │ color-coded badges   │
                                                    └──────────────────────┘
```

---

## 🔄 Three-Stage Classification Pipeline

### Stage 1: Rules Engine (src/rules_engine.py)

**Trigger:** Filename analysis  
**Method:** Regex pattern matching  
**Cost:** $0  
**Speed:** <1ms  
**Success Rate:** ~70% of documents

```python
def rules_engine(filename: str, image_data: bytes) -> Optional[Dict]:
    """
    Match documents by filename patterns.
    Fast, zero-cost, high-precision.
    """
    # Example patterns
    if filename.startswith("bill_"):
        return {
            "doc_type": "bill",
            "method": "rules",
            "confidence": 1.0,
            "latency_ms": 0.5
        }
    return None
```

**Patterns matched:**
- `bill_*` → doc_type = "bill"
- `invoice_*` → doc_type = "invoice"
- `receipt_*` → doc_type = "receipt"

**When to use:** Fast, immediate classification when metadata is reliable.

---

### Stage 2: KYC OCR Detection (src/kyc_detector.py)

**Trigger:** Documents unmatched at Stage 1  
**Method:** easyOCR text extraction + keyword matching  
**Cost:** ~$0.001 per document  
**Speed:** 1-2 seconds  
**Success Rate:** ~20% of remaining documents (~6% of total)

```python
def kyc_detector(image_data: bytes) -> Optional[Dict]:
    """
    Detect KYC documents (Aadhaar, PAN, Passport) via OCR.
    Medium speed, cheap, reliable for document types.
    """
    # Use easyOCR to extract text
    ocr_text = easyocr.recognize(image_data)
    
    # Match against KYC keywords
    kyc_keywords = ["aadhaar", "pan", "passport", "voter id", "driving license"]
    
    if any(keyword in ocr_text.lower() for keyword in kyc_keywords):
        return {
            "doc_type": "kyc",
            "sub_type": detect_kyc_subtype(ocr_text),
            "method": "ocr",
            "confidence": 0.95,
            "latency_ms": 1500
        }
    return None
```

**Document types detected:**
- Aadhaar → sub_type = "aadhaar"
- PAN → sub_type = "pan"
- Passport → sub_type = "passport"
- Voter ID → sub_type = "voter_id"
- Driving License → sub_type = "driving_license"

**When to use:** When OCR is fast enough and keyword matching is reliable.

---

### Stage 3: Gemini LLM Classification (src/llm_classifier.py)

**Trigger:** All documents unmatched at Stages 1 & 2  
**Method:** Gemini API (gemma-4-31b-it)  
**Cost:** ~$0.01 per document  
**Speed:** 2-4 seconds  
**Success Rate:** ~10% of documents (only complex cases)

```python
def llm_classifier(image_data: bytes, ocr_text: str) -> Dict:
    """
    Full AI classification for complex/ambiguous documents.
    Slow, expensive, but handles edge cases.
    """
    prompt = f"""
    Classify this insurance document.
    
    OCR extracted text (may be partial/noisy):
    {ocr_text}
    
    Image provided for visual analysis.
    
    Respond with JSON:
    {{
      "doc_type": "image|letter|form|other",
      "sub_type": "prescription|lab_report|claim_form|...",
      "confidence": 0.0-1.0,
      "reasoning": "brief explanation"
    }}
    """
    
    response = gemini_api.generate(
        image=image_data,
        text=prompt
    )
    
    return {
        "doc_type": response.doc_type,
        "sub_type": response.sub_type,
        "method": "llm",
        "confidence": response.confidence,
        "latency_ms": elapsed_time,
        "tokens_used": response.usage.total_tokens
    }
```

**Document types classified:**
- Prescriptions
- Lab reports
- Claim forms
- Medical letters
- X-ray reports
- Test certificates
- Insurance documents (various)

**When to use:** Complex, ambiguous cases where Rules + OCR aren't sufficient.

---

## ⚡ Async Concurrency Architecture

### Request Flow

```
FastAPI Handler (src/api.py)
    │
    ├─ Read multipart form data
    ├─ Extract file list: [file1.pdf, file2.pdf, ...]
    │
    ▼
asyncio.gather([
    executor.submit(classify_document, file1),
    executor.submit(classify_document, file2),
    ...
])
    │
    └─ Runs all files in PARALLEL thread pool
       Each file: Stage1 → Stage2 → Stage3 (cascading, any can short-circuit)
    │
    ▼
Collect results, emit LangSmith traces
    │
    ▼
Return JSON response
```

### Performance Characteristics

**Scenario A: All Stage 1 matches (bills with bill_ prefix)**
- Input: 10 bills
- Processing: 10 × <1ms = ~10ms total
- Response time: ~100ms (overhead)

**Scenario B: Mixed (70% rules, 20% OCR, 10% LLM)**
- Input: 100 documents
- Stage 1: 70 docs × <1ms = ~0.07s
- Stage 2: 20 docs × 1.5s = ~30s parallel (1 thread per doc)
- Stage 3: 10 docs × 3s = ~30s parallel (1 thread per doc)
- **Total: ~30s** (OCR & LLM run in parallel, limited by slowest)

**Optimization:** With N worker threads and M documents:
- If M ≤ N: perfect parallelism, time ≈ max(latencies)
- If M > N: queued, time ≈ sum(latencies) / N

---

## 📊 Monitoring & Observability

### LangSmith Tracing (@traceable decorator)

Each stage emits structured spans to LangSmith:

```python
from langsmith import traceable

@traceable(name="rules_engine")
def rules_engine(filename: str):
    # Automatic tracing:
    # - Execution time
    # - Input/output
    # - Errors
    pass

@traceable(name="kyc_ocr")
def kyc_detector(image_data: bytes):
    # Token usage tracked automatically
    # Latency metrics collected
    pass

@traceable(name="gemini_llm")
def llm_classifier(image_data: bytes):
    # Detailed LLM call tracing
    # Token usage: input + output
    # Model name, parameters, latency
    pass
```

### Metrics Collected

**Per-request metrics:**
- Request ID
- Number of documents
- Document types (histogram)
- Total latency (ms)
- Breakdown by stage
- Token usage (for LLM stage)
- Classification confidence scores

**Real-time dashboards:**
- Azure Monitor: logs, alerts, performance
- LangSmith: traces, token usage, latency percentiles

---

## 🚀 Deployment Architecture

### Azure Container Apps Stack

```
┌─────────────────────────────────────────┐
│  Azure Container Apps (ACA)             │
│  - 0.5 vCPU, 2GB RAM per replica        │
│  - Min 1 replica, Max 3 (auto-scale)    │
│  - HTTPS endpoint                       │
│  - Auto-scaling on CPU/memory           │
└────────────────┬──────────────────────────┘
                 │
    ┌────────────┼────────────┐
    │            │            │
    ▼            ▼            ▼
┌────────┐  ┌────────┐  ┌────────┐
│Replica1│  │Replica2│  │Replica3│
│(running)  │(standby)  │(standby)
└────────┘  └────────┘  └────────┘
    │
    └─────────────────┬─────────────────┐
                      │                 │
    ┌─────────────────▼──────┐  ┌────────▼──────┐
    │  Azure Monitor         │  │  LangSmith    │
    │  - Logs                │  │  - Traces     │
    │  - Performance         │  │  - Token usage│
    │  - Alerts              │  │  - Latency    │
    └────────────────────────┘  └───────────────┘
```

### Container Image

**Dockerfile:**
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy source
COPY src/ ./src/
COPY frontend/ ./frontend/

# Expose port
EXPOSE 8000

# Run with uvicorn
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Image stored in:** Azure Container Registry (medishieldacr.azurecr.io)

---

## 🔒 Security Architecture

### API Security

- **HTTPS only** via Azure Container Apps
- **CORS:** Configured for frontend origin
- **File validation:** Size limits, MIME type checks
- **Input sanitization:** Filename validation, size bounds

### Data Privacy

- **No persistent storage:** Processed files deleted after classification
- **Transient memory:** Results live only in response
- **Encrypted in transit:** TLS 1.2+
- **Audit logs:** All classifications logged to Azure Monitor

### Secrets Management

- **Environment variables** via Azure Container Apps secrets
- **Gemini API key:** Never in code, via env
- **LangSmith key:** Via env, read-only service key

---

## 📈 Scalability Analysis

### Current Setup

- **Max throughput:** ~1000 documents/hour (with 1 replica, max 3s per doc)
- **Bottleneck:** Gemini API rate limits (~100 requests/minute)
  - With 10% of docs hitting Gemini → ~100 docs/min × 10 = 1000 docs/min
  - Actual: limited by API quotas

### Scaling Options

1. **Increase replicas:** Auto-scaling to 3 replicas → 3x throughput
2. **Batch processing:** Collect documents, process asynchronously → decoupled throughput
3. **Queue-based:** Azure Service Bus → robust handling of traffic spikes
4. **Cache results:** Store common patterns (frequent filenames) → reduce processing

---

## 🧪 Testing Strategy

### 117 Passing Tests

**Unit tests (70):**
- Stage 1 rules engine (10 test cases)
- Stage 2 OCR patterns (15 test cases)
- Stage 3 LLM prompt formatting (10 test cases)
- Async orchestration (15 test cases)
- Monitoring/tracing (10 test cases)
- Response validation (10 test cases)

**Integration tests (30):**
- End-to-end classification pipeline (10 test cases)
- Multi-file concurrent processing (5 test cases)
- Error handling & retry logic (5 test cases)
- API endpoint validation (5 test cases)
- LangSmith trace verification (5 test cases)

**Performance tests (10):**
- Latency benchmarks (Stage 1, 2, 3)
- Concurrency stress tests
- Memory usage profiling

**Edge cases (7):**
- Empty files
- Corrupt images
- Unicode filenames
- Very large files
- Timeout handling

---

## 📊 Cost Model

### Per-Document Costs

| Stage | Cost | Trigger | Frequency |
|-------|------|---------|-----------|
| Stage 1 (Rules) | $0.00 | Filename pattern | 70% |
| Stage 2 (OCR) | ~$0.001 | easyOCR library | 20% |
| Stage 3 (LLM) | ~$0.01 | Gemini API call | 10% |

**Expected cost per document:** (0.7 × $0) + (0.2 × $0.001) + (0.1 × $0.01) = **$0.0013**

**Annual cost (1M documents):** 1,000,000 × $0.0013 = **$1,300** (AI costs only)

**Infrastructure:** Azure Container Apps ~$50-100/month (compute + storage)

**Total monthly:** ~$200 (AI + compute + monitoring)

### vs. Manual Labor

- **Manual operator:** ~$3,000/month salary
- **12 operators:** $36,000/month
- **2 remaining operators:** $6,000/month
- **Savings:** ~$30,000/month

**ROI:** Pays for itself in <1 week of savings.

---

## 🔄 Continuous Improvement

### Metrics to Monitor

1. **Accuracy by stage:** Track Stage 3 confidence scores
2. **False negatives:** Documents incorrectly classified at Stage 1 or 2
3. **Latency trends:** Identify performance regressions
4. **Token usage:** Monitor Gemini API efficiency
5. **Cost per document:** Optimize stage cascade

### Feedback Loop

```
Production metrics → Identify misclassifications
    ↓
Add new rules → Retrain Stage 1/2
    ↓
Deploy → Test in staging
    ↓
Compare accuracy vs production
    ↓
If better: deploy; else: revert
```

---

## 📚 Related Documentation

- [WORKFLOW_DIAGRAM.md](./WORKFLOW_DIAGRAM.md) — Mermaid diagrams
- [DIAGRAMS.md](./DIAGRAMS.md) — Interactive Excalidraw diagrams
- [README.md](./README.md) — Project overview
- [src/api.py](./src/api.py) — API implementation
- [src/classifier.py](./src/classifier.py) — Pipeline orchestration

---

Generated: April 26, 2026  
Document version: 2.0 (architecture diagrams added)

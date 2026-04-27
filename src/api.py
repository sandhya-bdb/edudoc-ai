import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
from functools import partial

import easyocr
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google import genai
import os
from dotenv import load_dotenv

from src.classifier import classify

load_dotenv()

ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}

# ── metrics store (in-memory, reset on restart) ───────────────────────────────
_metrics: dict = {
    "total_requests": 0,
    "total_documents": 0,
    "total_input_tokens": 0,
    "total_output_tokens": 0,
    "by_method": {"rules": 0, "ocr": 0, "llm": 0},
    "by_doc_type": {"bill": 0, "kyc": 0, "image": 0},
}

# ── shared ML resources (loaded once at startup) ──────────────────────────────
_ocr_reader: easyocr.Reader | None = None
_llm_client: genai.Client | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ocr_reader, _llm_client
    _ocr_reader = easyocr.Reader(["en"], gpu=False)
    _llm_client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    yield
    # cleanup (nothing needed for these clients)


app = FastAPI(
    title="MediShield Document Classifier",
    description="Classifies scanned insurance documents using rules, OCR, and Gemini LLM.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return _metrics


@app.post("/classify")
async def classify_documents(files: list[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=422, detail="At least one file is required.")

    for f in files:
        if f.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported file type '{f.content_type}' for '{f.filename}'. "
                       f"Accepted: {', '.join(ALLOWED_MIME_TYPES)}",
            )

    _metrics["total_requests"] += 1
    _metrics["total_documents"] += len(files)

    # Read all file bytes concurrently first
    contents = await asyncio.gather(*[f.read() for f in files])

    loop = asyncio.get_running_loop()

    async def _classify_one(filename: str, image_bytes: bytes):
        # Run synchronous classify() in a thread so bill_ files don't wait
        # behind slow OCR/LLM calls from other concurrent requests
        fn = partial(
            classify,
            filename=filename,
            image_bytes=image_bytes,
            ocr_reader=_ocr_reader,
            llm_client=_llm_client,
        )
        return await loop.run_in_executor(None, fn)

    classifications = await asyncio.gather(*[
        _classify_one(f.filename or "unknown.png", data)
        for f, data in zip(files, contents)
    ])

    results = []
    for result in classifications:
        _metrics["total_input_tokens"] += result.input_tokens
        _metrics["total_output_tokens"] += result.output_tokens
        _metrics["by_method"][result.method] = _metrics["by_method"].get(result.method, 0) + 1
        _metrics["by_doc_type"][result.doc_type] = _metrics["by_doc_type"].get(result.doc_type, 0) + 1
        results.append(asdict(result))

    return JSONResponse(content=results)

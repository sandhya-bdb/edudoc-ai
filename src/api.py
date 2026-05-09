import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
from functools import partial
import gc

import easyocr
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
import json
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from google import genai
import os
from dotenv import load_dotenv

from src.classifier import classify

load_dotenv()

# Workaround for macOS SSL certificate verification failures
import ssl
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}

# Cap how many documents are classified concurrently per request.
# For MacBook Air / 4 GiB systems, 1-2 is recommended to prevent OOM/freezing.
MAX_CONCURRENT_CLASSIFICATIONS = int(os.environ.get("CLASSIFY_CONCURRENCY", "1"))

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
    # Models are now lazy-loaded inside the classification loop to save startup memory
    yield
    # cleanup
    global _ocr_reader, _llm_client
    _ocr_reader = None
    _llm_client = None
    gc.collect()


app = FastAPI(
    title="Educational Document Classifier API",
    description="Classifies educational documents using OCR and LLMs.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.is_dir():
    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


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

    global _ocr_reader, _llm_client
    # Initialize models sequentially before spawning concurrent tasks to avoid race conditions
    if _ocr_reader is None:
        _ocr_reader = easyocr.Reader(["en"], gpu=False)
    if _llm_client is None:
        _llm_client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

    loop = asyncio.get_running_loop()
    sem = asyncio.Semaphore(MAX_CONCURRENT_CLASSIFICATIONS)

    async def _classify_one(filename: str, image_bytes: bytes):
        # Semaphore caps in-flight classifications so a 50-doc upload doesn't OOM
        # the worker. Excess docs queue here until a slot frees up.
        async with sem:
            fn = partial(
                classify,
                filename=filename,
                image_bytes=image_bytes,
                ocr_reader=_ocr_reader,
                llm_client=_llm_client,
            )
            return await loop.run_in_executor(None, fn)

    tasks = [
        asyncio.create_task(_classify_one(f.filename or "unknown.png", data))
        for f, data in zip(files, contents)
    ]

    async def stream():
        for coro in asyncio.as_completed(tasks):
            result = await coro
            _metrics["total_input_tokens"] += result.input_tokens
            _metrics["total_output_tokens"] += result.output_tokens
            _metrics["by_method"][result.method] = _metrics["by_method"].get(result.method, 0) + 1
            _metrics["by_doc_type"][result.doc_type] = _metrics["by_doc_type"].get(result.doc_type, 0) + 1
            yield json.dumps(asdict(result)) + "\n"
            
            # Force cleanup after each document to help low-memory systems
            gc.collect()

    return StreamingResponse(stream(), media_type="application/x-ndjson")

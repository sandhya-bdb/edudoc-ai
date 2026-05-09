import time
from dataclasses import dataclass, field
from pathlib import Path

import easyocr
from google import genai

from src.edu_detector import detect_edu
from src.llm_classifier import classify_with_llm
from src.monitoring import trace_classify, trace_edu_ocr, trace_llm_classify, trace_rules_engine
from src.rules_engine import apply_rules


_SUB_TYPE_DEFAULTS = {"transcript": "Transcripts", "certificate": "Certificates", "education": "Education Docs"}


def _default_sub_type(doc_type: str) -> str | None:
    return _SUB_TYPE_DEFAULTS.get(doc_type)


@dataclass
class ClassificationResult:
    filename: str
    doc_type: str           # "transcript" | "certificate" | "education" | "image"
    sub_type: str | None    # Gemini category for "image" docs, else None
    method: str             # "rules" | "ocr" | "llm"
    latency_ms: int
    input_tokens: int = 0
    output_tokens: int = 0


def classify(
    filename: str,
    image_bytes: bytes,
    ocr_reader: easyocr.Reader | None = None,
    llm_client: genai.Client | None = None,
) -> ClassificationResult:
    """Run a single image through the full classification pipeline."""
    start = time.monotonic()
    print(f"\nProcessing: {filename}")

    # Stage 1 — rules engine (filename-based, no ML)
    rules_result = apply_rules(filename)
    print(f"[RULES] type={rules_result.doc_type}, send_to_llm={rules_result.send_to_llm}")
    trace_rules_engine(
        filename=filename,
        doc_type=rules_result.doc_type,
        send_to_llm=rules_result.send_to_llm,
    )
    if not rules_result.send_to_llm:
        result = ClassificationResult(
            filename=filename,
            doc_type=rules_result.doc_type,
            sub_type=_default_sub_type(rules_result.doc_type),
            method="rules",
            latency_ms=int((time.monotonic() - start) * 1000),
        )
        trace_classify(**result.__dict__)
        return result

    # Stage 2 — EDU OCR detector
    edu_result = detect_edu(filename, image_bytes, reader=ocr_reader)
    print(f"[OCR] type={edu_result.doc_type}, send_to_llm={edu_result.send_to_llm}")
    trace_edu_ocr(
        filename=filename,
        doc_type=edu_result.doc_type,
        send_to_llm=edu_result.send_to_llm,
        ocr_text=edu_result.ocr_text,
    )
    if not edu_result.send_to_llm:
        result = ClassificationResult(
            filename=filename,
            doc_type=edu_result.doc_type,
            sub_type=_default_sub_type(edu_result.doc_type),
            method="ocr",
            latency_ms=int((time.monotonic() - start) * 1000),
        )
        trace_classify(**result.__dict__)
        return result

    # Stage 3 — Gemini LLM classifier
    # Stage 3 — Gemini LLM classifier
    try:
        llm_result = classify_with_llm(
            filename,
            image_bytes,
            client=llm_client,
        )
        print(f"[LLM] success -> {llm_result.sub_type}")
        trace_llm_classify(
            filename=filename,
            sub_type=llm_result.sub_type,
            input_tokens=llm_result.input_tokens,
            output_tokens=llm_result.output_tokens,
            raw_response=llm_result.raw_response,
        )

        result = ClassificationResult(
            filename=filename,
            doc_type=llm_result.doc_type,
            sub_type=llm_result.sub_type,
            method="llm",
            latency_ms=int((time.monotonic() - start) * 1000),
            input_tokens=llm_result.input_tokens,
            output_tokens=llm_result.output_tokens,
        )

    except Exception as e:
        result = ClassificationResult(
            filename=filename,
            doc_type="image",
            sub_type="Manual review required",
            method="llm",
            latency_ms=int((time.monotonic() - start) * 1000),
        )
        print(f"[LLM ERROR] {filename}: {e}")
    trace_classify(**result.__dict__)
    print(
    f"[DONE] {filename} | "
    f"type={result.doc_type} | "
    f"sub_type={result.sub_type} | "
    f"method={result.method} | "
    f"latency={result.latency_ms}ms"
)
    return result


def classify_dataset(
    dataset_dir: str | Path = "dataset",
    ocr_reader: easyocr.Reader | None = None,
    llm_client: genai.Client | None = None,
) -> list[ClassificationResult]:
    """Classify all PNG/JPEG images in a directory."""
    dataset_path = Path(dataset_dir)
    results = []

    for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        for image_path in sorted(dataset_path.glob(ext)):
            image_bytes = image_path.read_bytes()
            result = classify(
                filename=image_path.name,
                image_bytes=image_bytes,
                ocr_reader=ocr_reader,
                llm_client=llm_client,
            )
            results.append(result)

    return results

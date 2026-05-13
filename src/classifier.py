import time
from dataclasses import dataclass
from pathlib import Path

import easyocr
from google import genai

from src.edu_detector import detect_edu
from src.llm_classifier import classify_with_llm
from src.monitoring import record_token_usage
from src.rules_engine import apply_rules
from langsmith import traceable


_SUB_TYPE_DEFAULTS = {
    "transcript": "Transcripts",
    "certificate": "Certificates",
    "education": "Education Docs",
}


def _default_sub_type(doc_type: str) -> str | None:
    return _SUB_TYPE_DEFAULTS.get(doc_type)


@dataclass
class ClassificationResult:
    filename: str
    doc_type: str
    sub_type: str | None
    method: str
    latency_ms: int
    input_tokens: int = 0
    output_tokens: int = 0


@traceable(name="classify-document", run_type="chain", tags=["pipeline"])
def classify(
    filename: str,
    image_bytes: bytes,
    ocr_reader: easyocr.Reader | None = None,
    llm_client: genai.Client | None = None,
) -> ClassificationResult:
    """
    Run a single image through the full 3-stage classification pipeline.
    """

    start = time.monotonic()

    print("\n" + "=" * 60)
    print(f"PROCESSING: {filename}")

    

    rules_result = apply_rules(filename)

    print(
        f"[RULES] "
        f"type={rules_result.doc_type} | "
        f"send_to_llm={rules_result.send_to_llm}"
    )

    # Manual trace removed - now handled by @traceable in apply_rules

    if not rules_result.send_to_llm:
        result = ClassificationResult(
            filename=filename,
            doc_type=rules_result.doc_type,
            sub_type=_default_sub_type(rules_result.doc_type),
            method="rules",
            latency_ms=int((time.monotonic() - start) * 1000),
        )

        # Manual trace removed - now handled by top-level @traceable on classify()

        print(
            f"[DONE] "
            f"type={result.doc_type} | "
            f"sub_type={result.sub_type} | "
            f"method={result.method}"
        )

        return result



    edu_result = detect_edu(
        filename,
        image_bytes,
        reader=ocr_reader,
    )

    print(
        f"[OCR] "
        f"type={edu_result.doc_type} | "
        f"send_to_llm={edu_result.send_to_llm}"
    )

    # Manual trace removed - now handled by @traceable in detect_edu

    if not edu_result.send_to_llm:
        result = ClassificationResult(
            filename=filename,
            doc_type=edu_result.doc_type,
            sub_type=_default_sub_type(edu_result.doc_type),
            method="ocr",
            latency_ms=int((time.monotonic() - start) * 1000),
        )

        # Manual trace removed - now handled by top-level @traceable on classify()

        print(
            f"[DONE] "
            f"type={result.doc_type} | "
            f"sub_type={result.sub_type} | "
            f"method={result.method}"
        )

        return result

 
    try:
        llm_result = classify_with_llm(
            filename,
            image_bytes,
            client=llm_client,
        )

        print(f"[LLM] success -> {llm_result.sub_type}")

        # Manual trace removed - now handled by @traceable in classify_with_llm

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
        print(f"[LLM ERROR] {filename}: {e}")

        result = ClassificationResult(
            filename=filename,
            doc_type="image",
            sub_type="Unknown",
            method="llm",
            latency_ms=int((time.monotonic() - start) * 1000),
        )

    # Manual trace removed - now handled by top-level @traceable on classify()

    print(
        f"[DONE] "
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
    """
    Classify all PNG/JPEG/WebP images in a directory.
    """

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
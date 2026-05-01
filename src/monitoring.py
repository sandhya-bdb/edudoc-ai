"""
LangSmith observability for the EduDoc AI classification pipeline.

Each pipeline stage is wrapped with @traceable so LangSmith records:
  - inputs / outputs per stage
  - latency per stage
  - token usage for LLM calls
  - parent/child span relationships (rules → ocr → llm under classify)

Required env vars:
  LANGCHAIN_TRACING_V2=true
  LANGCHAIN_API_KEY=<your-langsmith-key>
  LANGCHAIN_PROJECT=edudoc-ai-classification
"""

import logging
import time
from typing import Any

from langsmith import traceable

logger = logging.getLogger(__name__)


@traceable(name="rules-engine", run_type="tool", tags=["stage:rules"])
def trace_rules_engine(filename: str, doc_type: str | None, send_to_llm: bool) -> dict:
    """Record the rules engine decision in LangSmith."""
    return {
        "filename": filename,
        "doc_type": doc_type,
        "send_to_llm": send_to_llm,
        "stage": "rules",
    }


@traceable(name="edu-ocr", run_type="tool", tags=["stage:ocr"])
def trace_edu_ocr(filename: str, doc_type: str | None, send_to_llm: bool, ocr_text: str) -> dict:
    """Record the EDU OCR decision in LangSmith."""
    return {
        "filename": filename,
        "doc_type": doc_type,
        "send_to_llm": send_to_llm,
        "ocr_text_length": len(ocr_text),
        "stage": "ocr",
    }


@traceable(name="llm-classify", run_type="llm", tags=["stage:llm"])
def trace_llm_classify(
    filename: str,
    sub_type: str,
    input_tokens: int,
    output_tokens: int,
    raw_response: str,
) -> dict:
    """Record the LLM classification result and token usage in LangSmith."""
    return {
        "filename": filename,
        "sub_type": sub_type,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
        "raw_response": raw_response,
        "stage": "llm",
    }


@traceable(name="classify-document", run_type="chain", tags=["pipeline"])
def trace_classify(
    filename: str,
    doc_type: str,
    sub_type: str | None,
    method: str,
    latency_ms: int,
    input_tokens: int,
    output_tokens: int,
) -> dict:
    """Top-level trace for a single document classification run."""
    result = {
        "filename": filename,
        "doc_type": doc_type,
        "sub_type": sub_type,
        "method": method,
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    logger.info(
        "classified",
        extra={
            "filename": filename,
            "doc_type": doc_type,
            "sub_type": sub_type,
            "method": method,
            "latency_ms": latency_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        },
    )
    return result


def record_token_usage(response_usage_metadata: Any) -> dict[str, int]:
    """Extract token counts from a Gemini usage_metadata object."""
    if response_usage_metadata is None:
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    input_t  = getattr(response_usage_metadata, "prompt_token_count", 0) or 0
    output_t = getattr(response_usage_metadata, "candidates_token_count", 0) or 0
    return {
        "input_tokens": input_t,
        "output_tokens": output_t,
        "total_tokens": input_t + output_t,
    }

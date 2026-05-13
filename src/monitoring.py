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


# Redundant functions removed. Tracing is now handled directly via @traceable decorators in worker modules.


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

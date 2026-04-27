from unittest.mock import MagicMock, patch, call
import pytest

from src.monitoring import (
    trace_rules_engine,
    trace_kyc_ocr,
    trace_llm_classify,
    trace_classify,
    record_token_usage,
)


# ── record_token_usage ────────────────────────────────────────────────────────

def test_record_token_usage_extracts_counts():
    usage = MagicMock()
    usage.prompt_token_count = 42
    usage.candidates_token_count = 7
    result = record_token_usage(usage)
    assert result["input_tokens"] == 42
    assert result["output_tokens"] == 7
    assert result["total_tokens"] == 49


def test_record_token_usage_none_returns_zeros():
    result = record_token_usage(None)
    assert result == {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def test_record_token_usage_missing_attrs_defaults_to_zero():
    usage = MagicMock(spec=[])   # no attributes
    result = record_token_usage(usage)
    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 0


# ── trace functions return correct structure ──────────────────────────────────

def test_trace_rules_engine_returns_dict():
    result = trace_rules_engine(
        filename="bill_x.png", doc_type="bill", send_to_llm=False
    )
    assert result["filename"] == "bill_x.png"
    assert result["doc_type"] == "bill"
    assert result["send_to_llm"] is False
    assert result["stage"] == "rules"


def test_trace_kyc_ocr_returns_dict():
    result = trace_kyc_ocr(
        filename="doc.png", doc_type="kyc",
        send_to_llm=False, ocr_text="AADHAAR card"
    )
    assert result["filename"] == "doc.png"
    assert result["doc_type"] == "kyc"
    assert result["ocr_text_length"] == len("AADHAAR card")
    assert result["stage"] == "ocr"


def test_trace_kyc_ocr_does_not_leak_raw_ocr_text():
    result = trace_kyc_ocr(
        filename="doc.png", doc_type="kyc",
        send_to_llm=False, ocr_text="sensitive PAN data"
    )
    assert "ocr_text" not in result   # length only, not the full text


def test_trace_llm_classify_returns_dict_with_token_usage():
    result = trace_llm_classify(
        filename="doc.png",
        sub_type="Medical Reports",
        input_tokens=55,
        output_tokens=7,
        raw_response="Medical Reports",
    )
    assert result["sub_type"] == "Medical Reports"
    assert result["usage"]["input_tokens"] == 55
    assert result["usage"]["output_tokens"] == 7
    assert result["usage"]["total_tokens"] == 62
    assert result["stage"] == "llm"


def test_trace_classify_returns_full_result():
    result = trace_classify(
        filename="bill_x.png",
        doc_type="bill",
        sub_type=None,
        method="rules",
        latency_ms=2,
        input_tokens=0,
        output_tokens=0,
    )
    assert result["doc_type"] == "bill"
    assert result["method"] == "rules"
    assert result["latency_ms"] == 2


# ── @traceable decorators applied — verified by calling and checking output ───

def test_trace_functions_are_callable_without_langsmith_configured():
    """Tracing should not raise even when LANGCHAIN_TRACING_V2 is not set."""
    with patch.dict("os.environ", {}, clear=False):
        r = trace_rules_engine(filename="test.png", doc_type=None, send_to_llm=True)
        assert r["send_to_llm"] is True


# ── classifier pipeline emits traces ─────────────────────────────────────────

def test_classifier_calls_trace_rules_engine_for_bill_file():
    with patch("src.classifier.trace_rules_engine") as mock_trace:
        from src.classifier import classify
        classify("bill_innovh_01.png", b"bytes")
    mock_trace.assert_called_once()
    _, kwargs = mock_trace.call_args
    assert kwargs["doc_type"] == "bill"


def test_classifier_calls_trace_classify_for_bill_file():
    with patch("src.classifier.trace_classify") as mock_trace:
        from src.classifier import classify
        classify("bill_innovh_01.png", b"bytes")
    mock_trace.assert_called_once()
    _, kwargs = mock_trace.call_args
    assert kwargs["method"] == "rules"


def test_classifier_calls_trace_kyc_ocr_for_kyc_doc():
    mock_reader = MagicMock()
    mock_reader.readtext.return_value = ["AADHAAR", "UIDAI"]

    with patch("src.classifier.trace_kyc_ocr") as mock_trace, \
         patch("src.classifier.trace_classify"):
        from src.classifier import classify
        classify("doc.png", b"bytes", ocr_reader=mock_reader)

    mock_trace.assert_called_once()
    _, kwargs = mock_trace.call_args
    assert kwargs["doc_type"] == "kyc"


def test_classifier_calls_trace_llm_classify_for_llm_doc():
    mock_reader = MagicMock()
    mock_reader.readtext.return_value = ["Hospital", "Bill"]

    usage = MagicMock()
    usage.prompt_token_count = 10
    usage.candidates_token_count = 3
    response = MagicMock()
    response.text = "Medical Reports"
    response.usage_metadata = usage
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = response

    with patch("src.classifier.trace_llm_classify") as mock_trace, \
         patch("src.classifier.trace_classify"):
        from src.classifier import classify
        classify("doc.png", b"bytes", ocr_reader=mock_reader, llm_client=mock_client)

    mock_trace.assert_called_once()
    _, kwargs = mock_trace.call_args
    assert kwargs["sub_type"] == "Medical Reports"
    assert kwargs["input_tokens"] == 10

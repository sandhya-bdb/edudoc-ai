from src.monitoring import (
    record_token_usage,
    trace_classify,
    trace_edu_ocr,
    trace_llm_classify,
    trace_rules_engine,
)


def test_trace_rules_engine():
    result = trace_rules_engine("transcript_01.png", "transcript", False)
    assert result["filename"] == "transcript_01.png"
    assert result["doc_type"] == "transcript"
    assert result["send_to_llm"] is False
    assert result["stage"] == "rules"


def test_trace_edu_ocr():
    result = trace_edu_ocr("random.png", "education", False, "University transcript here")
    assert result["filename"] == "random.png"
    assert result["doc_type"] == "education"
    assert result["send_to_llm"] is False
    assert result["ocr_text_length"] > 10
    assert result["stage"] == "ocr"


def test_trace_llm_classify():
    result = trace_llm_classify("doc.png", "Transcripts", 100, 20, "raw text")
    assert result["filename"] == "doc.png"
    assert result["sub_type"] == "Transcripts"
    assert result["usage"]["input_tokens"] == 100
    assert result["usage"]["output_tokens"] == 20
    assert result["usage"]["total_tokens"] == 120
    assert result["stage"] == "llm"


def test_trace_classify():
    result = trace_classify("doc.png", "image", "Transcripts", "llm", 1500, 100, 20)
    assert result["filename"] == "doc.png"
    assert result["method"] == "llm"
    assert result["latency_ms"] == 1500


def test_record_token_usage_none():
    assert record_token_usage(None) == {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


class DummyUsage:
    def __init__(self, p, c):
        self.prompt_token_count = p
        self.candidates_token_count = c


def test_record_token_usage_valid():
    usage = DummyUsage(100, 50)
    result = record_token_usage(usage)
    assert result == {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}

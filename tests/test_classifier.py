from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from src.classifier import classify, classify_dataset
from src.kyc_detector import KYCResult
from src.llm_classifier import LLMResult


# ── helpers ──────────────────────────────────────────────────────────────────

def _kyc_reader(is_kyc: bool, filename: str = "test.png") -> MagicMock:
    """Mock easyocr reader that simulates KYC or non-KYC OCR output."""
    reader = MagicMock()
    reader.readtext.return_value = ["AADHAAR", "UIDAI"] if is_kyc else ["Hospital", "Bill"]
    return reader


def _llm_client(sub_type: str = "Medical Reports") -> MagicMock:
    """Mock Gemini client returning the given sub_type."""
    usage = MagicMock()
    usage.prompt_token_count = 10
    usage.candidates_token_count = 3

    response = MagicMock()
    response.text = sub_type
    response.usage_metadata = usage

    client = MagicMock()
    client.models.generate_content.return_value = response
    return client


FAKE_BYTES = b"fake-image-bytes"


# ── Stage 1: rules engine short-circuits ─────────────────────────────────────

def test_bill_file_classified_by_rules():
    result = classify("bill_innovh_01.png", FAKE_BYTES)
    assert result.doc_type == "bill"
    assert result.method == "rules"
    assert result.sub_type is None


def test_bill_file_never_calls_ocr():
    reader = _kyc_reader(False)
    classify("bill_innovh_01.png", FAKE_BYTES, ocr_reader=reader)
    reader.readtext.assert_not_called()


def test_bill_file_never_calls_llm():
    client = _llm_client()
    classify("bill_innovh_01.png", FAKE_BYTES, llm_client=client)
    client.models.generate_content.assert_not_called()


@pytest.mark.parametrize("i", range(1, 11))
def test_all_ten_bill_files_use_rules(i):
    filename = f"bill_innovh_{i:02d}.png"
    result = classify(filename, FAKE_BYTES)
    assert result.doc_type == "bill"
    assert result.method == "rules"


# ── Stage 2: KYC OCR short-circuits ──────────────────────────────────────────

def test_kyc_doc_classified_by_ocr():
    result = classify("03ac1d4117.png", FAKE_BYTES, ocr_reader=_kyc_reader(True))
    assert result.doc_type == "kyc"
    assert result.method == "ocr"
    assert result.sub_type is None


def test_kyc_doc_never_calls_llm():
    client = _llm_client()
    classify("03ac1d4117.png", FAKE_BYTES, ocr_reader=_kyc_reader(True), llm_client=client)
    client.models.generate_content.assert_not_called()


def test_kyc_doc_passes_image_bytes_to_reader():
    reader = _kyc_reader(True)
    classify("03ac1d4117.png", FAKE_BYTES, ocr_reader=reader)
    reader.readtext.assert_called_once_with(FAKE_BYTES, detail=0)


# ── Stage 3: LLM classifier ───────────────────────────────────────────────────

def test_non_kyc_doc_classified_by_llm():
    result = classify(
        "05a5de87a2.png", FAKE_BYTES,
        ocr_reader=_kyc_reader(False),
        llm_client=_llm_client("Medical Reports"),
    )
    assert result.doc_type == "image"
    assert result.method == "llm"
    assert result.sub_type == "Medical Reports"


@pytest.mark.parametrize("sub_type", [
    "Patient Bills", "Claim Forms", "Medical Reports", "Prescriptions", "Unknown"
])
def test_llm_sub_types_passed_through(sub_type):
    result = classify(
        "test.png", FAKE_BYTES,
        ocr_reader=_kyc_reader(False),
        llm_client=_llm_client(sub_type),
    )
    assert result.sub_type == sub_type


def test_token_counts_captured_from_llm():
    usage = MagicMock()
    usage.prompt_token_count = 55
    usage.candidates_token_count = 7
    response = MagicMock()
    response.text = "Prescriptions"
    response.usage_metadata = usage
    client = MagicMock()
    client.models.generate_content.return_value = response

    result = classify("test.png", FAKE_BYTES, ocr_reader=_kyc_reader(False), llm_client=client)
    assert result.input_tokens == 55
    assert result.output_tokens == 7


# ── Result fields ─────────────────────────────────────────────────────────────

def test_latency_ms_is_non_negative():
    result = classify("bill_innovh_01.png", FAKE_BYTES)
    assert result.latency_ms >= 0


def test_filename_preserved_through_pipeline():
    result = classify("bill_innovh_05.png", FAKE_BYTES)
    assert result.filename == "bill_innovh_05.png"


# ── classify_dataset ──────────────────────────────────────────────────────────

def test_classify_dataset_returns_result_per_file(tmp_path):
    for name in ["bill_test_01.png", "doc_a.png", "doc_b.png"]:
        (tmp_path / name).write_bytes(FAKE_BYTES)

    reader = _kyc_reader(False)
    client = _llm_client("Unknown")
    results = classify_dataset(tmp_path, ocr_reader=reader, llm_client=client)

    assert len(results) == 3


def test_classify_dataset_bill_files_use_rules(tmp_path):
    (tmp_path / "bill_x.png").write_bytes(FAKE_BYTES)
    results = classify_dataset(tmp_path)
    assert results[0].doc_type == "bill"
    assert results[0].method == "rules"


def test_classify_dataset_returns_list_of_classification_results(tmp_path):
    from src.classifier import ClassificationResult
    (tmp_path / "bill_only.png").write_bytes(FAKE_BYTES)
    results = classify_dataset(tmp_path)
    assert all(isinstance(r, ClassificationResult) for r in results)


def test_classify_dataset_empty_dir_returns_empty_list(tmp_path):
    results = classify_dataset(tmp_path)
    assert results == []

from unittest.mock import MagicMock, patch
import pytest
from src.kyc_detector import detect_kyc, _is_kyc


# --- _is_kyc unit tests (no OCR needed) ---

@pytest.mark.parametrize("text", [
    "AADHAAR card issued by UIDAI",
    "Government of India PAN card",
    "Govt. of India permanent account number",
    "Date of Birth: 01/01/1990",
    "INCOME TAX DEPARTMENT",
    "PASSPORT No. A1234567",
    "2345 6789 0123",          # 12-digit Aadhaar
    "ABCDE1234F",              # PAN format
])
def test_is_kyc_returns_true_for_kyc_text(text):
    assert _is_kyc(text) is True


@pytest.mark.parametrize("text", [
    "Hospital bill for patient John Doe",
    "Lab report: blood glucose 95 mg/dL",
    "Dr. Smith prescription for amoxicillin",
    "MediShield claim form CF-2024",
    "",
])
def test_is_kyc_returns_false_for_non_kyc_text(text):
    assert _is_kyc(text) is False


# --- detect_kyc with mocked easyocr reader ---

def _mock_reader(ocr_words: list[str]) -> MagicMock:
    reader = MagicMock()
    reader.readtext.return_value = ocr_words
    return reader


def test_aadhaar_text_classified_as_kyc():
    reader = _mock_reader(["AADHAAR", "UIDAI", "Government", "of", "India"])
    result = detect_kyc("03ac1d4117.png", b"fake-image-bytes", reader=reader)
    assert result.doc_type == "kyc"
    assert result.send_to_llm is False


def test_pan_card_text_classified_as_kyc():
    reader = _mock_reader(["INCOME", "TAX", "DEPARTMENT", "ABCDE1234F"])
    result = detect_kyc("a35d0f5a19.png", b"fake-image-bytes", reader=reader)
    assert result.doc_type == "kyc"
    assert result.send_to_llm is False


def test_passport_text_classified_as_kyc():
    reader = _mock_reader(["PASSPORT", "Republic", "of", "India"])
    result = detect_kyc("1943d55a29.png", b"fake-image-bytes", reader=reader)
    assert result.doc_type == "kyc"
    assert result.send_to_llm is False


def test_non_kyc_doc_passes_through():
    reader = _mock_reader(["Hospital", "Bill", "Patient", "John", "Doe"])
    result = detect_kyc("05a5de87a2.png", b"fake-image-bytes", reader=reader)
    assert result.doc_type is None
    assert result.send_to_llm is True


def test_empty_ocr_result_passes_through():
    reader = _mock_reader([])
    result = detect_kyc("99da361705.png", b"fake-image-bytes", reader=reader)
    assert result.doc_type is None
    assert result.send_to_llm is True


def test_ocr_text_preserved_in_result():
    reader = _mock_reader(["AADHAAR", "card"])
    result = detect_kyc("03ac1d4117.png", b"fake-image-bytes", reader=reader)
    assert "AADHAAR" in result.ocr_text
    assert "card" in result.ocr_text


def test_filename_preserved_in_result():
    reader = _mock_reader(["AADHAAR"])
    result = detect_kyc("my_document.png", b"fake-image-bytes", reader=reader)
    assert result.filename == "my_document.png"


def test_reader_receives_image_bytes():
    reader = _mock_reader([])
    image_bytes = b"some-real-image-bytes"
    detect_kyc("test.png", image_bytes, reader=reader)
    reader.readtext.assert_called_once_with(image_bytes, detail=0)

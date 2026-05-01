from unittest.mock import MagicMock

import pytest

from src.edu_detector import detect_edu


@pytest.fixture
def mock_reader():
    reader = MagicMock()
    # By default, return no matching text
    reader.readtext.return_value = ["some", "random", "text"]
    return reader


def test_university_keyword_detected(mock_reader):
    mock_reader.readtext.return_value = ["State", "University", "Transcript"]
    result = detect_edu("doc1.png", b"imagebytes", reader=mock_reader)
    assert result.doc_type == "education"
    assert result.send_to_llm is False


def test_student_id_keyword_detected(mock_reader):
    mock_reader.readtext.return_value = ["Student ID: 12345"]
    result = detect_edu("doc2.png", b"imagebytes", reader=mock_reader)
    assert result.doc_type == "education"
    assert result.send_to_llm is False


def test_no_edu_keywords_passes_to_llm(mock_reader):
    mock_reader.readtext.return_value = ["Grocery", "Receipt", "Total", "5.99"]
    result = detect_edu("doc3.png", b"imagebytes", reader=mock_reader)
    assert result.doc_type is None
    assert result.send_to_llm is True


def test_case_insensitivity(mock_reader):
    mock_reader.readtext.return_value = ["DIPLOMA"]
    result = detect_edu("doc4.png", b"imagebytes", reader=mock_reader)
    assert result.doc_type == "education"
    assert result.send_to_llm is False


def test_preserves_filename(mock_reader):
    result = detect_edu("my_file.png", b"bytes", reader=mock_reader)
    assert result.filename == "my_file.png"

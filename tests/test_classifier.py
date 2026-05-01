import pytest
from unittest.mock import MagicMock, patch

from src.classifier import classify, classify_dataset


@pytest.fixture
def mock_ocr():
    reader = MagicMock()
    reader.readtext.return_value = ["Random text"]
    return reader


@pytest.fixture
def mock_llm():
    client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Transcripts"
    mock_response.usage_metadata.prompt_token_count = 100
    mock_response.usage_metadata.candidates_token_count = 10
    client.models.generate_content.return_value = mock_response
    return client


def test_classify_rules_match(mock_ocr, mock_llm):
    # transcript_ prefix should match stage 1
    result = classify("transcript_123.png", b"bytes", ocr_reader=mock_ocr, llm_client=mock_llm)
    assert result.doc_type == "transcript"
    assert result.method == "rules"
    # OCR and LLM should NOT be called
    mock_ocr.readtext.assert_not_called()
    mock_llm.models.generate_content.assert_not_called()


def test_classify_edu_ocr_match(mock_ocr, mock_llm):
    # Setup OCR to find an edu keyword
    mock_ocr.readtext.return_value = ["University"]
    
    result = classify("unrelated_name.png", b"bytes", ocr_reader=mock_ocr, llm_client=mock_llm)
    assert result.doc_type == "education"
    assert result.method == "ocr"
    # LLM should NOT be called
    mock_llm.models.generate_content.assert_not_called()


def test_classify_llm_fallback(mock_ocr, mock_llm):
    # OCR finds nothing useful
    result = classify("unrelated_name.png", b"bytes", ocr_reader=mock_ocr, llm_client=mock_llm)
    assert result.doc_type == "image"
    assert result.method == "llm"
    assert result.sub_type == "Transcripts"
    # LLM must be called
    mock_llm.models.generate_content.assert_called_once()


@patch("src.classifier.Path")
def test_classify_dataset(mock_path, mock_ocr, mock_llm):
    # Setup mock dir with 2 files
    mock_dir = MagicMock()
    class MockPath:
        def __init__(self, name, bytes_val):
            self.name = name
            self.bytes_val = bytes_val
        def read_bytes(self):
            return self.bytes_val
        def __lt__(self, other):
            return self.name < other.name
            
    mock_file1 = MockPath("transcript_01.png", b"bytes1")
    mock_file2 = MockPath("unknown_02.png", b"bytes2")
    
    # Return both files for the first extension, empty for the rest
    mock_dir.glob.side_effect = [[mock_file1, mock_file2], [], [], []]
    mock_path.return_value = mock_dir
    
    results = classify_dataset("dummy_dir", ocr_reader=mock_ocr, llm_client=mock_llm)
    
    assert len(results) == 2
    assert results[0].method == "rules"
    assert results[1].method == "llm"

from unittest.mock import MagicMock

import pytest
from google.genai import types

from src.llm_classifier import classify_with_llm, _parse_category


def test_parse_category_exact_match():
    assert _parse_category("Transcripts") == "Transcripts"


def test_parse_category_case_insensitive():
    assert _parse_category("transcripts") == "Transcripts"
    assert _parse_category(" CERTIFICATES ") == "Certificates"


def test_parse_category_unknown():
    assert _parse_category("Not a category") == "Unknown"
    assert _parse_category("") == "Unknown"


@pytest.fixture
def mock_client():
    client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Transcripts"
    mock_response.usage_metadata.prompt_token_count = 150
    mock_response.usage_metadata.candidates_token_count = 5
    client.models.generate_content.return_value = mock_response
    return client


def test_classify_with_llm_returns_structured_result(mock_client):
    result = classify_with_llm("test.png", b"bytes", client=mock_client)
    assert result.filename == "test.png"
    assert result.doc_type == "image"
    assert result.sub_type == "Transcripts"
    assert result.method == "llm"
    assert result.input_tokens == 150
    assert result.output_tokens == 5
    assert result.raw_response == "Transcripts"


def test_classify_with_llm_unknown_response(mock_client):
    mock_client.models.generate_content.return_value.text = "I don't know"
    result = classify_with_llm("test2.png", b"bytes", client=mock_client)
    assert result.sub_type == "Unknown"

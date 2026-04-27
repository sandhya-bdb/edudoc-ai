from unittest.mock import MagicMock, patch
import pytest
from src.llm_classifier import classify_with_llm, _parse_category, CATEGORIES, PROMPT, MODEL


# --- _parse_category unit tests ---

@pytest.mark.parametrize("category", CATEGORIES)
def test_parse_category_exact_match(category):
    assert _parse_category(category) == category

@pytest.mark.parametrize("category", CATEGORIES)
def test_parse_category_case_insensitive(category):
    assert _parse_category(category.upper()) == category
    assert _parse_category(category.lower()) == category

def test_parse_category_strips_whitespace():
    assert _parse_category("  Medical Reports  ") == "Medical Reports"

def test_parse_category_unknown_text_returns_unknown():
    assert _parse_category("something random") == "Unknown"

def test_parse_category_empty_string_returns_unknown():
    assert _parse_category("") == "Unknown"


# --- prompt structure ---

def test_prompt_contains_all_categories():
    for category in CATEGORIES:
        assert category in PROMPT

def test_prompt_instructs_single_category():
    assert "one" in PROMPT.lower() or "only" in PROMPT.lower()

def test_model_name_is_correct():
    assert MODEL == "gemma-4-31b-it"


# --- classify_with_llm with mocked Gemini client ---

def _make_mock_client(response_text: str, input_tokens: int = 10, output_tokens: int = 3):
    usage = MagicMock()
    usage.prompt_token_count = input_tokens
    usage.candidates_token_count = output_tokens

    response = MagicMock()
    response.text = response_text
    response.usage_metadata = usage

    client = MagicMock()
    client.models.generate_content.return_value = response
    return client


@pytest.mark.parametrize("category", CATEGORIES)
def test_classify_returns_correct_sub_type(category):
    client = _make_mock_client(category)
    result = classify_with_llm("test.png", b"fake-bytes", client=client)
    assert result.sub_type == category


def test_classify_doc_type_is_always_image():
    client = _make_mock_client("Medical Reports")
    result = classify_with_llm("test.png", b"fake-bytes", client=client)
    assert result.doc_type == "image"


def test_classify_method_is_always_llm():
    client = _make_mock_client("Prescriptions")
    result = classify_with_llm("test.png", b"fake-bytes", client=client)
    assert result.method == "llm"


def test_classify_filename_preserved():
    client = _make_mock_client("Claim Forms")
    result = classify_with_llm("03ac1d4117.png", b"fake-bytes", client=client)
    assert result.filename == "03ac1d4117.png"


def test_classify_token_counts_captured():
    client = _make_mock_client("Medical Reports", input_tokens=42, output_tokens=5)
    result = classify_with_llm("test.png", b"fake-bytes", client=client)
    assert result.input_tokens == 42
    assert result.output_tokens == 5


def test_classify_unrecognised_response_returns_unknown():
    client = _make_mock_client("I cannot determine the document type")
    result = classify_with_llm("test.png", b"fake-bytes", client=client)
    assert result.sub_type == "Unknown"


def test_classify_sends_image_bytes_to_gemini():
    client = _make_mock_client("Patient Bills")
    image_bytes = b"real-image-content"
    classify_with_llm("test.png", image_bytes, mime_type="image/png", client=client)

    call_args = client.models.generate_content.call_args
    assert call_args.kwargs["model"] == MODEL
    contents = call_args.kwargs["contents"]
    # First part must carry the image bytes
    assert contents[0].inline_data.data == image_bytes


def test_classify_sends_prompt_as_second_part():
    client = _make_mock_client("Claim Forms")
    classify_with_llm("test.png", b"bytes", client=client)

    contents = client.models.generate_content.call_args.kwargs["contents"]
    assert contents[1].text == PROMPT


def test_classify_none_usage_metadata_defaults_to_zero():
    response = MagicMock()
    response.text = "Unknown"
    response.usage_metadata = None

    client = MagicMock()
    client.models.generate_content.return_value = response

    result = classify_with_llm("test.png", b"bytes", client=client)
    assert result.input_tokens == 0
    assert result.output_tokens == 0

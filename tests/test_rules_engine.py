import pytest
from src.rules_engine import apply_rules

def test_transcript_file_is_classified_as_transcript():
    result = apply_rules("transcript_01.png")
    assert result.doc_type == "transcript"
    assert result.send_to_llm is False

def test_cert_file_is_classified_as_certificate():
    result = apply_rules("cert_john_doe.png")
    assert result.doc_type == "certificate"
    assert result.send_to_llm is False

def test_all_transcript_sample_files():
    transcript_files = [f"transcript_{i:02d}.png" for i in range(1, 11)]
    for filename in transcript_files:
        result = apply_rules(filename)
        assert result.doc_type == "transcript"
        assert result.send_to_llm is False

def test_non_matching_file_has_no_doc_type():
    result = apply_rules("03ac1d4117.png")
    assert result.doc_type is None
    assert result.send_to_llm is True

def test_random_filename_passes_through():
    result = apply_rules("ZLKMXcsoikn.png")
    assert result.send_to_llm is True

def test_uppercase_prefix_is_not_matched():
    result = apply_rules("TRANSCRIPT_something.png")
    assert result.doc_type is None
    assert result.send_to_llm is True

def test_filename_is_preserved_in_result():
    result = apply_rules("transcript_01.png")
    assert result.filename == "transcript_01.png"

def test_full_path_filename_transcript():
    result = apply_rules("dataset/transcript_01.png")
    assert result.doc_type == "transcript"
    assert result.send_to_llm is False

def test_full_path_filename_non_matching():
    result = apply_rules("dataset/03ac1d4117.png")
    assert result.doc_type is None
    assert result.send_to_llm is True

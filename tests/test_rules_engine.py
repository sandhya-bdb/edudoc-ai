import pytest
from src.rules_engine import apply_rules


# --- bill_ prefix rules ---

def test_bill_file_is_classified_as_bill():
    result = apply_rules("bill_innovh_01.png")
    assert result.doc_type == "bill"

def test_bill_file_is_not_sent_to_llm():
    result = apply_rules("bill_innovh_01.png")
    assert result.send_to_llm is False

def test_all_bill_sample_files():
    bill_files = [f"bill_innovh_{i:02d}.png" for i in range(1, 11)]
    for filename in bill_files:
        result = apply_rules(filename)
        assert result.doc_type == "bill", f"{filename} should be bill"
        assert result.send_to_llm is False, f"{filename} should not go to LLM"

# --- non-bill files pass through ---

def test_non_bill_file_has_no_doc_type():
    result = apply_rules("03ac1d4117.png")
    assert result.doc_type is None

def test_non_bill_file_is_sent_to_llm():
    result = apply_rules("03ac1d4117.png")
    assert result.send_to_llm is True

def test_random_filename_passes_through():
    result = apply_rules("ZLKMXcsoikn.png")
    assert result.send_to_llm is True

# --- case sensitivity ---

def test_uppercase_bill_prefix_is_not_matched():
    result = apply_rules("BILL_something.png")
    assert result.doc_type is None
    assert result.send_to_llm is True

def test_mixed_case_bill_prefix_is_not_matched():
    result = apply_rules("Bill_something.png")
    assert result.doc_type is None
    assert result.send_to_llm is True

# --- filename field preserved ---

def test_filename_is_preserved_in_result():
    result = apply_rules("bill_innovh_01.png")
    assert result.filename == "bill_innovh_01.png"

def test_full_path_filename_bill():
    result = apply_rules("dataset/bill_innovh_01.png")
    assert result.doc_type == "bill"
    assert result.send_to_llm is False

def test_full_path_filename_non_bill():
    result = apply_rules("dataset/03ac1d4117.png")
    assert result.doc_type is None
    assert result.send_to_llm is True

from src.privacy import mask_pii

def test_mask_emails():
    text = "Contact me at john.doe@example.com or support@company.org"
    masked = mask_pii(text)
    assert "john.doe@example.com" not in masked
    assert "support@company.org" not in masked
    assert "[EMAIL_REDACTED]" in masked

def test_mask_phones():
    text = "Call +1-234-567-8900 or (123) 456-7890"
    masked = mask_pii(text)
    assert "1-234-567-8900" not in masked
    assert "123" not in masked
    assert "[PHONE_REDACTED]" in masked

def test_mask_ids():
    text = "My ID is 123456789 and my other ID is 9876543210123456"
    masked = mask_pii(text)
    assert "123456789" not in masked
    assert "9876543210123456" not in masked
    assert "[ID_REDACTED]" in masked

def test_mask_dates():
    text = "Born on 1990-01-01 or 01/01/1990"
    masked = mask_pii(text)
    assert "1990-01-01" not in masked
    assert "01/01/1990" not in masked
    assert "[DATE_REDACTED]" in masked

def test_empty_text():
    assert mask_pii("") == ""
    assert mask_pii(None) == ""

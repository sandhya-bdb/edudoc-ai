import re

# Lightweight PII detection patterns
# ------------------------------------------------------------------------------
# 1. Emails
_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

# 2. Phone Numbers (International and common domestic formats)
# Covers: +1-234-567-8900, (123) 456-7890, 123.456.7890, 1234567890
_PHONE_PATTERN = re.compile(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")

# 3. Numeric IDs (Generic 9-16 digit numbers often used for Student IDs, SSNs, Aadhaar, etc.)
# We only match if they are at least 9 digits to avoid redacting small numbers like zip codes.
_ID_PATTERN = re.compile(r"\b\d{9,16}\b")

# 4. Dates of Birth / Sensitive Dates (Simplified YYYY-MM-DD, DD/MM/YYYY)
_DATE_PATTERN = re.compile(r"\b\d{1,4}[-/]\d{1,2}[-/]\d{1,4}\b")


def mask_pii(text: str) -> str:
    """
    Redact Personally Identifiable Information (PII) from text using 
    lightweight regex patterns.
    """
    if not text:
        return ""

    # Mask Emails
    text = _EMAIL_PATTERN.sub("[EMAIL_REDACTED]", text)
    
    # Mask Phone Numbers
    text = _PHONE_PATTERN.sub("[PHONE_REDACTED]", text)
    
    # Mask Dates
    text = _DATE_PATTERN.sub("[DATE_REDACTED]", text)
    
    # Mask Potential ID Numbers
    text = _ID_PATTERN.sub("[ID_REDACTED]", text)

    return text

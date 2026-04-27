import re
from dataclasses import dataclass

import easyocr

# Lazy-loaded singleton — easyocr model is ~200MB, load once
_reader: easyocr.Reader | None = None

_KYC_PATTERNS = [
    re.compile(r"\baadhaar\b", re.IGNORECASE),
    re.compile(r"\buidai\b", re.IGNORECASE),
    re.compile(r"\bpan\b", re.IGNORECASE),
    re.compile(r"\bpassport\b", re.IGNORECASE),
    re.compile(r"\bgovt\.?\s+of\s+india\b", re.IGNORECASE),
    re.compile(r"\bgovernment\s+of\s+india\b", re.IGNORECASE),
    re.compile(r"\bdate\s+of\s+birth\b", re.IGNORECASE),
    re.compile(r"\bpermanent\s+account\s+number\b", re.IGNORECASE),
    re.compile(r"\bincome\s+tax\b", re.IGNORECASE),
    re.compile(r"\b[2-9]\d{3}\s?\d{4}\s?\d{4}\b"),   # 12-digit Aadhaar pattern
    re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),         # PAN card format
]


@dataclass
class KYCResult:
    filename: str
    doc_type: str | None   # "kyc" or None
    send_to_llm: bool
    ocr_text: str


def _get_reader() -> easyocr.Reader:
    global _reader
    if _reader is None:
        _reader = easyocr.Reader(["en"], gpu=False)
    return _reader


def _is_kyc(text: str) -> bool:
    return any(pattern.search(text) for pattern in _KYC_PATTERNS)


def detect_kyc(filename: str, image_bytes: bytes, reader: easyocr.Reader | None = None) -> KYCResult:
    """Run OCR on image bytes and determine if the document is a KYC document."""
    r = reader if reader is not None else _get_reader()
    results = r.readtext(image_bytes, detail=0)
    full_text = " ".join(results)

    if _is_kyc(full_text):
        return KYCResult(filename=filename, doc_type="kyc", send_to_llm=False, ocr_text=full_text)

    return KYCResult(filename=filename, doc_type=None, send_to_llm=True, ocr_text=full_text)

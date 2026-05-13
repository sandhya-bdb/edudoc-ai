import re
from dataclasses import dataclass

import easyocr

# Lazy-loaded singleton — easyocr model is ~200MB, load once
_reader: easyocr.Reader | None = None

_EDU_PATTERNS = [
    re.compile(r"\buniversity\b", re.IGNORECASE),
    re.compile(r"\bcollege\b", re.IGNORECASE),
    re.compile(r"\bstudent\s+id\b", re.IGNORECASE),
    re.compile(r"\bdegree\b", re.IGNORECASE),
    re.compile(r"\bdiploma\b", re.IGNORECASE),
    re.compile(r"\btranscript\b", re.IGNORECASE),
    re.compile(r"\benrollment\b", re.IGNORECASE),
    re.compile(r"\bacademic\s+record\b", re.IGNORECASE),
    re.compile(r"\bbachelor\b", re.IGNORECASE),
    re.compile(r"\bmaster\b", re.IGNORECASE),
    re.compile(r"\bboard\b", re.IGNORECASE),
    re.compile(r"\bsecondary\b", re.IGNORECASE),
    re.compile(r"\bmarksheet\b", re.IGNORECASE),
    re.compile(r"\bresult\b", re.IGNORECASE),
    re.compile(r"\bcertificate\b", re.IGNORECASE),
]


from PIL import Image
import io

def _preprocess_image(image_bytes: bytes, max_dim: int = 1024) -> bytes:
    """Resize image to speed up OCR while maintaining enough quality for classification."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            # Calculate aspect ratio
            ratio = max_dim / max(img.size)
            if ratio < 1.0:
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                
            # Convert back to bytes
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=85)
            return img_byte_arr.getvalue()
    except Exception:
        # If image is corrupt or not an image (e.g. in tests), return original bytes
        # and let Stage 2/3 handle the failure gracefully.
        return image_bytes


@dataclass
class EduResult:
    filename: str
    doc_type: str | None   # "education" or None
    send_to_llm: bool
    ocr_text: str


def _get_reader() -> easyocr.Reader:
    global _reader
    if _reader is None:
        _reader = easyocr.Reader(["en"], gpu=False)
    return _reader


def _is_edu(text: str) -> bool:
    return any(pattern.search(text) for pattern in _EDU_PATTERNS)


from langsmith import traceable


@traceable(name="edu-ocr", run_type="tool", tags=["stage:ocr"])
def detect_edu(filename: str, image_bytes: bytes, reader: easyocr.Reader | None = None) -> EduResult:
    """Run OCR on image bytes and determine if the document is an educational document."""
    # Preprocess (resize) to speed up OCR
    processed_bytes = _preprocess_image(image_bytes)
    
    r = reader if reader is not None else _get_reader()
    results = r.readtext(processed_bytes, detail=0)
    from src.privacy import mask_pii
    full_text = mask_pii(" ".join(results))

    if _is_edu(full_text):
        return EduResult(filename=filename, doc_type="education", send_to_llm=False, ocr_text=full_text)

    return EduResult(filename=filename, doc_type=None, send_to_llm=True, ocr_text=full_text)

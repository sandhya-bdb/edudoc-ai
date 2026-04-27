import os
from dataclasses import dataclass, field

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

MODEL = "gemma-4-31b-it"

CATEGORIES = [
    "Patient Bills",
    "Claim Forms",
    "KYC Documents",
    "Medical Reports",
    "Prescriptions",
    "Unknown",
]

PROMPT = (
    "You are a document classification assistant for MediShield Insurance.\n"
    "Examine the scanned document image and classify it into exactly one of these categories:\n\n"
    + "\n".join(f"- {c}" for c in CATEGORIES)
    + "\n\nRespond with only the category name, nothing else."
)


@dataclass
class LLMResult:
    filename: str
    doc_type: str          # always "image"
    sub_type: str          # one of CATEGORIES
    method: str            # always "llm"
    input_tokens: int = 0
    output_tokens: int = 0
    raw_response: str = field(default="", repr=False)


def _parse_category(text: str) -> str:
    normalized = text.strip()
    for cat in CATEGORIES:
        if cat.lower() == normalized.lower():
            return cat
    return "Unknown"


def classify_with_llm(
    filename: str,
    image_bytes: bytes,
    mime_type: str = "image/png",
    client: genai.Client | None = None,
) -> LLMResult:
    """Send image to Gemini and return a structured classification result."""
    if client is None:
        client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

    response = client.models.generate_content(
        model=MODEL,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            types.Part.from_text(text=PROMPT),
        ],
    )

    raw = response.text or ""
    sub_type = _parse_category(raw)

    input_tokens = 0
    output_tokens = 0
    if response.usage_metadata:
        input_tokens = response.usage_metadata.prompt_token_count or 0
        output_tokens = response.usage_metadata.candidates_token_count or 0

    return LLMResult(
        filename=filename,
        doc_type="image",
        sub_type=sub_type,
        method="llm",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        raw_response=raw,
    )

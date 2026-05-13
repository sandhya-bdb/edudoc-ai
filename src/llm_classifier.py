import os
from dataclasses import dataclass, field

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

MODEL = "gemma-4-31b-it"

CATEGORIES = [
    "Transcripts",
    "Certificates",
    "Student IDs",
    "Admission Letters",
    "Assignment Papers",
    "Unknown",
]

PROMPT = (
    "You are an educational document classification assistant for EduDoc AI.\n"
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


from langsmith import traceable


# Safety settings to block harmful content
SAFETY_SETTINGS = [
    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_MEDIUM_AND_ABOVE"),
    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_MEDIUM_AND_ABOVE"),
    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_MEDIUM_AND_ABOVE"),
    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_MEDIUM_AND_ABOVE"),
]

@traceable(name="llm-classify", run_type="llm", tags=["stage:llm"], metadata={"model": MODEL})
def classify_with_llm(
    filename: str,
    image_bytes: bytes,
    mime_type: str = "image/png",
    client: genai.Client | None = None,
) -> LLMResult:
    """Send image to Gemini and return a structured classification result."""
    if client is None:
        client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

    # Augmented prompt with privacy instructions
    privacy_prompt = (
        PROMPT + "\n\n"
        "IMPORTANT: Ignore all personally identifiable information (PII) like names, "
        "IDs, or addresses. Use only the document structure and headers to classify."
    )

    response = client.models.generate_content(
        model=MODEL,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            types.Part.from_text(text=privacy_prompt),
        ],
        config=types.GenerateContentConfig(
            safety_settings=SAFETY_SETTINGS,
            temperature=0.0,  # Deterministic for classification
        )
    )

    raw = response.text or ""
    sub_type = _parse_category(raw)

    input_tokens = 0
    output_tokens = 0
    if response.usage_metadata:
        input_tokens = response.usage_metadata.prompt_token_count or 0
        output_tokens = response.usage_metadata.candidates_token_count or 0

    # Set usage metadata for LangSmith cost calculation
    from langsmith.run_helpers import get_current_run_tree
    run_tree = get_current_run_tree()
    if run_tree:
        run_tree.metadata["usage"] = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }

    return LLMResult(
        filename=filename,
        doc_type="image",
        sub_type=sub_type,
        method="llm",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        raw_response=raw,
    )

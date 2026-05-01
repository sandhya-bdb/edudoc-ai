import re
from dataclasses import dataclass

_TRANSCRIPT_PATTERN = re.compile(r"^transcript_")
_CERT_PATTERN = re.compile(r"^cert_")


@dataclass
class RulesResult:
    filename: str
    doc_type: str | None
    send_to_llm: bool


def apply_rules(filename: str) -> RulesResult:
    """Apply filename-based rules before any ML processing."""
    name = filename.split("/")[-1].split("\\")[-1]

    if _TRANSCRIPT_PATTERN.match(name):
        return RulesResult(filename=filename, doc_type="transcript", send_to_llm=False)
    
    if _CERT_PATTERN.match(name):
        return RulesResult(filename=filename, doc_type="certificate", send_to_llm=False)

    return RulesResult(filename=filename, doc_type=None, send_to_llm=True)

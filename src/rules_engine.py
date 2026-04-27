import re
from dataclasses import dataclass

_BILL_PATTERN = re.compile(r"^bill_")


@dataclass
class RulesResult:
    filename: str
    doc_type: str | None
    send_to_llm: bool


def apply_rules(filename: str) -> RulesResult:
    """Apply filename-based rules before any ML processing."""
    name = filename.split("/")[-1].split("\\")[-1]

    if _BILL_PATTERN.match(name):
        return RulesResult(filename=filename, doc_type="bill", send_to_llm=False)

    return RulesResult(filename=filename, doc_type=None, send_to_llm=True)

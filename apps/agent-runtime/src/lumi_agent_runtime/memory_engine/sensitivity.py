from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .contracts import MemoryCandidate, MemorySensitivity

_CREDENTIAL_PATTERNS = (
    re.compile(r"(?i)\b(api[_ -]?key|access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|password)\b\s*[:=]"),
    re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
_PAYMENT_PATTERNS = (
    re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    re.compile(r"(?i)\b(cvv|cvc|card number|credit card|bank account|routing number)\b"),
)
_HEALTH_PATTERNS = (
    re.compile(r"(?i)\b(diagnosed|diagnosis|medical condition|prescription|medication|therapy|psychiatr|oncolog|diabetes|hiv|pregnan)\b"),
)
_OTHER_SENSITIVE = (
    re.compile(r"(?i)\b(social security|passport number|national id|driver'?s license)\b"),
)


@dataclass(frozen=True, slots=True)
class SensitivityResult:
    classification: MemorySensitivity
    reason: str | None = None


def classify_candidate(candidate: MemoryCandidate) -> SensitivityResult:
    text = candidate.summary + "\n" + json.dumps(candidate.content_structured, ensure_ascii=False, sort_keys=True)
    if any(pattern.search(text) for pattern in _CREDENTIAL_PATTERNS):
        return SensitivityResult(MemorySensitivity.CREDENTIAL, "MEMORY_CREDENTIAL_CONTENT_DENIED")
    if any(pattern.search(text) for pattern in _PAYMENT_PATTERNS):
        return SensitivityResult(MemorySensitivity.PAYMENT, "MEMORY_PAYMENT_CONTENT_DENIED")
    if any(pattern.search(text) for pattern in _HEALTH_PATTERNS):
        return SensitivityResult(MemorySensitivity.HEALTH, "MEMORY_HEALTH_CONTENT_DENIED")
    if any(pattern.search(text) for pattern in _OTHER_SENSITIVE):
        return SensitivityResult(MemorySensitivity.OTHER_SENSITIVE, "MEMORY_OTHER_SENSITIVE_DENIED")
    return SensitivityResult(MemorySensitivity.NONE)

from __future__ import annotations

import re


_TOKEN_PATTERNS = (
    re.compile(r"(?i)(authorization:\s*bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\b(AKIA|ASIA)[A-Z0-9]{16}\b"),
)


class SecretRedactor:
    def __init__(self, secrets: tuple[str, ...] = ()) -> None:
        self._secrets = tuple(value for value in secrets if len(value) >= 6)

    def redact(self, value: str) -> str:
        redacted = value
        for secret in self._secrets:
            redacted = redacted.replace(secret, "[REDACTED]")
        redacted = _TOKEN_PATTERNS[0].sub(r"\1[REDACTED]", redacted)
        for pattern in _TOKEN_PATTERNS[1:]:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted

    def redact_argv(self, argv: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(self.redact(item) for item in argv)

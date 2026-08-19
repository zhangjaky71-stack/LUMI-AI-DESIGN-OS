from __future__ import annotations


class ImageGenerationTransientError(RuntimeError):
    """Infrastructure failure that is safe to retry through the same operation id."""

    retryable = True

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message[:2000])
        self.code = code

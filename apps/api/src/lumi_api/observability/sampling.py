from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .models import LogLevel, SpanStatus


class SamplingDecision(StrEnum):
    RECORD_AND_SAMPLE = "RECORD_AND_SAMPLE"
    DROP = "DROP"


@dataclass(frozen=True, slots=True)
class DeterministicSampler:
    normal_sample_rate: float = 0.10

    def __post_init__(self) -> None:
        if not 0.0 <= self.normal_sample_rate <= 1.0:
            raise ValueError("OBSERVABILITY_SAMPLE_RATE_INVALID")

    def decide(
        self,
        *,
        trace_id: str,
        span_status: SpanStatus = SpanStatus.UNSET,
        log_level: LogLevel | None = None,
        force: bool = False,
    ) -> SamplingDecision:
        if len(trace_id) != 32 or any(char not in "0123456789abcdef" for char in trace_id):
            raise ValueError("OBSERVABILITY_TRACE_ID_INVALID")
        if force or span_status is SpanStatus.ERROR or log_level in {LogLevel.ERROR, LogLevel.CRITICAL}:
            return SamplingDecision.RECORD_AND_SAMPLE
        threshold = int(self.normal_sample_rate * (1 << 64))
        bucket = int(trace_id[:16], 16)
        return (
            SamplingDecision.RECORD_AND_SAMPLE
            if bucket < threshold
            else SamplingDecision.DROP
        )

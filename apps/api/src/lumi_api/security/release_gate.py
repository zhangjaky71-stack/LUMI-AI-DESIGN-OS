from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FindingSeverity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class SecurityFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    finding_id: str = Field(min_length=1, max_length=120)
    severity: FindingSeverity
    title: str = Field(min_length=1, max_length=240)
    status: str = Field(pattern=r"^(OPEN|FIXED|ACCEPTED)$")
    owner: str | None = Field(default=None, max_length=160)
    due_at: datetime | None = None
    accepted_until: datetime | None = None
    acceptance_reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_dates(self) -> SecurityFinding:
        for value in (self.due_at, self.accepted_until):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("SECURITY_FINDING_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        if self.status == "ACCEPTED":
            if not self.owner or not self.accepted_until or not self.acceptance_reason:
                raise ValueError("SECURITY_ACCEPTANCE_EVIDENCE_REQUIRED")
        if self.severity is FindingSeverity.MEDIUM and self.status == "OPEN":
            if not self.owner or self.due_at is None:
                raise ValueError("SECURITY_MEDIUM_REQUIRES_OWNER_DUE_DATE")
        return self


class SecurityReleaseDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed: bool
    blockers: tuple[str, ...] = ()
    accepted_high_risks: tuple[str, ...] = ()
    evaluated_at: datetime


class SecurityReleaseGate:
    """Fail-closed release policy for NODE-66.

    Production default is zero Critical and zero High. High-risk exceptions are
    disabled unless the caller explicitly enables the exception profile; even then
    the acceptance must be short-lived and fully evidenced.
    """

    def __init__(
        self,
        *,
        allow_high_risk_exception: bool = False,
        max_high_exception_days: int = 14,
    ) -> None:
        if max_high_exception_days < 1 or max_high_exception_days > 30:
            raise ValueError("SECURITY_HIGH_EXCEPTION_WINDOW_INVALID")
        self.allow_high_risk_exception = allow_high_risk_exception
        self.max_high_exception_days = max_high_exception_days

    def evaluate(
        self,
        findings: tuple[SecurityFinding, ...],
        *,
        now: datetime | None = None,
    ) -> SecurityReleaseDecision:
        evaluated_at = now or datetime.now(UTC)
        if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
            raise ValueError("SECURITY_RELEASE_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")

        blockers: list[str] = []
        accepted_high: list[str] = []
        for finding in findings:
            if finding.status == "FIXED":
                continue
            if finding.severity is FindingSeverity.CRITICAL:
                blockers.append(finding.finding_id)
                continue
            if finding.severity is FindingSeverity.HIGH:
                if self._accepted_high_is_valid(finding, evaluated_at):
                    accepted_high.append(finding.finding_id)
                else:
                    blockers.append(finding.finding_id)
                continue
            if finding.status == "ACCEPTED":
                if finding.accepted_until is None or finding.accepted_until <= evaluated_at:
                    blockers.append(finding.finding_id)

        return SecurityReleaseDecision(
            allowed=not blockers,
            blockers=tuple(sorted(set(blockers))),
            accepted_high_risks=tuple(sorted(set(accepted_high))),
            evaluated_at=evaluated_at,
        )

    def _accepted_high_is_valid(
        self,
        finding: SecurityFinding,
        now: datetime,
    ) -> bool:
        if not self.allow_high_risk_exception or finding.status != "ACCEPTED":
            return False
        if not finding.owner or not finding.acceptance_reason or finding.accepted_until is None:
            return False
        if finding.accepted_until <= now:
            return False
        return finding.accepted_until <= now + timedelta(days=self.max_high_exception_days)

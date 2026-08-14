from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .model import (
    AuthorizedReference,
    ImageGenerationSpec,
    StoredImage,
    ValidatedImage,
    ValidationBundle,
    ValidationFinding,
)


@dataclass(frozen=True, slots=True)
class DelegateValidationResult:
    findings: tuple[ValidationFinding, ...]
    snapshot_id: str | None = None


class ConstraintValidationDelegate(Protocol):
    async def validate_constraints(
        self,
        *,
        spec: ImageGenerationSpec,
        candidate_id: str,
        image: ValidatedImage,
        stored: StoredImage,
        references: tuple[AuthorizedReference, ...],
    ) -> DelegateValidationResult: ...


class BrandValidationDelegate(Protocol):
    async def validate_brand(
        self,
        *,
        spec: ImageGenerationSpec,
        candidate_id: str,
        image: ValidatedImage,
        stored: StoredImage,
        references: tuple[AuthorizedReference, ...],
    ) -> DelegateValidationResult: ...


class IdentityValidationDelegate(Protocol):
    async def validate_identity(
        self,
        *,
        spec: ImageGenerationSpec,
        candidate_id: str,
        image: ValidatedImage,
        stored: StoredImage,
        references: tuple[AuthorizedReference, ...],
    ) -> DelegateValidationResult: ...


class CompositeGenerationValidator:
    """Fail-closed postflight coordinator without reimplementing NODE-39/43/44 scoring."""

    def __init__(
        self,
        *,
        constraints: ConstraintValidationDelegate | None = None,
        brand: BrandValidationDelegate | None = None,
        identity: IdentityValidationDelegate | None = None,
    ) -> None:
        self.constraints = constraints
        self.brand = brand
        self.identity = identity

    async def validate(
        self,
        *,
        spec: ImageGenerationSpec,
        candidate_id: str,
        image: ValidatedImage,
        stored: StoredImage,
        references: tuple[AuthorizedReference, ...],
    ) -> ValidationBundle:
        findings: list[ValidationFinding] = []
        identity_snapshot: str | None = None
        brand_snapshot: str | None = None

        if spec.constraints:
            if self.constraints is None:
                severity = "HARD" if any(item.severity == "HARD" for item in spec.constraints) else "SOFT"
                findings.append(
                    ValidationFinding(
                        validator="constraint-validator",
                        status="UNAVAILABLE",
                        severity=severity,
                        reason_code="GENERATION_CONSTRAINT_VALIDATOR_UNAVAILABLE",
                    )
                )
            else:
                result = await self.constraints.validate_constraints(
                    spec=spec,
                    candidate_id=candidate_id,
                    image=image,
                    stored=stored,
                    references=references,
                )
                findings.extend(result.findings)

        if spec.brand_rule_set_version is not None:
            if self.brand is None:
                findings.append(
                    ValidationFinding(
                        validator="brand-rules-engine",
                        status="UNAVAILABLE",
                        severity="HARD",
                        reason_code="GENERATION_BRAND_VALIDATOR_UNAVAILABLE",
                    )
                )
            else:
                result = await self.brand.validate_brand(
                    spec=spec,
                    candidate_id=candidate_id,
                    image=image,
                    stored=stored,
                    references=references,
                )
                findings.extend(result.findings)
                brand_snapshot = result.snapshot_id

        if spec.identity_requirements:
            if self.identity is None:
                for requirement in spec.identity_requirements:
                    findings.append(
                        ValidationFinding(
                            validator="identity-engine",
                            status="UNAVAILABLE",
                            severity=requirement.severity,
                            reason_code="GENERATION_IDENTITY_VALIDATOR_UNAVAILABLE",
                            evidence_refs=(
                                f"identity:{requirement.identity_id}@{requirement.reference_set_version}",
                            ),
                        )
                    )
            else:
                result = await self.identity.validate_identity(
                    spec=spec,
                    candidate_id=candidate_id,
                    image=image,
                    stored=stored,
                    references=references,
                )
                findings.extend(result.findings)
                identity_snapshot = result.snapshot_id

        # An explicit technical pass is retained so downstream audit can distinguish
        # "no domain validators required" from "validation was skipped".
        findings.append(
            ValidationFinding(
                validator="image-integrity",
                status="PASS",
                severity="HARD",
                reason_code="GENERATION_IMAGE_INTEGRITY_VALIDATED",
                evidence_refs=(f"sha256:{image.checksum_sha256}",),
            )
        )

        return ValidationBundle(
            findings=tuple(findings),
            identity_validation_snapshot_id=identity_snapshot,
            brand_validation_snapshot_id=brand_snapshot,
        )

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from .model import (
    AuthorizedReference,
    ConstraintSeverity,
    ImageGenerationSpec,
    StoredImage,
    ValidatedImage,
    ValidationBundle,
    ValidationFinding,
    ValidationStatus,
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
        candidate_id: UUID,
        image: ValidatedImage,
        stored: StoredImage,
        references: tuple[AuthorizedReference, ...],
    ) -> DelegateValidationResult: ...


class BrandValidationDelegate(Protocol):
    async def validate_brand(
        self,
        *,
        spec: ImageGenerationSpec,
        candidate_id: UUID,
        image: ValidatedImage,
        stored: StoredImage,
        references: tuple[AuthorizedReference, ...],
    ) -> DelegateValidationResult: ...


class IdentityValidationDelegate(Protocol):
    async def validate_identity(
        self,
        *,
        spec: ImageGenerationSpec,
        candidate_id: UUID,
        image: ValidatedImage,
        stored: StoredImage,
        references: tuple[AuthorizedReference, ...],
    ) -> DelegateValidationResult: ...


class CompositeGenerationValidator:
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
        candidate_id: UUID,
        image: ValidatedImage,
        stored: StoredImage,
        references: tuple[AuthorizedReference, ...],
    ) -> ValidationBundle:
        findings: list[ValidationFinding] = []
        identity_snapshot = None
        brand_snapshot = None
        if spec.constraints:
            if self.constraints is None:
                severity = (
                    ConstraintSeverity.HARD
                    if any(item.severity is ConstraintSeverity.HARD for item in spec.constraints)
                    else ConstraintSeverity.SOFT
                )
                findings.append(
                    ValidationFinding(
                        "constraint-validator",
                        ValidationStatus.UNAVAILABLE,
                        severity,
                        "GENERATION_CONSTRAINT_VALIDATOR_UNAVAILABLE",
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
        if spec.brand_rule_set_version:
            if self.brand is None:
                findings.append(
                    ValidationFinding(
                        "brand-rules-engine",
                        ValidationStatus.UNAVAILABLE,
                        ConstraintSeverity.HARD,
                        "GENERATION_BRAND_VALIDATOR_UNAVAILABLE",
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
                for item in spec.identity_requirements:
                    findings.append(
                        ValidationFinding(
                            "identity-engine",
                            ValidationStatus.UNAVAILABLE,
                            item.severity,
                            "GENERATION_IDENTITY_VALIDATOR_UNAVAILABLE",
                            evidence_refs=(
                                f"identity:{item.identity_id}@{item.reference_set_version}",
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
        findings.append(
            ValidationFinding(
                "image-integrity",
                ValidationStatus.PASS,
                ConstraintSeverity.HARD,
                "GENERATION_IMAGE_INTEGRITY_VALIDATED",
                evidence_refs=(f"sha256:{image.checksum_sha256}",),
            )
        )
        return ValidationBundle(tuple(findings), identity_snapshot, brand_snapshot)

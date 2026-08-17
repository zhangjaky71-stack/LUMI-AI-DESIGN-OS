from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .model import (
    EditFinding,
    EditValidationReport,
    ImageEditSpec,
    SourceImageRef,
    ValidatedImage,
)


class ValidatorDelegate(Protocol):
    async def validate(
        self,
        *,
        spec: ImageEditSpec,
        image: ValidatedImage,
        source: SourceImageRef,
    ) -> tuple[EditFinding, ...]: ...


@dataclass(slots=True)
class CompositePostflight:
    protected: ValidatorDelegate | None = None
    constraints: ValidatorDelegate | None = None
    brand: ValidatorDelegate | None = None
    identity: ValidatorDelegate | None = None
    qr: ValidatorDelegate | None = None
    ocr: ValidatorDelegate | None = None
    intended_change: ValidatorDelegate | None = None

    async def validate(
        self,
        *,
        spec: ImageEditSpec,
        image: ValidatedImage,
        source: SourceImageRef,
    ) -> EditValidationReport:
        findings: list[EditFinding] = []
        required = (
            ("protected-region", self.protected, bool(spec.protected_regions)),
            ("constraint-validator", self.constraints, bool(spec.constraints)),
            (
                "brand-rules-engine",
                self.brand,
                spec.brand_rule_set_version is not None,
            ),
            ("identity-engine", self.identity, bool(spec.identity_requirement_ids)),
            (
                "qr-decoder",
                self.qr,
                any(region.role == "QR" for region in spec.protected_regions),
            ),
            (
                "locked-text-ocr",
                self.ocr,
                any(
                    region.role in {"LOCKED_TEXT", "LOGO"}
                    and region.expected_text
                    for region in spec.protected_regions
                ),
            ),
            ("intended-change", self.intended_change, True),
        )
        for name, delegate, needed in required:
            if not needed:
                continue
            if delegate is None:
                reason = f"IMAGE_EDIT_{name.upper().replace('-', '_')}_UNAVAILABLE"
                findings.append(
                    EditFinding(name, "UNAVAILABLE", "HARD", reason)
                )
            else:
                findings.extend(
                    await delegate.validate(
                        spec=spec,
                        image=image,
                        source=source,
                    )
                )

        if (image.width, image.height) != (source.width, source.height):
            findings.append(
                EditFinding(
                    "resolution",
                    "FAIL",
                    "HARD",
                    "IMAGE_EDIT_OUTPUT_DIMENSIONS_CHANGED",
                )
            )
        else:
            findings.append(
                EditFinding(
                    "resolution",
                    "PASS",
                    "HARD",
                    "IMAGE_EDIT_OUTPUT_DIMENSIONS_PRESERVED",
                )
            )
        identity_snapshot = next(
            (
                finding.evidence_ref
                for finding in findings
                if finding.validator == "identity-engine"
                and finding.evidence_ref
            ),
            None,
        )
        return EditValidationReport(tuple(findings), identity_snapshot)

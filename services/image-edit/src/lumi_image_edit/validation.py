from __future__ import annotations

from typing import Protocol

from .model import EditFinding, EditPlan, EditValidationReport, ImageEditSpec
from .ports import StoredEditedImage


class ProtectedRegionDelegate(Protocol):
    async def compare_protected_regions(
        self, *, spec: ImageEditSpec, candidate: StoredEditedImage
    ) -> tuple[EditFinding, ...]: ...


class IdentityDelegate(Protocol):
    async def validate_identity(
        self, *, spec: ImageEditSpec, candidate: StoredEditedImage
    ) -> tuple[tuple[EditFinding, ...], str | None]: ...


class QrDelegate(Protocol):
    async def validate_qr(
        self, *, spec: ImageEditSpec, candidate: StoredEditedImage
    ) -> tuple[EditFinding, ...]: ...


class OcrDelegate(Protocol):
    async def validate_locked_text(
        self, *, spec: ImageEditSpec, candidate: StoredEditedImage
    ) -> tuple[EditFinding, ...]: ...


class IntendedChangeDelegate(Protocol):
    async def validate_intended_change(
        self, *, spec: ImageEditSpec, plan: EditPlan, candidate: StoredEditedImage
    ) -> tuple[EditFinding, ...]: ...


class CompositeEditValidator:
    def __init__(
        self,
        *,
        protected: ProtectedRegionDelegate | None = None,
        identity: IdentityDelegate | None = None,
        qr: QrDelegate | None = None,
        ocr: OcrDelegate | None = None,
        intended_change: IntendedChangeDelegate | None = None,
    ) -> None:
        self.protected = protected
        self.identity = identity
        self.qr = qr
        self.ocr = ocr
        self.intended_change = intended_change

    async def validate(
        self,
        *,
        spec: ImageEditSpec,
        plan: EditPlan,
        candidate: StoredEditedImage,
    ) -> EditValidationReport:
        findings: list[EditFinding] = []
        identity_snapshot: str | None = None

        if (candidate.width, candidate.height) != (spec.source.width, spec.source.height):
            findings.append(EditFinding(
                validator="resolution",
                status="FAIL",
                severity="HARD",
                reason_code="IMAGE_EDIT_DIMENSIONS_CHANGED",
            ))
        else:
            findings.append(EditFinding(
                validator="resolution",
                status="PASS",
                severity="HARD",
                reason_code="IMAGE_EDIT_DIMENSIONS_PRESERVED",
            ))

        if spec.protected_regions:
            if self.protected is None:
                findings.append(EditFinding(
                    validator="protected-region",
                    status="UNAVAILABLE",
                    severity="HARD",
                    reason_code="IMAGE_EDIT_PROTECTED_REGION_VALIDATOR_UNAVAILABLE",
                ))
            else:
                findings.extend(await self.protected.compare_protected_regions(spec=spec, candidate=candidate))

        if spec.identity_requirement_ids:
            if self.identity is None:
                findings.append(EditFinding(
                    validator="identity-engine",
                    status="UNAVAILABLE",
                    severity="HARD",
                    reason_code="IMAGE_EDIT_IDENTITY_VALIDATOR_UNAVAILABLE",
                ))
            else:
                identity_findings, identity_snapshot = await self.identity.validate_identity(
                    spec=spec, candidate=candidate
                )
                findings.extend(identity_findings)

        if any(region.role == "QR" for region in spec.protected_regions):
            if self.qr is None:
                findings.append(EditFinding(
                    validator="qr-scannability",
                    status="UNAVAILABLE",
                    severity="HARD",
                    reason_code="IMAGE_EDIT_QR_VALIDATOR_UNAVAILABLE",
                ))
            else:
                findings.extend(await self.qr.validate_qr(spec=spec, candidate=candidate))

        if any(region.role == "LOCKED_TEXT" for region in spec.protected_regions):
            if self.ocr is None:
                findings.append(EditFinding(
                    validator="ocr-lock",
                    status="UNAVAILABLE",
                    severity="HARD",
                    reason_code="IMAGE_EDIT_OCR_VALIDATOR_UNAVAILABLE",
                ))
            else:
                findings.extend(await self.ocr.validate_locked_text(spec=spec, candidate=candidate))

        if self.intended_change is None:
            findings.append(EditFinding(
                validator="intended-change",
                status="UNAVAILABLE",
                severity="HARD",
                reason_code="IMAGE_EDIT_INTENDED_CHANGE_VALIDATOR_UNAVAILABLE",
            ))
        else:
            findings.extend(await self.intended_change.validate_intended_change(
                spec=spec, plan=plan, candidate=candidate
            ))

        return EditValidationReport(
            findings=tuple(findings),
            identity_validation_snapshot_id=identity_snapshot,
        )

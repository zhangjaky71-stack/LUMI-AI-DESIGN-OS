from __future__ import annotations

from uuid import UUID

from lumi_image_edit import (
    EditFinding,
    ImageEditSpec,
    SourceImageRef,
    ValidatedImage,
)
from lumi_api.identity_engine.contracts import (
    CandidateIdentity,
    IdentityStatus,
    canonical_hash,
)
from lumi_api.identity_engine.service import IdentityService


class Node44IdentityPostflightDelegate:
    """Fail-closed NODE-44 identity postflight over a materialized candidate Asset."""

    def __init__(self, service: IdentityService) -> None:
        self.service = service

    @staticmethod
    def _severity(spec: ImageEditSpec, identity_id: str) -> str:
        for region in spec.protected_regions:
            if region.identity_id == identity_id:
                return region.severity
        return "HARD"

    async def validate(
        self,
        *,
        spec: ImageEditSpec,
        image: ValidatedImage,
        source: SourceImageRef,
    ) -> tuple[EditFinding, ...]:
        del source
        if not spec.identity_requirement_ids:
            return ()
        if image.asset_id is None:
            return tuple(
                EditFinding(
                    "identity-engine",
                    "UNAVAILABLE",
                    self._severity(spec, identity_id),
                    "IMAGE_EDIT_IDENTITY_CANDIDATE_ASSET_UNAVAILABLE",
                )
                for identity_id in spec.identity_requirement_ids
            )

        results = []
        for identity_id in spec.identity_requirement_ids:
            result = self.service.validate(
                organization_id=UUID(spec.organization_id),
                identity_id=UUID(identity_id),
                candidate=CandidateIdentity(asset_id=UUID(image.asset_id)),
            )
            results.append(result)

        snapshot_id = "identity-validation:" + canonical_hash(
            [result.model_dump(mode="json") for result in results]
        )
        findings = []
        for identity_id, result in zip(
            spec.identity_requirement_ids,
            results,
            strict=True,
        ):
            if result.status is IdentityStatus.PASS:
                status = "PASS"
                reason = "IMAGE_EDIT_IDENTITY_PRESERVED"
            elif result.status is IdentityStatus.VALIDATION_UNAVAILABLE:
                status = "UNAVAILABLE"
                reason = "IMAGE_EDIT_IDENTITY_VALIDATION_UNAVAILABLE"
            else:
                status = "FAIL"
                reason = f"IMAGE_EDIT_IDENTITY_{result.status.value}"
            findings.append(
                EditFinding(
                    "identity-engine",
                    status,
                    self._severity(spec, identity_id),
                    reason,
                    score=result.score_01,
                    threshold=result.threshold_profile.min_score / 100.0,
                    evidence_ref=snapshot_id,
                )
            )
        return tuple(findings)

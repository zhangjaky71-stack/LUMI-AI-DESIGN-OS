from __future__ import annotations

from typing import Protocol

from lumi_api.brand_rules.contracts import ComplianceResult
from lumi_api.constraint_validator.contracts import (
    ConstraintViolation,
    ValidationReport,
)
from lumi_api.identity_engine.contracts import (
    IdentitySeverity,
    IdentityStatus,
    IdentityType,
    IdentityValidationResult,
)
from lumi_visual_critic.model import (
    ArtifactQualityInput,
    DimensionAssessment,
    EvidenceKind,
    QualityDimension,
    QualityEvidence,
    QualitySeverity,
    QualitySignalBundle,
    QualityTaskSpec,
    QualityViolation,
    RepairAction,
    RepairActionType,
)


class ConstraintQualityBackend(Protocol):
    async def validate_exact(
        self,
        *,
        artifact_version_id: str,
        phase: str,
    ) -> ValidationReport: ...


class BrandQualityBackend(Protocol):
    async def validate_brand(
        self,
        *,
        artifact_version_id: str,
        brand_rule_snapshot_id: str,
    ) -> ComplianceResult: ...


class IdentityQualityBackend(Protocol):
    async def validate_identities(
        self,
        *,
        artifact_version_id: str,
        identity_refs: tuple[str, ...],
    ) -> tuple[IdentityValidationResult, ...]: ...


def _severity(value: str, *, blocking: bool = False) -> QualitySeverity:
    if blocking or value == "HARD":
        return QualitySeverity.HARD
    if value in {"SOFT", "ERROR"}:
        return QualitySeverity.ERROR
    if value in {"ADVISORY", "WARN", "WARNING"}:
        return QualitySeverity.WARNING
    return QualitySeverity.INFO


def _repair_from_constraint(
    item: ConstraintViolation,
) -> tuple[RepairAction, ...]:
    actions: list[RepairAction] = []
    supported = {
        "SET_PROPERTY": RepairActionType.SET_PROPERTY,
        "MOVE_NODE": RepairActionType.MOVE_NODE,
        "RESIZE_NODE": RepairActionType.RESIZE_NODE,
        "SET_TEXT": RepairActionType.REPLACE_TEXT,
        "REPLACE_ASSET": RepairActionType.REPLACE_ASSET,
        "APPLY_STYLE": RepairActionType.SET_PROPERTY,
    }
    for operation in item.suggested_fix_operations:
        op_type = str(operation.get("type", ""))
        action_type = supported.get(op_type)
        if action_type is None:
            continue
        target = str(
            operation.get("node_id")
            or operation.get("target")
            or (
                item.affected_node_ids[0]
                if item.affected_node_ids
                else "document"
            )
        )
        parameters = dict(operation)
        if (
            action_type is RepairActionType.REPLACE_TEXT
            and "text" not in parameters
        ):
            if "value" in parameters:
                parameters["text"] = parameters["value"]
            else:
                continue
        if (
            action_type is RepairActionType.SET_PROPERTY
            and "property" not in parameters
        ):
            parameters["property"] = str(parameters.get("key", "style"))
        actions.append(
            RepairAction(
                action_type=action_type,
                target=target,
                reason_code=f"CONSTRAINT:{item.type}",
                parameters=parameters,
                expected_effect=(
                    QualityDimension.CONSTRAINT_COMPLIANCE,
                ),
            )
        )
    return tuple(actions)


class Node39ConstraintSignalAdapter:
    source_id = "node39.constraint-runtime"
    deterministic = True

    def __init__(self, backend: ConstraintQualityBackend) -> None:
        self.backend = backend

    async def evaluate(
        self,
        *,
        spec: QualityTaskSpec,
        artifact: ArtifactQualityInput,
    ) -> QualitySignalBundle:
        report = await self.backend.validate_exact(
            artifact_version_id=artifact.artifact_version_id,
            phase="export",
        )
        evidence = QualityEvidence(
            evidence_id=f"constraint:{artifact.artifact_version_id}",
            kind=EvidenceKind.CONSTRAINT_RUNTIME,
            source_version="node39/1.0",
            summary=(
                f"{report.status}; "
                f"validators={len(report.metrics.validators_run)}"
            ),
            refs=tuple(report.metrics.validators_run),
            data={
                "hard_pass": report.hard_pass,
                "health_score": report.health_score,
                "violations": report.metrics.violations_count,
                "blocking": report.metrics.blocking_count,
            },
        )
        violations = tuple(
            QualityViolation(
                violation_id=item.violation_id,
                dimension=_constraint_dimension(
                    item.validator,
                    item.type,
                ),
                code=f"CONSTRAINT_{item.type}",
                severity=_severity(
                    item.severity,
                    blocking=item.blocking,
                ),
                message=item.message,
                confidence=0.0 if item.unavailable else 1.0,
                blocking=item.blocking,
                evidence_ids=(evidence.evidence_id,),
                repair_actions=_repair_from_constraint(item),
            )
            for item in report.violations
        )
        dimensions = {
            QualityDimension.CONSTRAINT_COMPLIANCE: report.health_score,
        }
        validators = set(report.metrics.validators_run)
        if "QRValidator" in validators:
            dimensions[QualityDimension.QR_READABILITY] = (
                0.0
                if any(
                    item.validator == "QRValidator"
                    for item in report.violations
                )
                else 100.0
            )
        if "TextOverflowValidator" in validators:
            dimensions[QualityDimension.TYPOGRAPHY_READABILITY] = (
                0.0
                if any(
                    item.validator
                    in {"TextOverflowValidator", "FontSizeValidator"}
                    for item in report.violations
                )
                else 100.0
            )
        if "ContrastValidator" in validators:
            dimensions[QualityDimension.CONTRAST] = (
                0.0
                if any(
                    item.validator == "ContrastValidator"
                    for item in report.violations
                )
                else 100.0
            )
        if "ExportDimensionValidator" in validators:
            dimensions[
                QualityDimension.RESOLUTION_EXPORT_READINESS
            ] = (
                0.0
                if any(
                    item.validator == "ExportDimensionValidator"
                    for item in report.violations
                )
                else 100.0
            )
        assessments = tuple(
            DimensionAssessment(
                dimension=dimension,
                score=score,
                confidence=(
                    1.0
                    if report.status != "VALIDATION_UNAVAILABLE"
                    else 0.0
                ),
                threshold=spec.profile.thresholds[dimension],
                severity=(
                    QualitySeverity.HARD
                    if (
                        dimension in spec.profile.hard_dimensions
                        and score < spec.profile.thresholds[dimension]
                    )
                    else QualitySeverity.INFO
                ),
                evidence_ids=(evidence.evidence_id,),
                grader_id=self.source_id,
            )
            for dimension, score in dimensions.items()
        )
        return QualitySignalBundle(
            source_id=self.source_id,
            deterministic=True,
            assessments=assessments,
            violations=violations,
            evidence=(evidence,),
            unavailable_reason=(
                "NODE39_VALIDATION_UNAVAILABLE"
                if report.status == "VALIDATION_UNAVAILABLE"
                else None
            ),
        )


def _constraint_dimension(
    validator: str,
    constraint_type: str,
) -> QualityDimension:
    if validator in {"TextOverflowValidator", "FontSizeValidator"}:
        return QualityDimension.TYPOGRAPHY_READABILITY
    if validator == "ContrastValidator":
        return QualityDimension.CONTRAST
    if validator == "QRValidator":
        return QualityDimension.QR_READABILITY
    if validator == "BrandTokenValidator":
        return QualityDimension.BRAND_CONSISTENCY
    if validator == "IdentityPreservationValidator":
        return QualityDimension.IDENTITY_CONSISTENCY
    if validator == "ExportDimensionValidator":
        return QualityDimension.RESOLUTION_EXPORT_READINESS
    if constraint_type.startswith("LOCK_"):
        return QualityDimension.CONSTRAINT_COMPLIANCE
    return QualityDimension.CONSTRAINT_COMPLIANCE


class Node43BrandSignalAdapter:
    source_id = "node43.brand-validator"
    deterministic = True

    def __init__(self, backend: BrandQualityBackend) -> None:
        self.backend = backend

    async def evaluate(
        self,
        *,
        spec: QualityTaskSpec,
        artifact: ArtifactQualityInput,
    ) -> QualitySignalBundle:
        if artifact.brand_rule_snapshot_id is None:
            return QualitySignalBundle(
                source_id=self.source_id,
                deterministic=True,
                assessments=(),
                violations=(),
                evidence=(),
            )
        result = await self.backend.validate_brand(
            artifact_version_id=artifact.artifact_version_id,
            brand_rule_snapshot_id=artifact.brand_rule_snapshot_id,
        )
        evidence = QualityEvidence(
            evidence_id=(
                f"brand:{artifact.artifact_version_id}:"
                f"{result.rule_set_id}"
            ),
            kind=EvidenceKind.BRAND_VALIDATOR,
            source_version=(
                f"brand-ruleset:{result.rule_set_version}"
            ),
            summary=(
                f"brand score={result.score}; "
                f"can_approve={result.can_approve}"
            ),
            refs=(str(result.rule_set_id),),
        )
        violations = tuple(
            QualityViolation(
                violation_id=(
                    f"brand:{item.rule_id}:{item.code}"
                ),
                dimension=(
                    QualityDimension.LOGO_INTEGRITY
                    if (
                        "LOGO" in item.code.upper()
                        or "LOGO" in item.rule_key.upper()
                    )
                    else QualityDimension.BRAND_CONSISTENCY
                ),
                code=item.code,
                severity=_severity(
                    item.severity.value,
                    blocking=item.blocking,
                ),
                message=f"Brand rule {item.rule_key} failed",
                confidence=0.0 if item.unavailable else 1.0,
                blocking=item.blocking,
                evidence_ids=(evidence.evidence_id,),
            )
            for item in result.violations
        )
        logo_failed = any(
            violation.dimension is QualityDimension.LOGO_INTEGRITY
            for violation in violations
        )
        assessments = [
            DimensionAssessment(
                dimension=QualityDimension.BRAND_CONSISTENCY,
                score=result.score,
                confidence=1.0,
                threshold=spec.profile.thresholds[
                    QualityDimension.BRAND_CONSISTENCY
                ],
                severity=(
                    QualitySeverity.HARD
                    if any(
                        violation.blocking
                        and violation.dimension
                        is QualityDimension.BRAND_CONSISTENCY
                        for violation in violations
                    )
                    else QualitySeverity.INFO
                ),
                evidence_ids=(evidence.evidence_id,),
                grader_id=self.source_id,
            )
        ]
        if logo_failed:
            assessments.append(
                DimensionAssessment(
                    dimension=QualityDimension.LOGO_INTEGRITY,
                    score=0.0,
                    confidence=1.0,
                    threshold=spec.profile.thresholds[
                        QualityDimension.LOGO_INTEGRITY
                    ],
                    severity=(
                        QualitySeverity.HARD
                        if any(
                            violation.blocking
                            and violation.dimension
                            is QualityDimension.LOGO_INTEGRITY
                            for violation in violations
                        )
                        else QualitySeverity.ERROR
                    ),
                    evidence_ids=(evidence.evidence_id,),
                    grader_id=self.source_id,
                )
            )
        return QualitySignalBundle(
            source_id=self.source_id,
            deterministic=True,
            assessments=tuple(assessments),
            violations=violations,
            evidence=(evidence,),
        )


class Node44IdentitySignalAdapter:
    source_id = "node44.identity-engine"
    deterministic = True

    def __init__(self, backend: IdentityQualityBackend) -> None:
        self.backend = backend

    async def evaluate(
        self,
        *,
        spec: QualityTaskSpec,
        artifact: ArtifactQualityInput,
    ) -> QualitySignalBundle:
        if not artifact.identity_refs:
            return QualitySignalBundle(
                source_id=self.source_id,
                deterministic=True,
                assessments=(),
                violations=(),
                evidence=(),
            )
        results = await self.backend.validate_identities(
            artifact_version_id=artifact.artifact_version_id,
            identity_refs=artifact.identity_refs,
        )
        evidence: list[QualityEvidence] = []
        violations: list[QualityViolation] = []
        scores: list[float] = []
        confidences: list[float] = []
        for result in results:
            evidence_id = (
                f"identity:{result.identity_id}:"
                f"v{result.reference_version}"
            )
            evidence.append(
                QualityEvidence(
                    evidence_id=evidence_id,
                    kind=EvidenceKind.IDENTITY_ENGINE,
                    source_version=(
                        result.provider_version or "node44/unknown"
                    ),
                    summary=(
                        f"{result.identity_type.value}:"
                        f"{result.status.value}"
                    ),
                    refs=result.evidence_refs,
                    data={
                        "score": result.identity_score,
                        "confidence": result.confidence,
                        "profile_key": (
                            result.threshold_profile.profile_key
                        ),
                        "profile_version": (
                            result.threshold_profile.version
                        ),
                    },
                )
            )
            if result.identity_score is not None:
                scores.append(result.identity_score)
                confidences.append(result.confidence)
            if result.status is not IdentityStatus.PASS:
                blocking = (
                    result.status is IdentityStatus.BLOCKED
                    or result.threshold_profile.severity
                    is IdentitySeverity.HARD
                )
                dimension = (
                    QualityDimension.LOGO_INTEGRITY
                    if result.identity_type is IdentityType.LOGO
                    else QualityDimension.IDENTITY_CONSISTENCY
                )
                violations.append(
                    QualityViolation(
                        violation_id=(
                            f"identity:{result.identity_id}:"
                            f"{result.status.value}"
                        ),
                        dimension=dimension,
                        code=(
                            result.failure_codes[0]
                            if result.failure_codes
                            else result.status.value
                        ),
                        severity=_severity(
                            result.threshold_profile.severity.value,
                            blocking=blocking,
                        ),
                        message=(
                            f"Identity {result.identity_id} "
                            f"{result.status.value}"
                        ),
                        confidence=result.confidence,
                        blocking=blocking,
                        evidence_ids=(evidence_id,),
                        repair_actions=(
                            RepairAction(
                                action_type=(
                                    RepairActionType.REGENERATE_REGION
                                ),
                                target=(
                                    result.candidate_node_id
                                    or "identity-region"
                                ),
                                reason_code=(
                                    "IDENTITY_PRESERVATION_FAILED"
                                ),
                                expected_effect=(dimension,),
                            ),
                        ),
                    )
                )
        score = min(scores) if scores else 0.0
        confidence = min(confidences) if confidences else 0.0
        assessment = DimensionAssessment(
            dimension=QualityDimension.IDENTITY_CONSISTENCY,
            score=score,
            confidence=confidence,
            threshold=spec.profile.thresholds[
                QualityDimension.IDENTITY_CONSISTENCY
            ],
            severity=(
                QualitySeverity.HARD
                if any(violation.blocking for violation in violations)
                else QualitySeverity.INFO
            ),
            evidence_ids=tuple(item.evidence_id for item in evidence),
            grader_id=self.source_id,
        )
        return QualitySignalBundle(
            source_id=self.source_id,
            deterministic=True,
            assessments=(assessment,),
            violations=tuple(violations),
            evidence=tuple(evidence),
            unavailable_reason=(
                "NODE44_IDENTITY_VALIDATION_UNAVAILABLE"
                if any(
                    result.status
                    is IdentityStatus.VALIDATION_UNAVAILABLE
                    for result in results
                )
                else None
            ),
        )

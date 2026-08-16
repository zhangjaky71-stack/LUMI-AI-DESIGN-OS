from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping
from uuid import UUID

from .registry import CapabilityRegistry, ModelRecord, RoutingProfile

_DIMENSIONS = ("quality", "constraint", "cost", "latency", "availability")


@dataclass(frozen=True, slots=True)
class RoutingEvidence:
    quality: Decimal | None = None
    constraint: Decimal | None = None
    cost: Decimal | None = None
    latency: Decimal | None = None
    availability: Decimal | None = None

    def __post_init__(self) -> None:
        for name in _DIMENSIONS:
            value = getattr(self, name)
            if value is not None and not Decimal("0") <= value <= Decimal("100"):
                raise ValueError(f"routing evidence {name} must be 0..100")


@dataclass(frozen=True, slots=True)
class ProfileEvaluation:
    model_key: str
    score: Decimal | None
    complete: bool
    reason_codes: tuple[str, ...]


class RoutingProfileEvaluator:
    """Evaluate versioned profile weights without inventing missing measurements."""

    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry

    def evaluate(
        self,
        profile_name: str,
        *,
        organization_id: UUID,
        evidence: Mapping[str, RoutingEvidence],
    ) -> tuple[ProfileEvaluation, ...]:
        snapshot = self.registry.capture_snapshot()
        try:
            profile = snapshot.routing_profiles[profile_name]
        except KeyError as exc:
            raise KeyError(f"unknown routing profile: {profile_name}") from exc
        policy = self.registry.policy_for(organization_id)
        evaluations: list[tuple[int, ProfileEvaluation]] = []
        for ordinal, model_key in enumerate(profile.candidate_model_keys):
            record = snapshot.models.get(model_key)
            if record is None or not self._eligible(record, profile, policy):
                continue
            value = evidence.get(model_key, RoutingEvidence())
            reasons: list[str] = []
            if profile.minimum_quality is not None:
                if value.quality is None:
                    reasons.append("minimum_quality_unmeasured")
                elif value.quality < profile.minimum_quality:
                    reasons.append("minimum_quality_not_met")
                    evaluations.append(
                        (
                            ordinal,
                            ProfileEvaluation(model_key, None, False, tuple(reasons)),
                        )
                    )
                    continue
            weighted = self._weighted_score(profile, value, reasons)
            evaluations.append(
                (
                    ordinal,
                    ProfileEvaluation(
                        model_key=model_key,
                        score=weighted,
                        complete=weighted is not None,
                        reason_codes=tuple(reasons),
                    ),
                )
            )
        evaluations.sort(
            key=lambda item: (
                item[1].score is None,
                -(item[1].score or Decimal("0")),
                item[0],
            )
        )
        return tuple(item[1] for item in evaluations)

    @staticmethod
    def _eligible(
        record: ModelRecord,
        profile: RoutingProfile,
        policy: object | None,
    ) -> bool:
        if not record.route_eligible:
            return False
        if any(
            not record.supports(capability)
            for capability in profile.required_capabilities
        ):
            return False
        if policy is not None:
            disabled = getattr(policy, "disabled_providers", frozenset())
            if record.provider in disabled:
                return False
        return True

    @staticmethod
    def _weighted_score(
        profile: RoutingProfile,
        evidence: RoutingEvidence,
        reasons: list[str],
    ) -> Decimal | None:
        weights = profile.weights
        pairs = (
            ("quality", weights.quality),
            ("constraint", weights.constraint),
            ("cost", weights.cost),
            ("latency", weights.latency),
            ("availability", weights.availability),
        )
        total = Decimal("0")
        missing: list[str] = []
        for name, weight in pairs:
            if weight == 0:
                continue
            value = getattr(evidence, name)
            if value is None:
                missing.append(name)
                continue
            total += value * weight
        if missing:
            reasons.append("insufficient_evidence:" + ",".join(sorted(missing)))
            return None
        reasons.append("profile_evidence_complete")
        return total.quantize(Decimal("0.0001"))

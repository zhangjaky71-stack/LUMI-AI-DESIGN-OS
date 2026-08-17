from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .contracts import (
    SOURCE_PRIORITY,
    SOURCE_PRIORITY_RANK,
    CompiledContextBundle,
    ConstraintStrength,
    ContextCompileRequest,
    ContextConstraint,
    ContextFactChannel,
    ContextScopeKind,
    ContextSourceSnapshot,
    ContextSourceType,
    bundle_content_hash,
    canonical_json,
    sha256_json,
)
from .errors import (
    ContextConflict,
    ContextConflictError,
    ContextSourcePermissionError,
    ContextSourceValidationError,
)
from .store import ContextBundleStore

_SEVERITY_RANK = {
    ConstraintStrength.HARD: 3,
    ConstraintStrength.SOFT: 2,
    ConstraintStrength.ADVISORY: 1,
}


@dataclass(frozen=True, slots=True)
class _FactCandidate:
    key: str
    channel: str
    source: ContextSourceSnapshot
    payload: dict[str, Any]

    @property
    def fingerprint(self) -> str:
        return sha256_json(self.payload)


@dataclass(frozen=True, slots=True)
class _ConstraintCandidate:
    source: ContextSourceSnapshot
    constraint: ContextConstraint

    @property
    def group_key(self) -> tuple[str, str]:
        return (
            self.constraint.constraint_type,
            canonical_json(self.constraint.scope.canonical_payload()),
        )

    @property
    def parameters_fingerprint(self) -> str:
        return sha256_json(dict(self.constraint.parameters))


class ContextCompiler:
    def __init__(self, store: ContextBundleStore) -> None:
        self.store = store

    async def compile(
        self,
        *,
        request: ContextCompileRequest,
        sources: tuple[ContextSourceSnapshot, ...],
    ) -> CompiledContextBundle:
        validated = self._validate_sources(request, sources)
        constraint_set, constraint_provenance, shadowed_constraints, inactive = (
            self._resolve_constraints(validated)
        )
        pinned_facts, shadowed_pinned = self._resolve_facts(
            validated, ContextFactChannel.PINNED
        )
        task_facts, shadowed_task = self._resolve_facts(
            validated, ContextFactChannel.TASK
        )

        source_refs = tuple(item.source_ref for item in validated)
        source_hashes = tuple(item.content_hash for item in validated)
        required_scopes = _required_memory_scopes(validated)

        pinned_constraints = canonical_json(
            {
                "constraint_set": constraint_set,
                "inactive_constraints": inactive,
                "provenance": constraint_provenance,
                "schema": "lumi.context-constraints/1.0",
                "shadowed": shadowed_constraints,
                "source_priority": [item.value for item in SOURCE_PRIORITY],
            }
        )
        task_context = canonical_json(
            {
                "brand_id": request.brand_id,
                "organization_id": str(request.organization_id),
                "pinned_facts": pinned_facts,
                "project_id": str(request.project_id),
                "required_memory_scopes": list(required_scopes),
                "schema": "lumi.context-task/1.0",
                "shadowed_pinned_facts": shadowed_pinned,
                "shadowed_task_facts": shadowed_task,
                "source_provenance": [
                    {"content_hash": item.content_hash, "source_ref": item.source_ref}
                    for item in validated
                ],
                "task_facts": task_facts,
                "task_id": str(request.task_id) if request.task_id else None,
                "user_id": request.user_id,
            }
        )
        if len(pinned_constraints) > 128_000:
            raise ContextSourceValidationError(
                "CONTEXT_PINNED_CONSTRAINTS_TOO_LARGE"
            )
        if len(task_context) > 128_000:
            raise ContextSourceValidationError("CONTEXT_TASK_CONTEXT_TOO_LARGE")
        digest = bundle_content_hash(
            version=request.version,
            pinned_constraints=pinned_constraints,
            task_context=task_context,
            source_refs=source_refs,
        )
        ref = (
            f"context-bundle://{request.organization_id}/"
            f"{request.project_id}/{digest}"
        )
        bundle = CompiledContextBundle(
            context_bundle_ref=ref,
            version=request.version,
            organization_id=request.organization_id,
            project_id=request.project_id,
            task_id=request.task_id,
            brand_id=request.brand_id,
            user_id=request.user_id,
            required_memory_scopes=required_scopes,
            pinned_constraints=pinned_constraints,
            task_context=task_context,
            source_refs=source_refs,
            source_hashes=source_hashes,
            content_hash=digest,
        )
        await self.store.put(bundle)
        return bundle

    def _validate_sources(
        self,
        request: ContextCompileRequest,
        sources: tuple[ContextSourceSnapshot, ...],
    ) -> tuple[ContextSourceSnapshot, ...]:
        refs = tuple(item.source_ref for item in sources)
        if len(refs) != len(set(refs)):
            raise ContextSourceValidationError("CONTEXT_SOURCE_REF_DUPLICATE")
        constraint_ids = [
            str(constraint.constraint_id)
            for source in sources
            for constraint in source.constraints
        ]
        if len(constraint_ids) != len(set(constraint_ids)):
            raise ContextSourceValidationError("CONTEXT_CONSTRAINT_ID_DUPLICATE")
        for source in sources:
            if source.content_hash != source.expected_content_hash():
                raise ContextSourceValidationError(
                    f"CONTEXT_SOURCE_HASH_MISMATCH:{source.source_ref}"
                )
            _assert_scope_matches(request, source)
            _assert_scope_permission(request, source)
        return tuple(
            sorted(
                sources,
                key=lambda item: (
                    SOURCE_PRIORITY_RANK[item.source_type],
                    item.scope_kind.value,
                    item.scope_id,
                    item.source_ref,
                ),
            )
        )

    def _resolve_constraints(
        self,
        sources: tuple[ContextSourceSnapshot, ...],
    ) -> tuple[
        dict[str, Any],
        list[dict[str, Any]],
        list[dict[str, Any]],
        list[dict[str, Any]],
    ]:
        grouped: dict[tuple[str, str], list[_ConstraintCandidate]] = defaultdict(list)
        inactive: list[dict[str, Any]] = []
        for source in sources:
            for constraint in source.constraints:
                if not constraint.active:
                    inactive.append(
                        {
                            "constraint": constraint.node14_payload(source.source_type),
                            "source_hash": source.content_hash,
                            "source_ref": source.source_ref,
                        }
                    )
                    continue
                candidate = _ConstraintCandidate(source=source, constraint=constraint)
                grouped[candidate.group_key].append(candidate)

        effective: list[dict[str, Any]] = []
        provenance: list[dict[str, Any]] = []
        shadowed: list[dict[str, Any]] = []
        conflicts: list[ContextConflict] = []
        for group_key in sorted(grouped):
            group = grouped[group_key]
            best_source_rank = min(
                SOURCE_PRIORITY_RANK[item.source.source_type] for item in group
            )
            source_winners = [
                item
                for item in group
                if SOURCE_PRIORITY_RANK[item.source.source_type] == best_source_rank
            ]
            max_priority = max(item.constraint.priority for item in source_winners)
            priority_winners = [
                item
                for item in source_winners
                if item.constraint.priority == max_priority
            ]
            parameter_fingerprints = tuple(
                sorted({item.parameters_fingerprint for item in priority_winners})
            )
            if len(parameter_fingerprints) > 1:
                conflicts.append(
                    ContextConflict(
                        key=f"{group_key[0]}:{sha256_json(group_key[1])}",
                        channel="constraint",
                        source_type=priority_winners[0].source.source_type.value,
                        source_refs=tuple(
                            sorted(item.source.source_ref for item in priority_winners)
                        ),
                        fingerprints=parameter_fingerprints,
                        constraint_ids=tuple(
                            sorted(
                                str(item.constraint.constraint_id)
                                for item in priority_winners
                            )
                        ),
                    )
                )
                continue
            strongest_rank = max(
                _SEVERITY_RANK[item.constraint.strength]
                for item in priority_winners
            )
            strongest = sorted(
                (
                    item
                    for item in priority_winners
                    if _SEVERITY_RANK[item.constraint.strength]
                    == strongest_rank
                ),
                key=lambda item: (
                    str(item.constraint.constraint_id),
                    item.source.source_ref,
                ),
            )
            chosen = strongest[0]
            effective.append(
                chosen.constraint.node14_payload(chosen.source.source_type)
            )
            provenance.append(
                {
                    "constraint_id": str(chosen.constraint.constraint_id),
                    "equivalent_winner_ids": sorted(
                        str(item.constraint.constraint_id) for item in strongest
                    ),
                    "source_hashes": [item.source.content_hash for item in strongest],
                    "source_refs": [item.source.source_ref for item in strongest],
                }
            )
            winner_ids = {item.constraint.constraint_id for item in strongest}
            for item in group:
                if item.constraint.constraint_id in winner_ids:
                    continue
                reason = _shadow_reason(
                    item,
                    best_source_rank=best_source_rank,
                    max_priority=max_priority,
                    strongest_rank=strongest_rank,
                    chosen=chosen,
                )
                shadowed.append(
                    {
                        "constraint": item.constraint.node14_payload(
                            item.source.source_type
                        ),
                        "reason": reason,
                        "source_hash": item.source.content_hash,
                        "source_ref": item.source.source_ref,
                        "winner_constraint_id": str(chosen.constraint.constraint_id),
                    }
                )
        if conflicts:
            raise ContextConflictError(tuple(conflicts))
        effective.sort(key=lambda item: item["id"])
        provenance.sort(key=lambda item: item["constraint_id"])
        shadowed.sort(key=lambda item: item["constraint"]["id"])
        inactive.sort(key=lambda item: item["constraint"]["id"])
        return (
            {
                "constraints": effective,
                "schema_version": "lumi.constraint-set/1.0",
            },
            provenance,
            shadowed,
            inactive,
        )

    def _resolve_facts(
        self,
        sources: tuple[ContextSourceSnapshot, ...],
        channel: ContextFactChannel,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        candidates: list[_FactCandidate] = []
        for source in sources:
            for item in source.facts:
                if item.channel is channel:
                    candidates.append(
                        _FactCandidate(
                            key=item.key,
                            channel=f"fact:{channel.value}",
                            source=source,
                            payload=item.canonical_payload(),
                        )
                    )
        return _resolve_facts(candidates)


def _shadow_reason(
    item: _ConstraintCandidate,
    *,
    best_source_rank: int,
    max_priority: int,
    strongest_rank: int,
    chosen: _ConstraintCandidate,
) -> str:
    source_rank = SOURCE_PRIORITY_RANK[item.source.source_type]
    if source_rank != best_source_rank:
        return "lower_source_priority"
    if item.constraint.priority != max_priority:
        return "lower_constraint_priority"
    if _SEVERITY_RANK[item.constraint.strength] != strongest_rank:
        return "weaker_severity"
    if item.parameters_fingerprint == chosen.parameters_fingerprint:
        return "equivalent_duplicate"
    return "shadowed"


def _resolve_facts(
    candidates: Iterable[_FactCandidate],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, list[_FactCandidate]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate.key].append(candidate)

    effective: list[dict[str, Any]] = []
    shadowed: list[dict[str, Any]] = []
    conflicts: list[ContextConflict] = []
    for key in sorted(grouped):
        items = sorted(
            grouped[key],
            key=lambda item: (
                SOURCE_PRIORITY_RANK[item.source.source_type],
                item.source.source_ref,
            ),
        )
        winner_rank = SOURCE_PRIORITY_RANK[items[0].source.source_type]
        top = [
            item
            for item in items
            if SOURCE_PRIORITY_RANK[item.source.source_type] == winner_rank
        ]
        fingerprints = tuple(sorted({item.fingerprint for item in top}))
        if len(fingerprints) > 1:
            conflicts.append(
                ContextConflict(
                    key=key,
                    channel=items[0].channel,
                    source_type=items[0].source.source_type.value,
                    source_refs=tuple(item.source.source_ref for item in top),
                    fingerprints=fingerprints,
                )
            )
            continue
        winner = top[0]
        provenance = tuple(item.source.source_ref for item in top)
        effective.append(
            {
                **winner.payload,
                "source_hashes": [item.source.content_hash for item in top],
                "source_refs": list(provenance),
                "source_type": winner.source.source_type.value,
            }
        )
        for item in items[len(top):]:
            shadowed.append(
                {
                    "key": key,
                    "payload": item.payload,
                    "reason": "lower_source_priority",
                    "source_hash": item.source.content_hash,
                    "source_ref": item.source.source_ref,
                    "source_type": item.source.source_type.value,
                    "winner_source_refs": list(provenance),
                    "winner_source_type": winner.source.source_type.value,
                }
            )
    if conflicts:
        raise ContextConflictError(tuple(conflicts))
    return effective, shadowed


def _assert_scope_matches(
    request: ContextCompileRequest,
    source: ContextSourceSnapshot,
) -> None:
    expected: str | None
    if source.scope_kind is ContextScopeKind.ORGANIZATION:
        expected = str(request.organization_id)
    elif source.scope_kind is ContextScopeKind.PROJECT:
        expected = str(request.project_id)
    elif source.scope_kind is ContextScopeKind.BRAND:
        expected = request.brand_id
    elif source.scope_kind is ContextScopeKind.USER:
        expected = request.user_id
    else:
        expected = str(request.task_id) if request.task_id else None
    if expected is None or source.scope_id != expected:
        raise ContextSourceValidationError(
            f"CONTEXT_SOURCE_SCOPE_MISMATCH:{source.source_ref}"
        )


def _assert_scope_permission(
    request: ContextCompileRequest,
    source: ContextSourceSnapshot,
) -> None:
    if source.source_type is ContextSourceType.SAFETY_SYSTEM:
        return
    if source.scope_kind is ContextScopeKind.TASK:
        return
    broad = source.scope_kind.value
    exact = f"{broad}:{source.scope_id}"
    allowed = set(request.memory_read_scopes)
    if broad not in allowed and exact not in allowed:
        raise ContextSourcePermissionError(
            f"CONTEXT_SOURCE_PERMISSION_DENIED:{source.source_ref}"
        )


def _required_memory_scopes(
    sources: tuple[ContextSourceSnapshot, ...],
) -> tuple[str, ...]:
    values: list[str] = []
    for source in sources:
        if source.source_type is ContextSourceType.SAFETY_SYSTEM:
            continue
        if source.scope_kind is ContextScopeKind.TASK:
            continue
        values.append(f"{source.scope_kind.value}:{source.scope_id}")
    return tuple(dict.fromkeys(values))

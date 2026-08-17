from __future__ import annotations

import hashlib

from lumi_agent_runtime.deep_runtime.contracts import (
    MaterializedSkill,
    PinnedContextBundle,
    ResolvedAgentConfig,
)

from .contracts import (
    ContextItem,
    ContextKind,
    ContextLayer,
    ContextRequest,
    ContextSourceRef,
    InstructionAuthority,
    TrustLevel,
)
from .errors import ContextIdentityError, ContextIntegrityError


def frozen_task_context_item(
    *,
    request: ContextRequest,
    bundle: PinnedContextBundle,
) -> ContextItem:
    _validate_bundle_identity(request=request, bundle=bundle)
    content_hash = hashlib.sha256(
        bundle.task_context.encode("utf-8")
    ).hexdigest()
    return ContextItem(
        item_id="frozen-task-context",
        layer=ContextLayer.L3_TASK,
        kind=ContextKind.FROZEN_TASK_CONTEXT,
        content=bundle.task_context,
        source=ContextSourceRef(
            source_ref=bundle.context_bundle_ref,
            source_type="context-bundle",
            source_id="task-context",
            version=bundle.version,
            content_hash=content_hash,
        ),
        trust=TrustLevel.TRUSTED_PROJECT_DATA,
        instruction_authority=InstructionAuthority.NONE,
        priority=1000,
        pinned=False,
        required=True,
        compressible=True,
        metadata={
            "base_context_bundle_hash": bundle.content_hash,
            "source_refs": list(bundle.source_refs),
        },
    )


def dependency_versions(
    *,
    bundle: PinnedContextBundle,
    agent: ResolvedAgentConfig,
    skills: tuple[MaterializedSkill, ...],
) -> tuple[str, ...]:
    if not agent.content_hash:
        raise ContextIntegrityError("CONTEXT_AGENT_CONTENT_HASH_REQUIRED")
    values = {
        (
            f"context-bundle:{bundle.context_bundle_ref}@{bundle.version}"
            f"#{bundle.content_hash}"
        ),
        (
            f"agent:{agent.identity}#{agent.content_hash}"
        ),
    }
    for skill in skills:
        values.add(
            f"skill:{skill.skill_id}@{skill.exact_version}"
            f"#{skill.content_hash}"
        )
    return tuple(sorted(values))


def validate_exact_runtime_identity(
    *,
    request: ContextRequest,
    bundle: PinnedContextBundle,
    agent: ResolvedAgentConfig,
) -> None:
    _validate_bundle_identity(request=request, bundle=bundle)
    if agent.identity != request.agent_ref:
        raise ContextIdentityError("CONTEXT_AGENT_IDENTITY_MISMATCH")


def _validate_bundle_identity(
    *,
    request: ContextRequest,
    bundle: PinnedContextBundle,
) -> None:
    if bundle.context_bundle_ref != request.context_bundle_ref:
        raise ContextIdentityError("CONTEXT_BUNDLE_IDENTITY_MISMATCH")
    if not bundle.content_hash or len(bundle.content_hash) != 64:
        raise ContextIntegrityError("CONTEXT_BUNDLE_HASH_INVALID")

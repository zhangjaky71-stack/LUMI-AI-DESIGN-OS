from __future__ import annotations

import json

from lumi_agent_runtime.deep_runtime.contracts import (
    DeepAgentInvocationContext,
    PinnedContextBundle,
)

from .contracts import CompiledContextBundle, bundle_content_hash
from .errors import ContextBundleIntegrityError, ContextSourcePermissionError
from .store import ContextBundleStore


class ContextBundleProviderAdapter:
    """NODE-29 ContextBundleProvider implementation backed by NODE-32 bundles."""

    def __init__(self, store: ContextBundleStore) -> None:
        self.store = store

    async def load(
        self,
        *,
        context_bundle_ref: str,
        context: DeepAgentInvocationContext,
    ) -> PinnedContextBundle:
        bundle = await self.store.get(context_bundle_ref)
        expected_hash = bundle_content_hash(
            version=bundle.version,
            pinned_constraints=bundle.pinned_constraints,
            task_context=bundle.task_context,
            source_refs=bundle.source_refs,
        )
        if expected_hash != bundle.content_hash:
            raise ContextBundleIntegrityError("CONTEXT_BUNDLE_HASH_MISMATCH")
        expected_ref = (
            f"context-bundle://{bundle.organization_id}/"
            f"{bundle.project_id}/{bundle.content_hash}"
        )
        if bundle.context_bundle_ref != expected_ref:
            raise ContextBundleIntegrityError("CONTEXT_BUNDLE_REF_MISMATCH")
        _assert_record_metadata(bundle)
        _assert_runtime_identity(bundle, context)
        _assert_runtime_permissions(bundle, context)
        return PinnedContextBundle(
            context_bundle_ref=bundle.context_bundle_ref,
            version=bundle.version,
            pinned_constraints=bundle.pinned_constraints,
            task_context=bundle.task_context,
            source_refs=bundle.source_refs,
            content_hash=bundle.content_hash,
        )


def _assert_runtime_identity(
    bundle: CompiledContextBundle,
    context: DeepAgentInvocationContext,
) -> None:
    if bundle.organization_id != context.organization_id:
        raise ContextBundleIntegrityError("CONTEXT_BUNDLE_ORGANIZATION_MISMATCH")
    if bundle.project_id != context.project_id:
        raise ContextBundleIntegrityError("CONTEXT_BUNDLE_PROJECT_MISMATCH")
    if bundle.task_id is not None and bundle.task_id != context.task_id:
        raise ContextBundleIntegrityError("CONTEXT_BUNDLE_TASK_MISMATCH")


def _assert_runtime_permissions(
    bundle: CompiledContextBundle,
    context: DeepAgentInvocationContext,
) -> None:
    allowed = set(context.permissions.memory_read_scopes)
    for required in bundle.required_memory_scopes:
        broad = required.split(":", 1)[0]
        if required not in allowed and broad not in allowed:
            raise ContextSourcePermissionError(
                f"CONTEXT_BUNDLE_PERMISSION_REVOKED:{required}"
            )


def _assert_record_metadata(bundle: CompiledContextBundle) -> None:
    try:
        payload = json.loads(bundle.task_context)
    except (TypeError, ValueError) as exc:
        raise ContextBundleIntegrityError(
            "CONTEXT_BUNDLE_TASK_CONTEXT_INVALID"
        ) from exc
    expected = {
        "organization_id": str(bundle.organization_id),
        "project_id": str(bundle.project_id),
        "task_id": str(bundle.task_id) if bundle.task_id else None,
        "brand_id": bundle.brand_id,
        "user_id": bundle.user_id,
        "required_memory_scopes": list(bundle.required_memory_scopes),
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ContextBundleIntegrityError(
                f"CONTEXT_BUNDLE_METADATA_MISMATCH:{key}"
            )
    provenance = payload.get("source_provenance")
    expected_provenance = [
        {"content_hash": digest, "source_ref": ref}
        for ref, digest in zip(bundle.source_refs, bundle.source_hashes, strict=True)
    ]
    if provenance != expected_provenance:
        raise ContextBundleIntegrityError(
            "CONTEXT_BUNDLE_SOURCE_PROVENANCE_MISMATCH"
        )

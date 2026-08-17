from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from lumi_agent_runtime.deep_runtime.contracts import (
    MaterializedSkill,
    PinnedContextBundle,
    ResolvedAgentConfig,
)

from .budget import (
    TokenCounter,
    conservative_token_estimate,
    layer_caps,
    with_token_estimate,
)
from .bundle_source import (
    dependency_versions,
    frozen_task_context_item,
    validate_exact_runtime_identity,
)
from .cache import InMemoryContextCache
from .compression import compress_item
from .contracts import (
    ContextItem,
    ContextLayer,
    ContextManifest,
    ContextRequest,
    stable_hash,
)
from .errors import ContextBudgetError, ContextSourceError
from .render import render_context
from .retrieval import rank_candidates
from .safety import inspect_context_item
from .source import ContextRetrievalSource, NullContextRetrievalSource


class ContextEngine:
    """Build a bounded runtime data view without mutating NODE-32 bundles."""

    def __init__(
        self,
        *,
        source: ContextRetrievalSource | None = None,
        cache: InMemoryContextCache | None = None,
        token_counter: TokenCounter = conservative_token_estimate,
    ) -> None:
        self.source = source or NullContextRetrievalSource()
        self.cache = cache or InMemoryContextCache()
        self.token_counter = token_counter

    async def build(
        self,
        *,
        request: ContextRequest,
        bundle: PinnedContextBundle,
        agent: ResolvedAgentConfig,
        skills: tuple[MaterializedSkill, ...],
    ) -> ContextManifest:
        validate_exact_runtime_identity(
            request=request,
            bundle=bundle,
            agent=agent,
        )
        base = frozen_task_context_item(request=request, bundle=bundle)
        candidates = await self.source.search(request)
        retrieved = rank_candidates(candidates, request=request)

        raw = (base, *retrieved)
        normalized = tuple(self._normalize(item) for item in raw)
        source_versions = self._source_versions(
            normalized=normalized,
            dependencies=dependency_versions(
                bundle=bundle,
                agent=agent,
                skills=skills,
            ),
        )
        cache_key = stable_hash(
            {
                "request_hash": request.semantic_hash,
                "source_versions": list(source_versions),
                "retrieval_fingerprint": [
                    {
                        "source": item.source.version_key,
                        "priority": item.priority,
                        "relevance": round(item.relevance_score, 8),
                        "freshness": round(item.freshness_score, 8),
                    }
                    for item in normalized
                ],
            }
        )
        cached = self.cache.get(
            cache_key,
            source_versions=source_versions,
        )
        if cached is not None:
            return cached

        manifest = self._assemble(
            request=request,
            bundle=bundle,
            items=normalized,
            source_versions=source_versions,
            cache_key=cache_key,
        )
        self.cache.put(
            cache_key,
            project_id=str(request.project_id),
            manifest=manifest,
        )
        return manifest

    def _normalize(self, item: ContextItem) -> ContextItem:
        inspected = inspect_context_item(item)
        return with_token_estimate(inspected, self.token_counter)

    def _assemble(
        self,
        *,
        request: ContextRequest,
        bundle: PinnedContextBundle,
        items: tuple[ContextItem, ...],
        source_versions: tuple[str, ...],
        cache_key: str,
    ) -> ContextManifest:
        unique = _deduplicate(items)
        grouped: dict[ContextLayer, list[ContextItem]] = defaultdict(list)
        for item in unique:
            grouped[item.layer].append(item)
        for values in grouped.values():
            values.sort(key=_selection_key, reverse=True)

        caps = layer_caps(request)
        policies = {item.layer: item for item in request.layer_budgets}
        selected: list[ContextItem] = []
        dropped = 0
        for layer in ContextLayer:
            policy = policies.get(layer)
            if policy is None:
                dropped += len(grouped.get(layer, []))
                continue
            values = grouped.get(layer, [])
            if policy.required and not values:
                raise ContextSourceError(
                    f"CONTEXT_REQUIRED_LAYER_EMPTY:{layer.value}"
                )
            used = 0
            for item in values:
                remaining_layer = caps[layer] - used
                if remaining_layer <= 0:
                    dropped += 1
                    continue
                candidate = item
                if candidate.token_estimate > remaining_layer:
                    candidate = compress_item(
                        candidate,
                        max_tokens=remaining_layer,
                        counter=self.token_counter,
                    )
                if not candidate.content or candidate.token_estimate > remaining_layer:
                    if item.required:
                        raise ContextBudgetError(
                            f"CONTEXT_REQUIRED_ITEM_TOO_LARGE:{item.item_id}"
                        )
                    dropped += 1
                    continue
                selected.append(candidate)
                used += candidate.token_estimate

        _assert_required_items(unique, tuple(selected))
        _assert_required_sources(request, tuple(selected))
        selected_tuple, final_rendered, final_tokens, final_drops = self._fit_final(
            request=request,
            selected=tuple(selected),
        )
        dropped += final_drops
        warnings = _warnings(
            selected=selected_tuple,
            dropped=dropped,
        )
        return ContextManifest(
            organization_id=request.organization_id,
            project_id=request.project_id,
            agent_run_id=request.agent_run_id,
            task_id=request.task_id,
            agent_ref=request.agent_ref,
            context_bundle_ref=bundle.context_bundle_ref,
            context_bundle_hash=bundle.content_hash,
            request_hash=request.semantic_hash,
            items=selected_tuple,
            total_tokens=final_tokens,
            max_tokens=request.dynamic_budget_tokens,
            source_versions=source_versions,
            cache_key=cache_key,
            rendered_context=final_rendered,
            warnings=warnings,
        )

    def _fit_final(
        self,
        *,
        request: ContextRequest,
        selected: tuple[ContextItem, ...],
    ) -> tuple[tuple[ContextItem, ...], str, int, int]:
        values = list(selected)
        dropped = 0
        for _ in range(max(8, len(values) * 4)):
            rendered = render_context(tuple(values))
            tokens = self.token_counter(rendered)
            if tokens <= request.dynamic_budget_tokens:
                return tuple(values), rendered, tokens, dropped

            optional = [
                (index, item)
                for index, item in enumerate(values)
                if not item.required and not item.pinned
            ]
            if optional:
                index, _ = min(
                    optional,
                    key=lambda pair: _selection_key(pair[1]),
                )
                values.pop(index)
                dropped += 1
                continue

            compressible = [
                (index, item)
                for index, item in enumerate(values)
                if item.compressible and item.token_estimate > 1
            ]
            if not compressible:
                break
            index, item = max(
                compressible,
                key=lambda pair: pair[1].token_estimate,
            )
            excess = tokens - request.dynamic_budget_tokens
            target = max(1, item.token_estimate - excess - 16)
            compressed = compress_item(
                item,
                max_tokens=target,
                counter=self.token_counter,
            )
            if (
                not compressed.content
                or compressed.token_estimate >= item.token_estimate
            ):
                break
            values[index] = compressed

        raise ContextBudgetError("CONTEXT_FINAL_RENDER_BUDGET_EXCEEDED")

    @staticmethod
    def _source_versions(
        *,
        normalized: tuple[ContextItem, ...],
        dependencies: tuple[str, ...],
    ) -> tuple[str, ...]:
        values = set(dependencies)
        values.update(item.source.version_key for item in normalized)
        return tuple(sorted(values))


def _selection_key(item: ContextItem) -> tuple[int, int, int, float, float, str]:
    return (
        int(item.required),
        int(item.pinned),
        item.priority,
        item.relevance_score,
        item.freshness_score,
        item.item_id,
    )


def _deduplicate(items: tuple[ContextItem, ...]) -> tuple[ContextItem, ...]:
    seen: set[tuple[str, str, str, str]] = set()
    output: list[ContextItem] = []
    for item in items:
        identity = (
            item.source.source_type,
            item.source.source_id,
            item.source.version,
            item.source.content_hash,
        )
        if identity in seen:
            continue
        seen.add(identity)
        output.append(item)
    return tuple(output)


def _assert_required_items(
    raw: tuple[ContextItem, ...],
    selected: tuple[ContextItem, ...],
) -> None:
    selected_ids = {item.item_id for item in selected}
    missing = [
        item.item_id
        for item in raw
        if item.required and item.item_id not in selected_ids
    ]
    if missing:
        raise ContextBudgetError(
            "CONTEXT_REQUIRED_ITEM_NOT_INCLUDED:" + ",".join(sorted(missing))
        )


def _assert_required_sources(
    request: ContextRequest,
    selected: tuple[ContextItem, ...],
) -> None:
    included = {item.source.source_ref for item in selected}
    missing = set(request.required_source_refs) - included
    if missing:
        raise ContextBudgetError(
            "CONTEXT_REQUIRED_SOURCE_NOT_INCLUDED:"
            + ",".join(sorted(missing))
        )


def _warnings(
    *,
    selected: tuple[ContextItem, ...],
    dropped: int,
) -> tuple[str, ...]:
    values: list[str] = []
    if dropped:
        values.append("CONTEXT_ITEMS_DROPPED_BY_BUDGET_OR_POLICY")
    if any(item.metadata.get("compressed") for item in selected):
        values.append("CONTEXT_ITEMS_COMPRESSED")
    if any(
        item.metadata.get("prompt_injection_suspected")
        for item in selected
    ):
        values.append("CONTEXT_PROMPT_INJECTION_SUSPECTED")
    if any(item.metadata.get("secret_shape_suspected") for item in selected):
        values.append("CONTEXT_SECRET_SHAPE_SUSPECTED")
    return tuple(values)

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import replace
from typing import Iterable

from .budget import TokenCounter, conservative_token_estimate, layer_caps, with_token_estimate
from .cache import InMemoryContextCache
from .compression import compress_item
from .contracts import (
    ContextItem,
    ContextLayer,
    ContextManifest,
    ContextRequest,
)
from .errors import ContextBudgetError, ContextSourceError
from .retrieval import rank_candidates
from .safety import inspect_untrusted
from .source import ContextSourcePort


class ContextBuilder:
    def __init__(
        self,
        *,
        source: ContextSourcePort,
        cache: InMemoryContextCache | None = None,
        token_counter: TokenCounter = conservative_token_estimate,
    ) -> None:
        self.source = source
        self.cache = cache or InMemoryContextCache()
        self.token_counter = token_counter

    async def build(self, request: ContextRequest) -> ContextManifest:
        system = await self.source.load_system(request)
        project = await self.source.load_project(request)
        agent = await self.source.load_agent(request)
        task = await self.source.load_task(request)
        candidates = await self.source.search(request)
        retrieved = rank_candidates(
            candidates,
            organization_id=str(request.organization_id),
            project_id=str(request.project_id),
            limit=request.retrieval_limit,
        )
        raw = (*system, *project, *agent, *task, *retrieved)
        normalized = tuple(self._normalize(item) for item in raw)
        source_versions = _source_versions(normalized)
        cache_key = _cache_key(request.semantic_hash, source_versions)
        cached = self.cache.get(cache_key, source_versions=source_versions)
        if cached is not None:
            return cached

        manifest = self._assemble(
            request,
            normalized,
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
        inspected = inspect_untrusted(item)
        return with_token_estimate(inspected, self.token_counter)

    def _assemble(
        self,
        request: ContextRequest,
        items: tuple[ContextItem, ...],
        *,
        source_versions: tuple[str, ...],
        cache_key: str,
    ) -> ContextManifest:
        unique = _deduplicate(items)
        grouped: dict[ContextLayer, list[ContextItem]] = defaultdict(list)
        for item in unique:
            grouped[item.layer].append(item)
        for values in grouped.values():
            values.sort(
                key=lambda item: (
                    item.source.source_id in request.required_source_ids,
                    item.priority,
                    item.relevance_score,
                    item.source.version,
                    item.item_id,
                ),
                reverse=True,
            )

        caps = layer_caps(request)
        budget_by_layer = {budget.layer: budget for budget in request.layer_budgets}
        selected: list[ContextItem] = []
        warnings: list[str] = []
        total = 0
        included_sources: set[str] = set()

        for layer in ContextLayer:
            cap = min(caps.get(layer, 0), request.context_budget_tokens - total)
            policy = budget_by_layer.get(layer)
            values = grouped.get(layer, [])
            if policy is None:
                continue
            if policy.required and not values:
                raise ContextSourceError(f"CONTEXT_REQUIRED_LAYER_EMPTY:{layer.value}")
            used = 0
            for item in values:
                remaining_layer = cap - used
                remaining_total = request.context_budget_tokens - total
                remaining = min(remaining_layer, remaining_total)
                if remaining <= 0:
                    break
                candidate = item
                if candidate.token_estimate > remaining:
                    candidate = compress_item(
                        candidate,
                        max_tokens=remaining,
                        counter=self.token_counter,
                    )
                if candidate.token_estimate > remaining:
                    continue
                selected.append(candidate)
                used += candidate.token_estimate
                total += candidate.token_estimate
                included_sources.add(candidate.source.source_id)

            if policy.required and not any(item.layer == layer for item in selected):
                raise ContextBudgetError(
                    f"CONTEXT_REQUIRED_LAYER_BUDGET_EXHAUSTED:{layer.value}"
                )

        missing_required = set(request.required_source_ids) - included_sources
        if missing_required:
            raise ContextBudgetError(
                "CONTEXT_REQUIRED_SOURCE_NOT_INCLUDED:"
                + ",".join(sorted(missing_required))
            )
        if total > request.context_budget_tokens:
            raise ContextBudgetError("CONTEXT_TOTAL_BUDGET_EXCEEDED")
        if len(selected) < len(unique):
            warnings.append("CONTEXT_ITEMS_DROPPED_BY_BUDGET")

        return ContextManifest(
            request_hash=request.semantic_hash,
            items=tuple(selected),
            total_tokens=total,
            max_tokens=request.context_budget_tokens,
            source_versions=source_versions,
            cache_key=cache_key,
            warnings=tuple(warnings),
        )


def _deduplicate(items: Iterable[ContextItem]) -> tuple[ContextItem, ...]:
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


def _source_versions(items: tuple[ContextItem, ...]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                f"{item.source.source_type}:{item.source.source_id}@"
                f"{item.source.version}#{item.source.content_hash}"
                for item in items
            }
        )
    )


def _cache_key(request_hash: str, source_versions: tuple[str, ...]) -> str:
    material = request_hash + "|" + "|".join(source_versions)
    return hashlib.sha256(material.encode()).hexdigest()

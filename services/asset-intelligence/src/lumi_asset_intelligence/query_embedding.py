from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from .model import AssetIndexVersion, AssetSearchRequest


class QueryEmbeddingProvider(Protocol):
    provider_id: str
    model_id: str
    model_version: str
    preprocessor_version: str
    registry_snapshot_id: str

    def embed_text(self, organization_id: str, text: str) -> tuple[float, ...]: ...


def attach_query_embedding(
    request: AssetSearchRequest,
    index: AssetIndexVersion,
    provider: QueryEmbeddingProvider,
) -> AssetSearchRequest:
    if request.scope.organization_id != index.organization_id:
        raise ValueError("QUERY_EMBEDDING_TENANT_MISMATCH")
    if provider.model_id != index.embedding_model_id:
        raise ValueError("QUERY_EMBEDDING_MODEL_MISMATCH")
    if provider.model_version != index.embedding_model_version:
        raise ValueError("QUERY_EMBEDDING_MODEL_VERSION_MISMATCH")
    if provider.preprocessor_version != index.embedding_preprocessor_version:
        raise ValueError("QUERY_EMBEDDING_PREPROCESSOR_VERSION_MISMATCH")
    if provider.registry_snapshot_id != index.registry_snapshot_id:
        raise ValueError("QUERY_EMBEDDING_REGISTRY_SNAPSHOT_MISMATCH")
    vector = provider.embed_text(request.scope.organization_id, request.query)
    if len(vector) != index.embedding_dimensions:
        raise ValueError("QUERY_EMBEDDING_DIMENSION_MISMATCH")
    return replace(request, query_embedding=vector)

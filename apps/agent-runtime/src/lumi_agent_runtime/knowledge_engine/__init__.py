from .context_source import hit_to_context_item
from .contracts import (
    IngestionState,
    KnowledgeAccessContext,
    KnowledgeChunk,
    KnowledgeCitation,
    KnowledgeDocument,
    KnowledgeHit,
    KnowledgeIngestRequest,
    KnowledgeScopeKind,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
    KnowledgeSourceType,
    SourceSection,
)
from .embedding_port import KnowledgeEmbeddingPort
from .engine import DeterministicEmbedding, KnowledgeEngine
from .extraction import (
    KnowledgeExtractionPort,
    KnowledgeExtractionResult,
    KnowledgeSourceInput,
    extract_native_then_ocr,
)
from .ingestion import KnowledgeIngestionService
from .store import GitWorkspaceKnowledgeStore, InMemoryKnowledgeStore, KnowledgeStore

__all__ = [
    "DeterministicEmbedding",
    "GitWorkspaceKnowledgeStore",
    "InMemoryKnowledgeStore",
    "IngestionState",
    "KnowledgeAccessContext",
    "KnowledgeChunk",
    "KnowledgeCitation",
    "KnowledgeDocument",
    "KnowledgeEmbeddingPort",
    "KnowledgeEngine",
    "KnowledgeExtractionPort",
    "KnowledgeExtractionResult",
    "KnowledgeHit",
    "KnowledgeIngestRequest",
    "KnowledgeIngestionService",
    "KnowledgeScopeKind",
    "KnowledgeSearchRequest",
    "KnowledgeSearchResult",
    "KnowledgeSourceInput",
    "KnowledgeSourceType",
    "KnowledgeStore",
    "SourceSection",
    "extract_native_then_ocr",
    "hit_to_context_item",
]

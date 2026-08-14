from __future__ import annotations

import hashlib
import re
from typing import Any
from uuid import UUID, uuid5

from .contracts import KnowledgeChunk, KnowledgeDocument, KnowledgeSegment

_TOKEN = re.compile(r"\S+")


def chunk_document(
    document: KnowledgeDocument,
    *,
    chunk_size_tokens: int,
    chunk_overlap_tokens: int,
    segments: tuple[KnowledgeSegment, ...] = (),
) -> tuple[KnowledgeChunk, ...]:
    if segments:
        return _chunk_segments(
            document,
            segments=segments,
            chunk_size_tokens=chunk_size_tokens,
            chunk_overlap_tokens=chunk_overlap_tokens,
        )
    return _chunk_text(
        document,
        text=document.normalized_text,
        base_locator={},
        ordinal_start=0,
        chunk_size_tokens=chunk_size_tokens,
        chunk_overlap_tokens=chunk_overlap_tokens,
    )


def _chunk_segments(
    document: KnowledgeDocument,
    *,
    segments: tuple[KnowledgeSegment, ...],
    chunk_size_tokens: int,
    chunk_overlap_tokens: int,
) -> tuple[KnowledgeChunk, ...]:
    output: list[KnowledgeChunk] = []
    ordinal = 0
    for segment_index, segment in enumerate(segments):
        locator: dict[str, Any] = {
            "segment_index": segment_index,
            **segment.metadata,
        }
        if segment.page is not None:
            locator["page"] = segment.page
        if segment.section is not None:
            locator["section"] = segment.section
        chunks = _chunk_text(
            document,
            text=segment.text,
            base_locator=locator,
            ordinal_start=ordinal,
            chunk_size_tokens=chunk_size_tokens,
            chunk_overlap_tokens=chunk_overlap_tokens,
        )
        output.extend(chunks)
        ordinal += len(chunks)
    return tuple(output)


def _chunk_text(
    document: KnowledgeDocument,
    *,
    text: str,
    base_locator: dict[str, Any],
    ordinal_start: int,
    chunk_size_tokens: int,
    chunk_overlap_tokens: int,
) -> tuple[KnowledgeChunk, ...]:
    matches = list(_TOKEN.finditer(text))
    if not matches:
        return ()
    step = chunk_size_tokens - chunk_overlap_tokens
    chunks: list[KnowledgeChunk] = []
    start_token = 0
    local_ordinal = 0
    while start_token < len(matches):
        end_token = min(start_token + chunk_size_tokens, len(matches))
        start_char = matches[start_token].start()
        end_char = matches[end_token - 1].end()
        chunk_text = text[start_char:end_char].strip()
        content_hash = hashlib.sha256(chunk_text.encode()).hexdigest()
        ordinal = ordinal_start + local_ordinal
        locator = {
            **base_locator,
            "start_char": start_char,
            "end_char": end_char,
            "start_token": start_token,
            "end_token": end_token,
        }
        chunk_id = uuid5(
            document.document_id,
            f"chunk:{ordinal}:{content_hash}:{_locator_hash(locator)}",
        )
        chunks.append(
            KnowledgeChunk(
                chunk_id=chunk_id,
                document_id=document.document_id,
                organization_id=document.organization_id,
                project_id=document.project_id,
                ordinal=ordinal,
                text=chunk_text,
                content_hash=content_hash,
                token_estimate=end_token - start_token,
                locator=locator,
                source=document.source,
                trust=document.trust,
            )
        )
        if end_token == len(matches):
            break
        local_ordinal += 1
        start_token += step
    return tuple(chunks)


def deterministic_document_id(
    namespace: UUID,
    *,
    source_type: str,
    source_id: str,
    source_version: str,
    source_hash: str,
    index_version: str = "knowledge-v1",
) -> UUID:
    return uuid5(
        namespace,
        "knowledge:"
        f"{source_type}:{source_id}:{source_version}:{source_hash}:{index_version}",
    )


def _locator_hash(locator: dict[str, Any]) -> str:
    import json

    encoded = json.dumps(
        locator,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]

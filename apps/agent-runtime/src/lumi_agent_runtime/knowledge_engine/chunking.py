from __future__ import annotations

import hashlib
import re
from uuid import UUID, uuid5

from .contracts import KnowledgeChunk, KnowledgeDocument

_TOKEN = re.compile(r"\S+")


def chunk_document(
    document: KnowledgeDocument,
    *,
    chunk_size_tokens: int,
    chunk_overlap_tokens: int,
) -> tuple[KnowledgeChunk, ...]:
    matches = list(_TOKEN.finditer(document.normalized_text))
    if not matches:
        return ()
    step = chunk_size_tokens - chunk_overlap_tokens
    chunks: list[KnowledgeChunk] = []
    ordinal = 0
    start_token = 0
    while start_token < len(matches):
        end_token = min(start_token + chunk_size_tokens, len(matches))
        start_char = matches[start_token].start()
        end_char = matches[end_token - 1].end()
        text = document.normalized_text[start_char:end_char].strip()
        content_hash = hashlib.sha256(text.encode()).hexdigest()
        chunk_id = uuid5(
            document.document_id,
            f"chunk:{ordinal}:{content_hash}",
        )
        chunks.append(
            KnowledgeChunk(
                chunk_id=chunk_id,
                document_id=document.document_id,
                organization_id=document.organization_id,
                project_id=document.project_id,
                ordinal=ordinal,
                text=text,
                content_hash=content_hash,
                token_estimate=end_token - start_token,
                locator={
                    "start_char": start_char,
                    "end_char": end_char,
                    "start_token": start_token,
                    "end_token": end_token,
                },
                source=document.source,
                trust=document.trust,
            )
        )
        if end_token == len(matches):
            break
        ordinal += 1
        start_token += step
    return tuple(chunks)


def deterministic_document_id(
    namespace: UUID,
    *,
    source_type: str,
    source_id: str,
    source_version: str,
    source_hash: str,
) -> UUID:
    return uuid5(
        namespace,
        f"knowledge:{source_type}:{source_id}:{source_version}:{source_hash}",
    )

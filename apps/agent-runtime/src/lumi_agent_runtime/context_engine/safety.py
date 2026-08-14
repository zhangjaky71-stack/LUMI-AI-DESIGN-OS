from __future__ import annotations

import re
from dataclasses import replace

from .contracts import ContextItem, TrustLevel

_INJECTION_PATTERNS = (
    re.compile(r"(?i)ignore\s+(all\s+)?previous\s+instructions"),
    re.compile(r"(?i)reveal\s+(the\s+)?system\s+prompt"),
    re.compile(r"(?i)developer\s+message"),
    re.compile(r"(?i)you\s+are\s+(chatgpt|an?\s+assistant)"),
    re.compile(r"(?i)<\/?(system|assistant|developer|tool)[^>]*>"),
    re.compile(r"(?i)authorization\s*:\s*bearer"),
    re.compile(r"(?i)api[_-]?key\s*[:=]"),
)


def inspect_untrusted(item: ContextItem) -> ContextItem:
    if item.trust != TrustLevel.UNTRUSTED_RETRIEVED:
        return item
    content = item.content.replace("\x00", "").strip()
    suspicious = any(pattern.search(content) for pattern in _INJECTION_PATTERNS)
    metadata = dict(item.metadata)
    metadata["instruction_authority"] = "none"
    metadata["prompt_injection_suspected"] = suspicious
    metadata["render_boundary"] = "untrusted-data"
    return replace(item, content=content, metadata=metadata)


def render_context_item(item: ContextItem) -> str:
    if item.trust == TrustLevel.UNTRUSTED_RETRIEVED:
        return (
            f"[UNTRUSTED_RETRIEVED_DATA source={item.source.source_type}:"
            f"{item.source.source_id}@{item.source.version}]\n"
            f"{item.content}\n[/UNTRUSTED_RETRIEVED_DATA]"
        )
    return item.content

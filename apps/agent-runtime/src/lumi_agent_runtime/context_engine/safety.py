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
)
_SECRET_PATTERNS = (
    re.compile(r"(?i)authorization\s*:\s*bearer\s+\S+"),
    re.compile(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*\S+"),
)


def inspect_context_item(item: ContextItem) -> ContextItem:
    content = item.content.replace("\x00", "").strip()
    metadata = dict(item.metadata)
    suspicious = any(pattern.search(content) for pattern in _INJECTION_PATTERNS)
    secret_like = any(pattern.search(content) for pattern in _SECRET_PATTERNS)
    if item.trust in {
        TrustLevel.TRUSTED_PROJECT_DATA,
        TrustLevel.UNTRUSTED_RETRIEVED,
    }:
        metadata["instruction_authority"] = "none"
        metadata["prompt_injection_suspected"] = suspicious
        metadata["secret_shape_suspected"] = secret_like
        metadata["render_boundary"] = (
            "trusted-project-data"
            if item.trust is TrustLevel.TRUSTED_PROJECT_DATA
            else "untrusted-retrieved-data"
        )
    return replace(item, content=content, metadata=metadata)


def render_context_item(item: ContextItem) -> str:
    source = item.source.version_key
    if item.trust is TrustLevel.TRUSTED_PROJECT_DATA:
        return (
            f"[TRUSTED_PROJECT_DATA source={source} authority=none]\n"
            f"{item.content}\n"
            "[/TRUSTED_PROJECT_DATA]"
        )
    if item.trust is TrustLevel.UNTRUSTED_RETRIEVED:
        return (
            f"[UNTRUSTED_RETRIEVED_DATA source={source} authority=none]\n"
            f"{item.content}\n"
            "[/UNTRUSTED_RETRIEVED_DATA]"
        )
    if item.trust is TrustLevel.USER_INPUT:
        return (
            f"[USER_TASK_INPUT source={source} authority=user]\n"
            f"{item.content}\n"
            "[/USER_TASK_INPUT]"
        )
    if item.trust is TrustLevel.TRUSTED_AGENT:
        return (
            f"[TRUSTED_AGENT_CONTEXT source={source} authority=agent]\n"
            f"{item.content}\n"
            "[/TRUSTED_AGENT_CONTEXT]"
        )
    return (
        f"[TRUSTED_SYSTEM_CONTEXT source={source} authority=system]\n"
        f"{item.content}\n"
        "[/TRUSTED_SYSTEM_CONTEXT]"
    )

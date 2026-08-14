from __future__ import annotations

import re
from dataclasses import replace

from .budget import TokenCounter
from .contracts import ContextItem

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。！？])\s+")


def compress_item(
    item: ContextItem,
    *,
    max_tokens: int,
    counter: TokenCounter,
) -> ContextItem:
    if max_tokens < 1:
        raise ValueError("CONTEXT_COMPRESSION_BUDGET_INVALID")
    if counter(item.content) <= max_tokens:
        return replace(item, token_estimate=counter(item.content))

    sentences = [part.strip() for part in _SENTENCE_SPLIT.split(item.content) if part.strip()]
    if not sentences:
        sentences = [item.content.strip()]
    selected: list[str] = []
    for sentence in sentences:
        candidate = " ".join((*selected, sentence)).strip()
        if counter(candidate) > max_tokens:
            break
        selected.append(sentence)
    if not selected:
        # Character clipping is a last-resort bounded fallback. Keep a conservative
        # ratio because the default token counter is intentionally conservative.
        clip = max(1, max_tokens * 2)
        text = item.content[:clip].rstrip()
    else:
        text = " ".join(selected)
    if text != item.content:
        text = text.rstrip() + " …[compressed]"
    metadata = dict(item.metadata)
    metadata["compressed"] = True
    metadata["original_token_estimate"] = counter(item.content)
    return replace(
        item,
        content=text,
        token_estimate=counter(text),
        metadata=metadata,
    )

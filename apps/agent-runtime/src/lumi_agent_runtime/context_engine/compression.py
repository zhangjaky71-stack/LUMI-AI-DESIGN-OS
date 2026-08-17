from __future__ import annotations

import re
from dataclasses import replace

from .budget import TokenCounter, with_token_estimate
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
    if not item.compressible:
        return item
    if item.token_estimate <= max_tokens:
        return item

    sentences = [
        part.strip()
        for part in _SENTENCE_SPLIT.split(item.content)
        if part.strip()
    ]
    if not sentences:
        sentences = [item.content.strip()]
    selected: list[str] = []
    for sentence in sentences:
        candidate = " ".join((*selected, sentence)).strip()
        provisional = replace(item, content=candidate)
        if with_token_estimate(provisional, counter).token_estimate > max_tokens:
            break
        selected.append(sentence)

    if selected:
        text = " ".join(selected)
    else:
        low = 1
        high = len(item.content)
        best = ""
        while low <= high:
            middle = (low + high) // 2
            candidate = item.content[:middle].rstrip()
            provisional = replace(item, content=candidate)
            tokens = with_token_estimate(provisional, counter).token_estimate
            if tokens <= max_tokens:
                best = candidate
                low = middle + 1
            else:
                high = middle - 1
        text = best

    if text and text != item.content:
        suffix = " …[compressed]"
        provisional = replace(item, content=text + suffix)
        if with_token_estimate(provisional, counter).token_estimate <= max_tokens:
            text += suffix

    metadata = dict(item.metadata)
    metadata["compressed"] = text != item.content
    metadata["original_content_hash"] = item.rendered_content_hash
    candidate = replace(item, content=text, metadata=metadata)
    return with_token_estimate(candidate, counter)

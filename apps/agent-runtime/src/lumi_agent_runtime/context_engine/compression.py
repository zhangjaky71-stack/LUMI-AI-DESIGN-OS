from __future__ import annotations

import re
from dataclasses import replace

from .budget import TokenCounter
from .contracts import ContextItem
from .safety import render_context_item

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。！？])\s+")
_COMPRESSION_MARKER = " …[compressed]"


def _rendered_tokens(item: ContextItem, counter: TokenCounter) -> int:
    return counter(render_context_item(item))


def _marked_content(content: str) -> str:
    return content.rstrip() + _COMPRESSION_MARKER


def compress_item(
    item: ContextItem,
    *,
    max_tokens: int,
    counter: TokenCounter,
) -> ContextItem:
    if max_tokens < 1:
        raise ValueError("CONTEXT_COMPRESSION_BUDGET_INVALID")

    original_token_estimate = _rendered_tokens(item, counter)
    if original_token_estimate <= max_tokens:
        return replace(item, token_estimate=original_token_estimate)

    sentences = [part.strip() for part in _SENTENCE_SPLIT.split(item.content) if part.strip()]
    if not sentences:
        sentences = [item.content.strip()]

    selected: list[str] = []
    for sentence in sentences:
        candidate_content = " ".join((*selected, sentence)).strip()
        candidate = replace(item, content=_marked_content(candidate_content))
        if _rendered_tokens(candidate, counter) > max_tokens:
            break
        selected.append(sentence)

    if selected:
        text = _marked_content(" ".join(selected))
    else:
        # Last-resort clipping still accounts for the rendered trust/source wrapper and
        # the compression marker. Binary search keeps the longest prefix that fits.
        low = 1
        high = len(item.content)
        text = ""
        while low <= high:
            midpoint = (low + high) // 2
            candidate_text = _marked_content(item.content[:midpoint])
            candidate = replace(item, content=candidate_text)
            if _rendered_tokens(candidate, counter) <= max_tokens:
                text = candidate_text
                low = midpoint + 1
            else:
                high = midpoint - 1
        if not text:
            # The layer budget cannot even hold this item's rendered envelope. Return
            # the original bounded accounting so the caller can fail closed.
            return replace(item, token_estimate=original_token_estimate)

    metadata = dict(item.metadata)
    metadata["compressed"] = True
    metadata["original_token_estimate"] = original_token_estimate
    compressed = replace(item, content=text, metadata=metadata)
    return replace(
        compressed,
        token_estimate=_rendered_tokens(compressed, counter),
    )

from __future__ import annotations

from collections import defaultdict

from .contracts import ContextItem, ContextLayer
from .safety import render_context_item


def render_context(items: tuple[ContextItem, ...]) -> str:
    grouped: dict[ContextLayer, list[ContextItem]] = defaultdict(list)
    for item in items:
        grouped[item.layer].append(item)

    sections: list[str] = []
    for layer in ContextLayer:
        values = grouped.get(layer)
        if not values:
            continue
        body = "\n\n".join(render_context_item(item) for item in values)
        sections.append(
            f"<runtime_context_layer name=\"{layer.value}\">\n"
            f"{body}\n"
            "</runtime_context_layer>"
        )
    return "\n\n".join(sections)

from __future__ import annotations

from dataclasses import dataclass

from .contracts import ContextManifest
from .safety import render_context_item


@dataclass(frozen=True, slots=True)
class RenderedContext:
    text: str
    manifest_hash: str
    total_tokens: int
    source_versions: tuple[str, ...]


def render_manifest(manifest: ContextManifest) -> RenderedContext:
    sections: list[str] = []
    current_layer: str | None = None
    for item in manifest.items:
        layer = item.layer.value
        if layer != current_layer:
            sections.append(f"\n## {layer}\n")
            current_layer = layer
        sections.append(render_context_item(item))
    return RenderedContext(
        text="\n\n".join(sections).strip(),
        manifest_hash=manifest.freeze_hash,
        total_tokens=manifest.total_tokens,
        source_versions=manifest.source_versions,
    )

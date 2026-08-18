"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { OperationDescriptor } from "@lumi/canvas-sdk";
import type { DesignDocument } from "@lumi/design-ir";

import {
  LAYER_ROW_HEIGHT,
  flattenLayerRows,
  layerLabel,
  virtualLayerWindow,
} from "@/lib/layers/model";

export function LayerTree({
  document,
  selectedIds,
  canEdit,
  onSelect,
  onCommit,
}: {
  document: DesignDocument;
  selectedIds: readonly string[];
  canEdit: boolean;
  onSelect: (id: string, additive: boolean) => void;
  onCommit: (descriptor: OperationDescriptor) => boolean;
}) {
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(() => new Set());
  const [query, setQuery] = useState("");
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(420);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const rows = useMemo(
    () => flattenLayerRows(document, collapsed, query),
    [collapsed, document, query],
  );
  const windowed = useMemo(
    () => virtualLayerWindow(rows, scrollTop, viewportHeight),
    [rows, scrollTop, viewportHeight],
  );
  const selected = useMemo(() => new Set(selectedIds), [selectedIds]);

  useEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) setViewportHeight(Math.max(LAYER_ROW_HEIGHT, entry.contentRect.height));
    });
    observer.observe(scroller);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const id = selectedIds.at(-1);
    const scroller = scrollerRef.current;
    if (!id || !scroller) return;
    const index = rows.findIndex((row) => row.id === id);
    if (index < 0) return;
    const top = index * LAYER_ROW_HEIGHT;
    const bottom = top + LAYER_ROW_HEIGHT;
    if (top < scroller.scrollTop) scroller.scrollTop = top;
    else if (bottom > scroller.scrollTop + scroller.clientHeight) {
      scroller.scrollTop = bottom - scroller.clientHeight;
    }
  }, [rows, selectedIds]);

  const toggleCollapse = useCallback((id: string) => {
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  const beginRename = useCallback((id: string) => {
    const node = document.nodes[id];
    if (!node || !canEdit || node.locked) return;
    setEditingId(id);
    setRenameValue(layerLabel(node));
  }, [canEdit, document.nodes]);

  const finishRename = useCallback(() => {
    if (!editingId) return;
    const node = document.nodes[editingId];
    const value = renameValue.trim();
    setEditingId(null);
    if (!node || !value || value === layerLabel(node)) return;
    onCommit({
      type: "SET_PROPERTY",
      targetIds: [editingId],
      payload: { property: "name", value },
      reason: "rename layer",
    });
  }, [document.nodes, editingId, onCommit, renameValue]);

  return (
    <section className="layers-panel" aria-label="Layers">
      <header className="layers-panel-header">
        <div>
          <span className="canvas-panel-eyebrow">Structure</span>
          <strong>Layers</strong>
        </div>
        <span>{rows.length}</span>
      </header>
      <label className="layers-search">
        <span className="sr-only">Search layers</span>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search name, role, kind…"
          type="search"
        />
      </label>
      <div
        className="layers-scroll"
        ref={scrollerRef}
        onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
      >
        <div className="layers-spacer" style={{ height: windowed.totalHeight }}>
          <div className="layers-window" style={{ transform: `translateY(${windowed.offset}px)` }}>
            {windowed.rows.map((row) => {
              const isSelected = selected.has(row.id);
              const isEditing = editingId === row.id;
              return (
                <div
                  className={`layer-row${isSelected ? " is-selected" : ""}${row.matched ? " is-match" : ""}`}
                  key={row.id}
                  style={{ paddingLeft: 6 + row.depth * 14 }}
                  data-node-id={row.id}
                >
                  <button
                    className="layer-expand"
                    type="button"
                    aria-label={row.expandable ? (row.expanded ? "Collapse layer" : "Expand layer") : "Leaf layer"}
                    disabled={!row.expandable}
                    onClick={() => toggleCollapse(row.id)}
                  >
                    {row.expandable ? (row.expanded ? "▾" : "▸") : "·"}
                  </button>
                  <button
                    className="layer-main"
                    type="button"
                    aria-pressed={isSelected}
                    onClick={(event) => onSelect(row.id, event.shiftKey || event.metaKey || event.ctrlKey)}
                    onDoubleClick={() => beginRename(row.id)}
                  >
                    <span className={`layer-kind kind-${row.node.kind.toLowerCase()}`}>{kindGlyph(row.node.kind)}</span>
                    {isEditing ? (
                      <input
                        autoFocus
                        value={renameValue}
                        onChange={(event) => setRenameValue(event.target.value)}
                        onClick={(event) => event.stopPropagation()}
                        onBlur={finishRename}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") finishRename();
                          if (event.key === "Escape") setEditingId(null);
                        }}
                      />
                    ) : (
                      <span className="layer-label">{layerLabel(row.node)}</span>
                    )}
                    {row.node.role ? <small>{row.node.role}</small> : null}
                  </button>
                  <button
                    className="layer-icon-action"
                    type="button"
                    title={row.node.visible === false ? "Show layer" : "Hide layer"}
                    disabled={!canEdit || row.node.locked === true}
                    onClick={() => onCommit({
                      type: "SET_PROPERTY",
                      targetIds: [row.id],
                      payload: { property: "visible", value: row.node.visible === false },
                      reason: row.node.visible === false ? "show layer" : "hide layer",
                    })}
                  >
                    {row.node.visible === false ? "○" : "◉"}
                  </button>
                  <button
                    className="layer-icon-action"
                    type="button"
                    title={row.node.locked ? "Unlock layer" : "Lock layer"}
                    disabled={!canEdit || row.node.metadata?.source_kind === "page"}
                    onClick={() => onCommit({
                      type: "SET_PROPERTY",
                      targetIds: [row.id],
                      payload: { property: "locked", value: row.node.locked !== true },
                      reason: row.node.locked ? "unlock layer" : "lock layer",
                    })}
                  >
                    {row.node.locked ? "▣" : "□"}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      </div>
      <footer className="layers-panel-footer">
        <span>{selectedIds.length ? `${selectedIds.length} selected` : "Select a layer or canvas node"}</span>
        <span>10k-safe virtual rows</span>
      </footer>
    </section>
  );
}

function kindGlyph(kind: string): string {
  if (kind === "FRAME") return "F";
  if (kind === "GROUP") return "G";
  if (kind === "TEXT") return "T";
  if (kind === "IMAGE") return "I";
  if (kind === "VECTOR_PATH") return "V";
  if (kind === "SHAPE") return "S";
  return "•";
}
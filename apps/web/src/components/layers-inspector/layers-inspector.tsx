"use client";

import { useMemo, useState, type MouseEvent } from "react";
import type { ProjectReference } from "@/lib/projects/types";
import type {
  CanvasEditorRef,
  CanvasEditorState,
  InspectorTransformPatch,
  LayerTreeNode,
} from "@/lib/layers-inspector/types";
import styles from "./layers-inspector.module.css";

interface Props {
  readonly state: CanvasEditorState | null;
  readonly editorRef: CanvasEditorRef;
  readonly brandName: string | null;
  readonly references: readonly ProjectReference[];
  readonly selectedReferenceIds: readonly string[];
  readonly onToggleReference: (assetId: string) => void;
  readonly onAIEdit: (nodeIds: readonly string[]) => void;
}

type Tab = "layers" | "design" | "context";

function filteredTree(nodes: readonly LayerTreeNode[], query: string): LayerTreeNode[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return [...nodes];
  return nodes.flatMap((node) => {
    const children = filteredTree(node.children, normalized);
    const match = `${node.name} ${node.id} ${node.kind}`.toLowerCase().includes(normalized);
    return match || children.length ? [{ ...node, children }] : [];
  });
}

function kindGlyph(kind: string): string {
  if (kind === "FRAME") return "▣";
  if (kind === "GROUP") return "◇";
  if (kind === "TEXT") return "T";
  if (kind === "IMAGE") return "▧";
  if (kind === "SHAPE") return "●";
  if (kind === "VIDEO") return "▶";
  return "◆";
}

function LayerRow({
  node,
  editorRef,
  collapsed,
  setCollapsed,
  editingId,
  setEditingId,
}: Readonly<{
  node: LayerTreeNode;
  editorRef: CanvasEditorRef;
  collapsed: ReadonlySet<string>;
  setCollapsed: (value: Set<string>) => void;
  editingId: string | null;
  setEditingId: (value: string | null) => void;
}>) {
  const isCollapsed = collapsed.has(node.id);
  const select = (event: MouseEvent<HTMLButtonElement>) => {
    const api = editorRef.current;
    if (!api) return;
    if (event.shiftKey) {
      const current = new Set<string>();
      document.querySelectorAll<HTMLElement>("[data-layer-selected='true']").forEach((element) => {
        if (element.dataset.layerId) current.add(element.dataset.layerId);
      });
      if (current.has(node.id)) current.delete(node.id);
      else current.add(node.id);
      api.select([...current], node.id);
    } else {
      api.select([node.id], node.id);
    }
  };

  return (
    <div className={styles.layerBranch}>
      <div
        className={styles.layerRow}
        data-layer-id={node.id}
        data-layer-selected={node.selected}
        data-primary={node.primary}
        style={{ paddingLeft: `${8 + node.depth * 14}px` }}
      >
        <button
          type="button"
          className={styles.disclosure}
          disabled={!node.children.length}
          aria-label={`${node.name} ${isCollapsed ? "展开" : "折叠"}`}
          onClick={() => {
            const next = new Set(collapsed);
            if (isCollapsed) next.delete(node.id);
            else next.add(node.id);
            setCollapsed(next);
          }}
        >
          {node.children.length ? (isCollapsed ? "›" : "⌄") : "·"}
        </button>
        <button type="button" className={styles.layerMain} onClick={select} title={node.id}>
          <span className={styles.kindGlyph}>{kindGlyph(node.kind)}</span>
          {editingId === node.id ? (
            <input
              autoFocus
              defaultValue={node.name}
              aria-label={`${node.name} 重命名`}
              onClick={(event) => event.stopPropagation()}
              onBlur={(event) => {
                editorRef.current?.renameNode(node.id, event.currentTarget.value);
                setEditingId(null);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") event.currentTarget.blur();
                if (event.key === "Escape") setEditingId(null);
              }}
            />
          ) : (
            <span className={styles.layerName} onDoubleClick={() => setEditingId(node.id)}>{node.name}</span>
          )}
        </button>
        <button
          type="button"
          className={styles.iconButton}
          aria-label={`${node.name} ${node.visible ? "隐藏" : "显示"}`}
          title={node.effective_visible ? "Visible" : node.visible ? "Hidden by parent" : "Hidden"}
          onClick={() => editorRef.current?.setVisibility([node.id], !node.visible)}
        >
          {node.visible ? (node.effective_visible ? "◉" : "◌") : "○"}
        </button>
        <button
          type="button"
          className={styles.iconButton}
          aria-label={`${node.name} ${node.locked ? "解锁" : "锁定"}`}
          title={node.effective_locked ? "Locked" : "Unlocked"}
          onClick={() => editorRef.current?.setLocked([node.id], !node.locked)}
        >
          {node.locked ? "▣" : node.effective_locked ? "▧" : "□"}
        </button>
      </div>
      {!isCollapsed ? node.children.map((child) => (
        <LayerRow
          key={child.id}
          node={child}
          editorRef={editorRef}
          collapsed={collapsed}
          setCollapsed={setCollapsed}
          editingId={editingId}
          setEditingId={setEditingId}
        />
      )) : null}
    </div>
  );
}

function NumberField({
  label,
  value,
  step = 1,
  min,
  max,
  version,
  onCommit,
}: Readonly<{
  label: string;
  value: number;
  step?: number;
  min?: number;
  max?: number;
  version: number;
  onCommit: (value: number) => void;
}>) {
  return (
    <label className={styles.field}>
      <span>{label}</span>
      <input
        key={`${version}:${label}:${value}`}
        type="number"
        defaultValue={Number.isInteger(value) ? value : Number(value.toFixed(2))}
        step={step}
        min={min}
        max={max}
        onBlur={(event) => {
          const next = Number(event.currentTarget.value);
          if (Number.isFinite(next) && next !== value) onCommit(next);
        }}
      />
    </label>
  );
}

function DesignInspector({
  state,
  editorRef,
  onAIEdit,
}: Readonly<{
  state: CanvasEditorState;
  editorRef: CanvasEditorRef;
  onAIEdit: (ids: readonly string[]) => void;
}>) {
  const primary = state.selected_nodes.find((node) => node.id === state.primary_id) ?? state.selected_nodes[0] ?? null;
  if (!primary) {
    return <div className={styles.empty}>选择 Canvas 对象后，可在这里编辑 Transform、Appearance 与 Typography。</div>;
  }

  const version = state.local_document_version;
  const selectedIds = state.selected_ids;
  const setTransform = (patch: InspectorTransformPatch) => editorRef.current?.setTransform(primary.id, patch);

  return (
    <div className={styles.designPane}>
      <section className={styles.section}>
        <div className={styles.sectionTitle}><strong>Selection</strong><span>{selectedIds.length} selected</span></div>
        <label className={styles.stackField}>
          <span>Name</span>
          <input
            key={`${version}:name:${primary.name}`}
            defaultValue={primary.name}
            onBlur={(event) => {
              const value = event.currentTarget.value.trim();
              if (value && value !== primary.name) editorRef.current?.renameNode(primary.id, value);
            }}
          />
        </label>
        <div className={styles.actionGrid}>
          <button type="button" onClick={() => editorRef.current?.groupSelection()} disabled={!state.can_group}>Group</button>
          <button type="button" onClick={() => editorRef.current?.ungroupSelection()} disabled={!state.can_ungroup}>Ungroup</button>
          <button type="button" onClick={() => editorRef.current?.duplicateSelection()}>Duplicate</button>
          <button type="button" onClick={() => onAIEdit(selectedIds)}>AI Edit</button>
        </div>
      </section>

      {selectedIds.length === 1 ? (
        <section className={styles.section}>
          <div className={styles.sectionTitle}><strong>Transform</strong><span>{primary.kind}</span></div>
          <div className={styles.fieldGrid}>
            <NumberField label="X" value={primary.transform.x} version={version} onCommit={(x) => setTransform({ x })} />
            <NumberField label="Y" value={primary.transform.y} version={version} onCommit={(y) => setTransform({ y })} />
            <NumberField label="W" value={primary.transform.width} min={0} version={version} onCommit={(width) => setTransform({ width })} />
            <NumberField label="H" value={primary.transform.height} min={0} version={version} onCommit={(height) => setTransform({ height })} />
            <NumberField label="Rotate" value={primary.transform.rotation_deg} step={0.5} version={version} onCommit={(rotation_deg) => setTransform({ rotation_deg })} />
          </div>
          <div className={styles.layerOrder}>
            <button type="button" onClick={() => editorRef.current?.moveLayer(primary.id, "up")}>Bring forward</button>
            <button type="button" onClick={() => editorRef.current?.moveLayer(primary.id, "down")}>Send backward</button>
            <button type="button" onClick={() => editorRef.current?.fitSelection()}>Fit selection</button>
          </div>
        </section>
      ) : null}

      <section className={styles.section}>
        <div className={styles.sectionTitle}><strong>Appearance</strong><span>{state.sync_state}</span></div>
        <div className={styles.toggleRow}>
          <button type="button" data-active={primary.visible} onClick={() => editorRef.current?.setVisibility(selectedIds, !primary.visible)}>Visible</button>
          <button type="button" data-active={primary.locked} onClick={() => editorRef.current?.setLocked(selectedIds, !primary.locked)}>Locked</button>
        </div>
        <NumberField
          label="Opacity %"
          value={Math.round(primary.opacity * 100)}
          min={0}
          max={100}
          version={version}
          onCommit={(value) => editorRef.current?.setOpacity(selectedIds, Math.max(0, Math.min(100, value)) / 100)}
        />
        <label className={styles.stackField}>
          <span>Blend</span>
          <select
            key={`${version}:blend:${primary.blend_mode}`}
            defaultValue={primary.blend_mode}
            onChange={(event) => editorRef.current?.setBlendMode(selectedIds, event.currentTarget.value)}
          >
            {["normal", "multiply", "screen", "overlay", "darken", "lighten"].map((mode) => <option key={mode}>{mode}</option>)}
          </select>
        </label>
        {selectedIds.length === 1 && ["FRAME", "SHAPE", "TEXT"].includes(primary.kind) ? (
          <label className={styles.colorField}>
            <span>Fill</span>
            <input
              key={`${version}:fill:${primary.fill ?? "#222222"}`}
              type="color"
              defaultValue={primary.fill && /^#[0-9a-f]{6}$/i.test(primary.fill) ? primary.fill : "#222222"}
              onBlur={(event) => editorRef.current?.setFill(primary.id, event.currentTarget.value)}
            />
            <code>{primary.fill ?? "unset"}</code>
          </label>
        ) : null}
      </section>

      {primary.text && selectedIds.length === 1 ? (
        <section className={styles.section}>
          <div className={styles.sectionTitle}><strong>Typography</strong><span>TEXT</span></div>
          <label className={styles.stackField}>
            <span>Content</span>
            <textarea
              key={`${version}:text:${primary.text.content}`}
              defaultValue={primary.text.content}
              onBlur={(event) => {
                if (event.currentTarget.value !== primary.text?.content) {
                  editorRef.current?.setText(primary.id, { content: event.currentTarget.value });
                }
              }}
            />
          </label>
          <div className={styles.fieldGrid}>
            <NumberField label="Font" value={primary.text.font_size} min={1} version={version} onCommit={(font_size) => editorRef.current?.setText(primary.id, { font_size })} />
            <NumberField label="Line" value={primary.text.line_height} step={0.05} min={0.1} version={version} onCommit={(line_height) => editorRef.current?.setText(primary.id, { line_height })} />
            <NumberField label="Tracking" value={primary.text.letter_spacing} step={0.1} version={version} onCommit={(letter_spacing) => editorRef.current?.setText(primary.id, { letter_spacing })} />
          </div>
          <label className={styles.stackField}>
            <span>Align</span>
            <select
              key={`${version}:align:${primary.text.text_align}`}
              defaultValue={primary.text.text_align}
              onChange={(event) => editorRef.current?.setText(primary.id, { text_align: event.currentTarget.value as "left" | "center" | "right" })}
            >
              <option value="left">Left</option><option value="center">Center</option><option value="right">Right</option>
            </select>
          </label>
        </section>
      ) : null}

      <section className={styles.section}>
        <div className={styles.sectionTitle}><strong>Node</strong><span>{primary.id}</span></div>
        <p className={styles.metaLine}>Parent: {primary.parent_id ?? "document root"}</p>
        {primary.asset_id ? <p className={styles.metaLine}>Asset: {primary.asset_id}</p> : null}
        <button type="button" className={styles.danger} onClick={() => editorRef.current?.deleteSelection()} disabled={primary.effective_locked}>Delete selection</button>
      </section>
    </div>
  );
}

export function LayersInspector({
  state,
  editorRef,
  brandName,
  references,
  selectedReferenceIds,
  onToggleReference,
  onAIEdit,
}: Props) {
  const [tab, setTab] = useState<Tab>("layers");
  const [query, setQuery] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [editingId, setEditingId] = useState<string | null>(null);
  const layers = useMemo(() => filteredTree(state?.layers ?? [], query), [state?.layers, query]);

  return (
    <aside className={styles.inspector} aria-label="Layers 与 Inspector">
      <header className={styles.header}>
        <div><span>LUMI CANVAS</span><h2>Layers / Inspector</h2></div>
        <span className={styles.version}>{state ? `S${state.server_document_version} · L${state.local_document_version}` : "—"}</span>
      </header>
      <nav className={styles.tabs} aria-label="Inspector tabs">
        {(["layers", "design", "context"] as const).map((value) => (
          <button key={value} type="button" data-active={tab === value} onClick={() => setTab(value)}>{value}</button>
        ))}
      </nav>

      {tab === "layers" ? (
        <div className={styles.layersPane}>
          <div className={styles.layerTools}>
            <input aria-label="搜索图层" placeholder="Search layers" value={query} onChange={(event) => setQuery(event.currentTarget.value)} />
            <button type="button" onClick={() => editorRef.current?.groupSelection()} disabled={!state?.can_group}>Group</button>
            <button type="button" onClick={() => editorRef.current?.ungroupSelection()} disabled={!state?.can_ungroup}>Ungroup</button>
          </div>
          <div className={styles.layerList} role="tree" aria-label="Canvas layers">
            {layers.map((node) => (
              <LayerRow
                key={node.id}
                node={node}
                editorRef={editorRef}
                collapsed={collapsed}
                setCollapsed={setCollapsed}
                editingId={editingId}
                setEditingId={setEditingId}
              />
            ))}
            {!layers.length ? <div className={styles.empty}>没有匹配的图层。</div> : null}
          </div>
          <footer className={styles.layerFooter}>
            <span>{state?.selected_ids.length ?? 0} selected</span>
            <span>{state?.sync_state ?? "LOADING"}</span>
          </footer>
        </div>
      ) : null}

      {tab === "design" ? (
        state ? <DesignInspector state={state} editorRef={editorRef} onAIEdit={onAIEdit} /> : <div className={styles.empty}>Canvas runtime 正在加载。</div>
      ) : null}

      {tab === "context" ? (
        <div className={styles.contextPane}>
          <section className={styles.section}>
            <div className={styles.sectionTitle}><strong>Project context</strong><span>{brandName ?? "No Brand Kit"}</span></div>
            {references.map((reference) => (
              <label key={reference.id} className={styles.referenceRow}>
                <input
                  type="checkbox"
                  checked={selectedReferenceIds.includes(reference.asset_id)}
                  onChange={() => onToggleReference(reference.asset_id)}
                  disabled={reference.scan_status !== "READY"}
                />
                <span><strong>{reference.file_name}</strong><small>{reference.role} · {reference.scan_status}</small></span>
              </label>
            ))}
          </section>
          <section className={styles.section}>
            <div className={styles.sectionTitle}><strong>Context transparency</strong><span>SAFE</span></div>
            <p className={styles.metaLine}>Agent commands use exact Canvas selection IDs and the last saved server document version.</p>
            <p className={styles.privacy}>DIRTY / SAVING / OFFLINE / CONFLICT blocks AI Send. The UI never exposes system prompts or private chain-of-thought.</p>
          </section>
        </div>
      ) : null}
    </aside>
  );
}

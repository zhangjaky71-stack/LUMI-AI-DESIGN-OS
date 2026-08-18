"use client";

import { useEffect, useMemo, useState } from "react";
import type { OperationDescriptor } from "@lumi/canvas-sdk";
import type { DesignDocument, DesignNode } from "@lumi/design-ir";

import {
  brandBindings,
  commonValue,
  constraintBadges,
  layerLabel,
} from "@/lib/layers/model";

export function DesignInspector({
  document,
  selectedIds,
  canEdit,
  onCommit,
  onCommitBatch,
}: {
  document: DesignDocument;
  selectedIds: readonly string[];
  canEdit: boolean;
  onCommit: (descriptor: OperationDescriptor) => boolean;
  onCommitBatch: (descriptors: readonly OperationDescriptor[]) => boolean;
}) {
  const nodes = useMemo(
    () => selectedIds.map((id) => document.nodes[id]).filter((node): node is DesignNode => Boolean(node)),
    [document.nodes, selectedIds],
  );
  const single = nodes.length === 1 ? nodes[0]! : null;
  const [name, setName] = useState("");
  const [text, setText] = useState("");

  useEffect(() => setName(single ? layerLabel(single) : ""), [single]);
  useEffect(() => setText(single && typeof single.content === "string" ? single.content : ""), [single]);

  if (!nodes.length) {
    return (
      <aside className="design-inspector" aria-label="Inspector">
        <header className="inspector-header">
          <span className="canvas-panel-eyebrow">Properties</span>
          <strong>Inspector</strong>
        </header>
        <div className="inspector-empty">
          <strong>No selection</strong>
          <p>Select a layer or object to inspect structured Design IR properties.</p>
        </div>
      </aside>
    );
  }

  const allLocked = nodes.every((node) => node.locked === true);
  const anyLocked = nodes.some((node) => node.locked === true);
  const visible = commonValue(nodes, (node) => node.visible !== false);
  const opacity = commonValue(nodes, (node) => number(node.opacity, 1));
  const x = commonValue(nodes, (node) => number(node.transform?.x, 0));
  const y = commonValue(nodes, (node) => number(node.transform?.y, 0));
  const width = commonValue(nodes, (node) => numeric(node.transform?.width));
  const height = commonValue(nodes, (node) => numeric(node.transform?.height));
  const rotation = commonValue(nodes, (node) => number(node.transform?.rotation_deg, 0));
  const constraints = single ? constraintBadges(single) : [];
  const bindings = single ? brandBindings(single) : [];
  const propertyEditable = canEdit && !allLocked;

  const commitName = () => {
    if (!single || !propertyEditable || !name.trim() || name.trim() === layerLabel(single)) return;
    onCommit({
      type: "SET_PROPERTY",
      targetIds: [single.id],
      payload: { property: "name", value: name.trim() },
      reason: "inspector rename",
    });
  };

  const applyNumber = (field: "x" | "y" | "width" | "height" | "rotation", value: number) => {
    if (!Number.isFinite(value) || !propertyEditable) return;
    const descriptors: OperationDescriptor[] = [];
    for (const node of nodes) {
      if (node.locked) continue;
      if (field === "x" || field === "y") {
        descriptors.push({
          type: "MOVE_NODE",
          targetIds: [node.id],
          payload: {
            x: field === "x" ? value : number(node.transform?.x, 0),
            y: field === "y" ? value : number(node.transform?.y, 0),
          },
          reason: `inspector ${field}`,
        });
      } else if (field === "width" || field === "height") {
        const currentWidth = numeric(node.transform?.width);
        const currentHeight = numeric(node.transform?.height);
        if (currentWidth === undefined || currentHeight === undefined || value <= 0) continue;
        descriptors.push({
          type: "RESIZE_NODE",
          targetIds: [node.id],
          payload: {
            width: field === "width" ? value : currentWidth,
            height: field === "height" ? value : currentHeight,
          },
          reason: `inspector ${field}`,
        });
      } else {
        descriptors.push({
          type: "ROTATE_NODE",
          targetIds: [node.id],
          payload: { rotation_deg: value },
          reason: "inspector rotation",
        });
      }
    }
    if (descriptors.length) onCommitBatch(descriptors);
  };

  return (
    <aside className="design-inspector" aria-label="Inspector">
      <header className="inspector-header">
        <div>
          <span className="canvas-panel-eyebrow">Properties</span>
          <strong>{single ? layerLabel(single) : `${nodes.length} layers`}</strong>
        </div>
        <span>{single?.kind ?? "MULTI"}</span>
      </header>

      <div className="inspector-scroll">
        {single ? (
          <InspectorSection title="Identity">
            <label className="inspector-field inspector-field-wide">
              <span>Name</span>
              <input
                value={name}
                disabled={!propertyEditable}
                onChange={(event) => setName(event.target.value)}
                onBlur={commitName}
                onKeyDown={(event) => { if (event.key === "Enter") event.currentTarget.blur(); }}
              />
            </label>
            <ReadOnlyRow label="Kind" value={single.kind} />
            <ReadOnlyRow label="Role" value={typeof single.role === "string" ? single.role : "—"} />
          </InspectorSection>
        ) : null}

        <InspectorSection title="Transform">
          <div className="inspector-field-grid">
            <NumberField label="X" value={x.value} mixed={x.mixed} disabled={!propertyEditable} onCommit={(value) => applyNumber("x", value)} />
            <NumberField label="Y" value={y.value} mixed={y.mixed} disabled={!propertyEditable} onCommit={(value) => applyNumber("y", value)} />
            <NumberField label="W" value={width.value} mixed={width.mixed} disabled={!propertyEditable || (!width.mixed && width.value === undefined)} onCommit={(value) => applyNumber("width", value)} />
            <NumberField label="H" value={height.value} mixed={height.mixed} disabled={!propertyEditable || (!height.mixed && height.value === undefined)} onCommit={(value) => applyNumber("height", value)} />
            <NumberField label="°" value={rotation.value} mixed={rotation.mixed} disabled={!propertyEditable} onCommit={(value) => applyNumber("rotation", value)} />
          </div>
        </InspectorSection>

        <InspectorSection title="Appearance">
          <div className="inspector-toggle-row">
            <button
              type="button"
              disabled={!canEdit || anyLocked}
              onClick={() => onCommit({
                type: "SET_PROPERTY",
                targetIds: nodes.map((node) => node.id),
                payload: { property: "visible", value: visible.mixed ? true : !visible.value },
                reason: "inspector visibility",
              })}
            >
              Visibility · {visible.mixed ? "Mixed" : visible.value ? "Visible" : "Hidden"}
            </button>
            <button
              type="button"
              disabled={!canEdit || nodes.some((node) => node.metadata?.source_kind === "page")}
              onClick={() => onCommit({
                type: "SET_PROPERTY",
                targetIds: nodes.map((node) => node.id),
                payload: { property: "locked", value: !allLocked },
                reason: allLocked ? "inspector unlock" : "inspector lock",
              })}
            >
              {allLocked ? "Unlock" : anyLocked ? "Lock all (mixed)" : "Lock"}
            </button>
          </div>
          <NumberField
            label="Opacity %"
            value={opacity.value === undefined ? undefined : opacity.value * 100}
            mixed={opacity.mixed}
            disabled={!propertyEditable}
            min={0}
            max={100}
            onCommit={(value) => onCommit({
              type: "SET_PROPERTY",
              targetIds: nodes.filter((node) => !node.locked).map((node) => node.id),
              payload: { property: "opacity", value: Math.max(0, Math.min(100, value)) / 100 },
              reason: "inspector opacity",
            })}
          />
        </InspectorSection>

        {single?.kind === "TEXT" ? (
          <InspectorSection title="Typography / Content">
            <label className="inspector-field inspector-field-wide">
              <span>Text</span>
              <textarea
                value={text}
                rows={5}
                maxLength={200_000}
                disabled={!propertyEditable}
                onChange={(event) => setText(event.target.value)}
                onBlur={() => {
                  if (typeof single.content === "string" && text === single.content) return;
                  onCommit({ type: "SET_TEXT", targetIds: [single.id], payload: { content: text }, reason: "inspector text" });
                }}
              />
            </label>
            <ReadOnlyRow label="Font controls" value="Server text-style projection pending" />
          </InspectorSection>
        ) : null}

        {single ? (
          <InspectorSection title="Constraints">
            {constraints.length ? constraints.map((constraint) => (
              <div className={`constraint-card severity-${constraint.severity.toLowerCase()}`} key={constraint.id}>
                <div><strong>{constraint.type}</strong><span>{constraint.severity}</span></div>
                <p>{constraint.reason}</p>
                <small>Source: {constraint.source}</small>
              </div>
            )) : (
              <div className="inspector-info-card">
                <strong>No projected node constraint details</strong>
                <p>Server NODE-39 validation remains authoritative for every persisted edit. The Inspector never treats an enabled field as proof that an edit is allowed.</p>
              </div>
            )}
          </InspectorSection>
        ) : null}

        {single ? (
          <InspectorSection title="Brand Binding">
            {bindings.length ? bindings.map((binding) => (
              <div className="brand-binding-row" key={`${binding.property}:${binding.tokenRef}`}>
                <span>{binding.property}</span><code>{binding.tokenRef}</code>
              </div>
            )) : <p className="inspector-muted">No token binding is projected for this node.</p>}
            <p className="inspector-help">Bound visual properties are read-only in this core slice; NODE-56 will never silently detach a brand token.</p>
          </InspectorSection>
        ) : null}

        {single ? (
          <InspectorSection title="Metadata">
            <ReadOnlyRow label="Node ID" value={single.id} mono />
            <ReadOnlyRow label="Parent" value={single.parent_id ?? "—"} mono />
            <ReadOnlyRow label="Semantic tags" value={semanticTags(single).join(", ") || "—"} />
          </InspectorSection>
        ) : null}
      </div>
    </aside>
  );
}

function InspectorSection({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="inspector-section"><h3>{title}</h3>{children}</section>;
}

function NumberField({
  label,
  value,
  mixed,
  disabled,
  min,
  max,
  onCommit,
}: {
  label: string;
  value: number | undefined;
  mixed: boolean;
  disabled: boolean;
  min?: number;
  max?: number;
  onCommit: (value: number) => void;
}) {
  const [draft, setDraft] = useState(value === undefined ? "" : format(value));
  useEffect(() => setDraft(value === undefined ? "" : format(value)), [value]);
  return (
    <label className="inspector-field">
      <span>{label}</span>
      <input
        type="number"
        value={draft}
        placeholder={mixed ? "Mixed" : "—"}
        disabled={disabled}
        min={min}
        max={max}
        step="any"
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => {
          const parsed = Number(draft);
          if (draft.trim() && Number.isFinite(parsed)) onCommit(parsed);
        }}
        onKeyDown={(event) => { if (event.key === "Enter") event.currentTarget.blur(); }}
      />
    </label>
  );
}

function ReadOnlyRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div className="inspector-readonly"><span>{label}</span><span className={mono ? "is-mono" : ""}>{value}</span></div>;
}

function number(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function numeric(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function format(value: number): string {
  return Number.isInteger(value) ? String(value) : String(Math.round(value * 1000) / 1000);
}

function semanticTags(node: DesignNode): string[] {
  const semantic = node.semantic;
  if (!semantic || typeof semantic !== "object") return [];
  const tags = (semantic as Record<string, unknown>).tags;
  return Array.isArray(tags) ? tags.filter((item): item is string => typeof item === "string") : [];
}
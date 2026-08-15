import type { DesignNodeKind } from "@lumi/design-ir";
import type { CanvasSyncState } from "@/lib/infinite-canvas/types";

export interface LayerTreeNode {
  readonly id: string;
  readonly name: string;
  readonly kind: DesignNodeKind | `custom:${string}`;
  readonly parent_id: string | null;
  readonly depth: number;
  readonly children: readonly LayerTreeNode[];
  readonly visible: boolean;
  readonly effective_visible: boolean;
  readonly locked: boolean;
  readonly effective_locked: boolean;
  readonly selected: boolean;
  readonly primary: boolean;
}

export interface InspectorTransformSnapshot {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
  readonly rotation_deg: number;
}

export interface InspectorTextSnapshot {
  readonly content: string;
  readonly font_size: number;
  readonly line_height: number;
  readonly letter_spacing: number;
  readonly text_align: "left" | "center" | "right";
}

export interface InspectorNodeSnapshot {
  readonly id: string;
  readonly name: string;
  readonly kind: DesignNodeKind | `custom:${string}`;
  readonly parent_id: string | null;
  readonly visible: boolean;
  readonly effective_visible: boolean;
  readonly locked: boolean;
  readonly effective_locked: boolean;
  readonly opacity: number;
  readonly blend_mode: string;
  readonly fill: string | null;
  readonly asset_id: string | null;
  readonly transform: InspectorTransformSnapshot;
  readonly text: InspectorTextSnapshot | null;
}

export interface CanvasEditorState {
  readonly document_id: string;
  readonly server_document_version: number;
  readonly local_document_version: number;
  readonly sync_state: CanvasSyncState;
  readonly selected_ids: readonly string[];
  readonly primary_id: string | null;
  readonly layers: readonly LayerTreeNode[];
  readonly selected_nodes: readonly InspectorNodeSnapshot[];
  readonly can_group: boolean;
  readonly can_ungroup: boolean;
}

export interface InspectorTransformPatch {
  readonly x?: number;
  readonly y?: number;
  readonly width?: number;
  readonly height?: number;
  readonly rotation_deg?: number;
}

export interface InspectorTextPatch {
  readonly content?: string;
  readonly font_size?: number;
  readonly line_height?: number;
  readonly letter_spacing?: number;
  readonly text_align?: "left" | "center" | "right";
  readonly fill?: string;
}

export interface CanvasEditorApi {
  select(ids: readonly string[], primaryId?: string | null): void;
  renameNode(nodeId: string, name: string): boolean;
  setVisibility(nodeIds: readonly string[], visible: boolean): boolean;
  setLocked(nodeIds: readonly string[], locked: boolean): boolean;
  setOpacity(nodeIds: readonly string[], opacity: number): boolean;
  setBlendMode(nodeIds: readonly string[], blendMode: string): boolean;
  setFill(nodeId: string, fill: string): boolean;
  setTransform(nodeId: string, patch: InspectorTransformPatch): boolean;
  setText(nodeId: string, patch: InspectorTextPatch): boolean;
  moveLayer(nodeId: string, direction: "up" | "down"): boolean;
  groupSelection(): boolean;
  ungroupSelection(): boolean;
  duplicateSelection(): void;
  deleteSelection(): void;
  fitSelection(): void;
}

export interface CanvasEditorRef {
  current: CanvasEditorApi | null;
}

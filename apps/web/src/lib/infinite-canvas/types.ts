import type { DesignDocument, DesignOperation } from "@lumi/design-ir";

export type CanvasSyncState = "SAVED" | "DIRTY" | "SAVING" | "OFFLINE" | "CONFLICT";

export interface InfiniteCanvasSnapshot {
  readonly project_id: string;
  readonly document: DesignDocument;
  readonly saved_at: string;
}

export interface SaveCanvasOperationsInput {
  readonly project_id: string;
  readonly document_id: string;
  readonly expected_document_version: number;
  readonly operations: readonly DesignOperation[];
}

export interface InfiniteCanvasSeed {
  readonly snapshot: InfiniteCanvasSnapshot;
  readonly conflict_on_next_save: boolean;
}

export interface InfiniteCanvasBootstrap {
  readonly mode: "http" | "e2e";
  readonly seed: InfiniteCanvasSeed | null;
}

export interface CanvasSelectionContext {
  readonly selected_node_ids: readonly string[];
  readonly document_version: number;
  readonly sync_state: CanvasSyncState;
}

export interface PendingOperationBatch {
  readonly base_document_version: number;
  readonly operations: readonly DesignOperation[];
  readonly count: number;
}

export type FramePresetId = "1:1" | "4:5" | "9:16" | "16:9" | "A4";
export interface FramePreset {
  readonly id: FramePresetId;
  readonly width: number;
  readonly height: number;
  readonly label: string;
}

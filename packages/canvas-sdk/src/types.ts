import type { DesignDocument, DesignNode, DesignOperation, IrIssue } from "../../design-ir/src/index";

export interface Point { readonly x: number; readonly y: number }
export interface Rect { readonly x: number; readonly y: number; readonly width: number; readonly height: number }
export interface Viewport { readonly width: number; readonly height: number; readonly dpr: number }
export interface CameraState { readonly x: number; readonly y: number; readonly zoom: number }

export const MIN_ZOOM = 0.05;
export const MAX_ZOOM = 64;

export type CanvasDiagnosticSeverity = "info" | "warning" | "error";
export interface CanvasDiagnostic {
  readonly code: string;
  readonly message: string;
  readonly severity: CanvasDiagnosticSeverity;
  readonly nodeId?: string;
}

export const CANVAS_RENDER_KINDS = [
  "FRAME", "GROUP", "TEXT", "IMAGE", "SHAPE", "VECTOR_PATH", "VIDEO",
  "MASK", "GUIDE", "COMPONENT", "INSTANCE",
] as const;
export type CanvasRenderKind = (typeof CANVAS_RENDER_KINDS)[number];

export interface RenderNodeSnapshot {
  readonly id: string;
  readonly kind: CanvasRenderKind | "PLACEHOLDER";
  readonly sourceKind: string;
  readonly parentId: string | null;
  readonly childIds: readonly string[];
  readonly bounds: Rect;
  readonly rotationDeg: number;
  readonly visible: boolean;
  readonly locked: boolean;
  readonly opacity: number;
  readonly zOrder: number;
  readonly role?: string;
  readonly assetId?: string;
  readonly text?: string;
  readonly styleRefs: readonly string[];
  readonly diagnosticCodes: readonly string[];
}

export interface SceneSnapshot {
  readonly documentId: string;
  readonly nodes: ReadonlyMap<string, RenderNodeSnapshot>;
  readonly orderedIds: readonly string[];
  readonly diagnostics: readonly CanvasDiagnostic[];
}

export interface RendererFrame {
  readonly camera: CameraState;
  readonly viewport: Viewport;
  readonly visibleNodes: readonly RenderNodeSnapshot[];
  readonly selectedIds: ReadonlySet<string>;
  readonly diagnostics: readonly CanvasDiagnostic[];
}

export interface RendererAdapter {
  mount(): void | Promise<void>;
  render(frame: RendererFrame): void;
  destroyNode(nodeId: string): void;
  destroy(): void;
}

export interface TextureHandle { readonly key: string; readonly bytes?: number; destroy(): void }
export type AssetTier = "preview" | "full";
export interface AuthorizedAssetSource { readonly assetId: string; readonly tier: AssetTier; readonly url: string }
export interface AssetResolver { resolve(assetId: string, tier: AssetTier): Promise<AuthorizedAssetSource> }
export interface TextureLoader { load(source: AuthorizedAssetSource): Promise<TextureHandle> }

export interface OperationDescriptor {
  readonly type: DesignOperation["type"];
  readonly targetIds: readonly string[];
  readonly payload: Readonly<Record<string, unknown>>;
  readonly reason?: string;
}

export interface OperationCommitResult {
  readonly ok: boolean;
  readonly document: DesignDocument;
  readonly operationIds: readonly string[];
  readonly issues: readonly IrIssue[];
  readonly error?: Error;
}

export interface ClipboardAssetPolicy {
  remapAsset(assetId: string, sourceProjectId: string, targetProjectId: string): Promise<string | null>;
}

export interface CanvasFragment {
  readonly schemaVersion: "lumi.canvas-fragment/1.0";
  readonly sourceProjectId: string;
  readonly rootNodeIds: readonly string[];
  readonly nodes: Readonly<Record<string, DesignNode>>;
}

export type KeyboardCommand =
  | "select-tool" | "pan-tool" | "delete" | "copy" | "paste" | "undo" | "redo"
  | "nudge-left" | "nudge-right" | "nudge-up" | "nudge-down";

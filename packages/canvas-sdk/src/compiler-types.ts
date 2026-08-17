import type { DesignDocument, JsonValue, SemanticDiff } from "../../design-ir/src/index";
import type { CanvasDiagnostic, CanvasRenderKind, Rect, RenderNodeSnapshot, SceneSnapshot } from "./types";

export const CANVAS_COMPILER_VERSION = "1.0.0" as const;

export type CompileDiagnosticSeverity = "info" | "warning" | "error";
export type CompileDiagnosticCode =
  | "COMPILER_STRUCTURAL_INVALID"
  | "COMPILER_NODE_PLACEHOLDER"
  | "COMPILER_RESOURCE_MISSING"
  | "COMPILER_RESOURCE_RESOLUTION_FAILED"
  | "COMPILER_FONT_MISSING"
  | "COMPILER_FONT_RESOLUTION_FAILED"
  | "COMPILER_STYLE_TOKEN_MISSING"
  | "COMPILER_MASK_REFERENCE_MISSING"
  | "COMPILER_TEXT_MEASURE_FAILED"
  | "COMPILER_INCREMENTAL_FALLBACK"
  | "COMPILER_VERSION_MISMATCH";

export interface CompileDiagnostic {
  readonly code: CompileDiagnosticCode;
  readonly message: string;
  readonly severity: CompileDiagnosticSeverity;
  readonly nodeId?: string;
  readonly resourceId?: string;
}

export interface Matrix2D {
  readonly a: number;
  readonly b: number;
  readonly c: number;
  readonly d: number;
  readonly tx: number;
  readonly ty: number;
}

export type CompilerResourceTier = "preview" | "full";
export type CompilerResourceStatus = "ready" | "missing" | "error";

export interface ResolvedCompilerAsset {
  readonly assetId: string;
  readonly kind: "image" | "video" | "generic";
  readonly tier: CompilerResourceTier;
  readonly resourceVersion: string;
  readonly fingerprint: string;
  readonly status: CompilerResourceStatus;
  readonly authorizedUrl?: string;
  readonly mimeType?: string;
  readonly width?: number;
  readonly height?: number;
}

export interface ResolvedCompilerFont {
  readonly fontRef: string;
  readonly family: string;
  readonly style: string;
  readonly weight: number;
  readonly resourceVersion: string;
  readonly fingerprint: string;
  readonly status: CompilerResourceStatus;
  readonly authorizedUrl?: string;
}

export interface ResolvedCompilerText {
  readonly content: string;
  readonly fontRef?: string;
  readonly font?: ResolvedCompilerFont;
  readonly metrics: {
    readonly width: number;
    readonly height: number;
    readonly baseline: number;
  };
}

export type ResolvedCompilerStyle = Readonly<Record<string, JsonValue>>;

export interface CompilerInteractionFlags {
  readonly selectable: boolean;
  readonly transformable: boolean;
  readonly hitTestable: boolean;
  readonly editable: boolean;
}

export interface CompiledSceneNode {
  readonly id: string;
  readonly kind: CanvasRenderKind | "PLACEHOLDER";
  readonly sourceKind: string;
  readonly parentId: string | null;
  readonly childIds: readonly string[];
  readonly localTransform: Matrix2D;
  readonly worldTransform: Matrix2D;
  readonly localBounds: Rect;
  readonly worldBounds: Rect;
  readonly clipId?: string;
  readonly maskId?: string;
  readonly resolvedStyle: ResolvedCompilerStyle;
  readonly styleVersions: Readonly<Record<string, string>>;
  readonly resolvedText?: ResolvedCompilerText;
  readonly resolvedResource?: ResolvedCompilerAsset;
  readonly zOrder: number;
  readonly interactionFlags: CompilerInteractionFlags;
  readonly visible: boolean;
  readonly locked: boolean;
  readonly opacity: number;
  readonly placeholder: boolean;
  readonly diagnosticCodes: readonly CompileDiagnosticCode[];
  readonly sourceFingerprint: string;
  readonly renderFingerprint: string;
}

export interface CanvasCompilerProvenance {
  readonly compiler_version: string;
  readonly document_id: string;
  readonly schema_version: string;
  readonly document_hash: string;
  readonly scene_hash: string;
  readonly resource_versions: Readonly<Record<string, string>>;
  readonly font_versions: Readonly<Record<string, string>>;
  readonly token_versions: Readonly<Record<string, string>>;
}

export interface CompiledSceneSnapshot {
  readonly compilerVersion: string;
  readonly documentId: string;
  readonly nodes: ReadonlyMap<string, CompiledSceneNode>;
  readonly orderedIds: readonly string[];
  readonly diagnostics: readonly CompileDiagnostic[];
  readonly sceneHash: string;
  readonly provenance: CanvasCompilerProvenance;
}

export interface CompileSuccess {
  readonly ok: true;
  readonly snapshot: CompiledSceneSnapshot;
  readonly diagnostics: readonly CompileDiagnostic[];
}
export interface CompileFailure {
  readonly ok: false;
  readonly diagnostics: readonly CompileDiagnostic[];
}
export type CompileResult = CompileSuccess | CompileFailure;

export interface CompiledScenePatch {
  readonly compilerVersion: string;
  readonly documentId: string;
  readonly removedNodeIds: readonly string[];
  readonly upsertedNodes: readonly CompiledSceneNode[];
  readonly orderedIds: readonly string[];
  readonly diagnostics: readonly CompileDiagnostic[];
  readonly sceneHash: string;
}

export interface IncrementalCompileSuccess extends CompileSuccess {
  readonly dirtyNodeIds: readonly string[];
  readonly fallbackToFull: boolean;
  readonly patch: CompiledScenePatch;
}
export type IncrementalCompileResult = IncrementalCompileSuccess | CompileFailure;

export interface AssetCompileResolver {
  resolveAsset(input: {
    readonly document: DesignDocument;
    readonly assetId: string;
    readonly tier: CompilerResourceTier;
    readonly nodeId: string;
  }): Promise<ResolvedCompilerAsset | null>;
}

export interface FontCompileResolver {
  resolveFont(input: {
    readonly document: DesignDocument;
    readonly fontRef: string;
    readonly nodeId: string;
  }): Promise<ResolvedCompilerFont | null>;
}

export interface StyleCompileResolution {
  readonly style: ResolvedCompilerStyle;
  readonly missingRefs: readonly string[];
  readonly versions: Readonly<Record<string, string>>;
}
export interface StyleCompileResolver {
  resolveStyle(document: DesignDocument, styleRefs: readonly string[]): StyleCompileResolution;
}

export interface TextCompileMeasurer {
  measure(input: {
    readonly content: string;
    readonly style: ResolvedCompilerStyle;
    readonly font: ResolvedCompilerFont | null;
    readonly nodeId: string;
  }): Promise<{ readonly width: number; readonly height: number; readonly baseline: number }>;
}

export interface CanvasCompilerOptions {
  readonly compilerVersion?: string;
  readonly resourceTier?: CompilerResourceTier;
  readonly assetResolver?: AssetCompileResolver;
  readonly fontResolver?: FontCompileResolver;
  readonly styleResolver?: StyleCompileResolver;
  readonly textMeasurer?: TextCompileMeasurer;
}

export interface IncrementalCompileRequest {
  readonly previous: CompiledSceneSnapshot;
  readonly before: DesignDocument;
  readonly after: DesignDocument;
  readonly diff?: SemanticDiff;
}

export interface ResourceInvalidation {
  readonly assetIds?: readonly string[];
  readonly fontRefs?: readonly string[];
  readonly styleRefs?: readonly string[];
}

export interface ArtifactCompilerProvenanceSink {
  recordCompilerProvenance(provenance: CanvasCompilerProvenance): void | Promise<void>;
}

export interface CompiledRendererPatchBindings {
  upsertNode(node: RenderNodeSnapshot): void;
  removeNode(nodeId: string): void;
  setPaintOrder(orderedIds: readonly string[]): void;
}

export interface CompiledSceneBridge {
  toCanvasScene(snapshot: CompiledSceneSnapshot): SceneSnapshot;
  toCanvasDiagnostics(diagnostics: readonly CompileDiagnostic[]): readonly CanvasDiagnostic[];
}

import type {
  DesignDocument,
  JsonValue,
  SemanticDiff,
} from "../../design-ir/src/index";
import type {
  CanvasNodeDiagnostic,
  CanvasSceneNode,
  CanvasSceneSnapshot,
} from "./ir-scene";
import type { Matrix2D } from "./matrix";
import type { Rect } from "./types";

export const CANVAS_COMPILER_VERSION = "1.0.0";

export type CompileSeverity = "ERROR" | "WARNING" | "INFO";

export type CompileDiagnosticCode =
  | "STRUCTURAL_INVALID"
  | "SCHEMA_UNSUPPORTED"
  | "NODE_PLACEHOLDER"
  | "RESOURCE_MISSING"
  | "RESOURCE_RESOLUTION_FAILED"
  | "FONT_MISSING"
  | "FONT_RESOLUTION_FAILED"
  | "STYLE_TOKEN_MISSING"
  | "TEXT_MEASURE_FAILED"
  | "INCREMENTAL_FALLBACK"
  | "IR_DIAGNOSTIC";

export interface CompileDiagnostic {
  readonly code: CompileDiagnosticCode;
  readonly severity: CompileSeverity;
  readonly message: string;
  readonly node_id?: string;
  readonly pointer?: string;
  readonly source?: string;
}

export type CompilerResourceVariant = "thumbnail" | "preview" | "full";
export type CompilerResourceStatus = "READY" | "PENDING" | "MISSING";

export interface ResolvedCompilerResource {
  readonly asset_id: string;
  readonly variant: CompilerResourceVariant;
  readonly version: string;
  readonly status: CompilerResourceStatus;
  readonly fingerprint: string;
  readonly uri?: string;
  readonly mime_type?: string;
  readonly width?: number;
  readonly height?: number;
}

export interface ResolvedCompilerFont {
  readonly font_ref: string;
  readonly family: string;
  readonly version: string;
  readonly status: CompilerResourceStatus;
  readonly style?: string;
  readonly weight?: number;
  readonly uri?: string;
  readonly fingerprint: string;
}

export interface ResolvedCompilerText {
  readonly content: string;
  readonly font_ref?: string;
  readonly font?: ResolvedCompilerFont;
  readonly metrics?: {
    readonly width: number;
    readonly height: number;
    readonly baseline: number;
  };
}

export type ResolvedCompilerStyle = Readonly<Record<string, JsonValue>>;

export interface CompilerInteractionFlags {
  readonly selectable: boolean;
  readonly transformable: boolean;
  readonly hit_testable: boolean;
  readonly editable: boolean;
}

export interface CompiledSceneNode extends CanvasSceneNode {
  readonly resolved_style: ResolvedCompilerStyle;
  readonly resolved_text?: ResolvedCompilerText;
  readonly resolved_resource?: ResolvedCompilerResource;
  readonly interaction_flags: CompilerInteractionFlags;
  readonly clip_id?: string;
  readonly mask_id?: string;
  readonly placeholder: boolean;
}

export interface CanvasRenderPlanItem {
  readonly id: string;
  readonly kind: string;
  readonly parent_id: string | null;
  readonly z_order: number;
  readonly visible: boolean;
  readonly local_matrix: Matrix2D;
  readonly world_matrix: Matrix2D;
  readonly local_bounds: Rect;
  readonly world_bounds: Rect;
  readonly resolved_style: ResolvedCompilerStyle;
  readonly resolved_text?: ResolvedCompilerText;
  readonly resolved_resource?: ResolvedCompilerResource;
  readonly interaction_flags: CompilerInteractionFlags;
  readonly clip_id?: string;
  readonly mask_id?: string;
  readonly placeholder: boolean;
}

export interface CanvasRenderPlan {
  readonly compiler_version: string;
  readonly document_id: string;
  readonly items: readonly CanvasRenderPlanItem[];
}

export interface CanvasCompileProvenance {
  readonly compiler_version: string;
  readonly document_id: string;
  readonly schema_version: string;
  readonly document_version: number;
  readonly resource_versions: Readonly<Record<string, string>>;
  readonly font_versions: Readonly<Record<string, string>>;
  readonly compile_hash?: string;
}

export interface CompiledSceneSnapshot extends CanvasSceneSnapshot {
  readonly compiler_version: string;
  readonly nodes: ReadonlyMap<string, CompiledSceneNode>;
  readonly diagnostics: readonly CanvasNodeDiagnostic[];
  readonly compile_diagnostics: readonly CompileDiagnostic[];
  readonly render_plan: CanvasRenderPlan;
  readonly provenance: CanvasCompileProvenance;
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

export interface CompilePatch {
  readonly compiler_version: string;
  readonly document_id: string;
  readonly removed_node_ids: readonly string[];
  readonly upserted_nodes: readonly CompiledSceneNode[];
  readonly paint_order: readonly string[];
  readonly diagnostics: readonly CompileDiagnostic[];
}

export interface IncrementalCompileResult extends CompileSuccess {
  readonly patch: CompilePatch;
  readonly dirty_node_ids: readonly string[];
  readonly fallback_to_full: boolean;
}

export interface CompilerAssetResolver {
  resolveAsset(
    document: DesignDocument,
    assetId: string,
    variant: CompilerResourceVariant,
  ): Promise<ResolvedCompilerResource | null>;
}

export interface CompilerFontResolver {
  resolveFont(
    document: DesignDocument,
    fontRef: string,
  ): Promise<ResolvedCompilerFont | null>;
}

export interface CompilerStyleResolver {
  resolveStyle(
    document: DesignDocument,
    styleRefs: readonly string[],
  ): {
    readonly style: ResolvedCompilerStyle;
    readonly missing_refs: readonly string[];
  };
}

export interface CompilerTextMeasurer {
  measure(
    content: string,
    style: ResolvedCompilerStyle,
    font: ResolvedCompilerFont | null,
  ): Promise<{ readonly width: number; readonly height: number; readonly baseline: number }>;
}

export interface CanvasCompilerOptions {
  readonly compiler_version?: string;
  readonly resource_variant?: CompilerResourceVariant;
  readonly asset_resolver?: CompilerAssetResolver;
  readonly font_resolver?: CompilerFontResolver;
  readonly style_resolver?: CompilerStyleResolver;
  readonly text_measurer?: CompilerTextMeasurer;
}

export interface CanvasSceneCompilerPort {
  compileStructure(document: DesignDocument): CompileResult;
}

export interface IncrementalCompileRequest {
  readonly previous: CompiledSceneSnapshot;
  readonly before: DesignDocument;
  readonly after: DesignDocument;
  readonly diff?: SemanticDiff;
}

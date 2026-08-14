export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { readonly [key: string]: JsonValue };

export const DESIGN_NODE_KINDS = [
  "DOCUMENT_ROOT",
  "FRAME",
  "GROUP",
  "TEXT",
  "IMAGE",
  "SHAPE",
  "VECTOR_PATH",
  "VIDEO",
  "MASK",
  "GUIDE",
  "COMPONENT",
  "INSTANCE",
] as const;

export type DesignNodeKind = (typeof DESIGN_NODE_KINDS)[number];

export interface DesignTransform {
  readonly x?: number;
  readonly y?: number;
  readonly width?: number;
  readonly height?: number;
  readonly rotation_deg?: number;
  readonly scale_x?: number;
  readonly scale_y?: number;
  readonly skew_x?: number;
  readonly skew_y?: number;
  readonly anchor_x?: number;
  readonly anchor_y?: number;
}

export interface DesignNode {
  readonly id: string;
  readonly kind: DesignNodeKind | `custom:${string}`;
  readonly name?: string;
  readonly role?: string;
  readonly parent_id: string | null;
  readonly children: readonly string[];
  readonly visible?: boolean;
  readonly locked?: boolean;
  readonly opacity?: number;
  readonly blend_mode?: string;
  readonly transform?: DesignTransform;
  readonly style_refs?: readonly string[];
  readonly constraint_refs?: readonly string[];
  readonly semantic?: Readonly<Record<string, JsonValue>>;
  readonly metadata?: Readonly<Record<string, JsonValue>>;
  readonly [key: string]: unknown;
}

export interface DesignDocument {
  readonly schema_version: string;
  readonly document_id: string;
  readonly unit: "px" | string;
  readonly root_id: string;
  readonly nodes: Readonly<Record<string, DesignNode>>;
  readonly resources: Readonly<Record<string, JsonValue>>;
  readonly metadata: Readonly<Record<string, JsonValue>>;
}

export const DESIGN_OPERATION_TYPES = [
  "CREATE_NODE",
  "DELETE_NODE",
  "SET_PROPERTY",
  "MOVE_NODE",
  "RESIZE_NODE",
  "ROTATE_NODE",
  "REORDER_NODE",
  "REPARENT_NODE",
  "REPLACE_ASSET",
  "SET_TEXT",
  "APPLY_STYLE",
  "BATCH",
] as const;

export type DesignOperationType = (typeof DESIGN_OPERATION_TYPES)[number];

export interface DesignOperation {
  readonly operation_id: string;
  readonly type: DesignOperationType;
  readonly target_ids: readonly string[];
  readonly expected_document_version: number;
  readonly payload: Readonly<Record<string, unknown>>;
  readonly reason?: string;
}

export interface OperationFailure {
  readonly operation_id: string;
  readonly code:
    | "VERSION_CONFLICT"
    | "INVALID_OPERATION"
    | "TARGET_NOT_FOUND"
    | "PARENT_NOT_FOUND"
    | "ROOT_MUTATION_FORBIDDEN"
    | "CYCLE_DETECTED"
    | "NON_FINITE_NUMBER"
    | "UNSUPPORTED_OPERATION";
  readonly message: string;
  readonly target_id?: string;
}

export interface ExecutionSuccess {
  readonly ok: true;
  readonly document: DesignDocument;
  readonly applied_operation_ids: readonly string[];
  readonly previous_version: number;
  readonly document_version: number;
}

export interface ExecutionFailure {
  readonly ok: false;
  readonly document: DesignDocument;
  readonly failures: readonly OperationFailure[];
  readonly previous_version: number;
  readonly document_version: number;
}

export type ExecutionResult = ExecutionSuccess | ExecutionFailure;

export function getDocumentVersion(document: DesignDocument): number {
  const value = document.metadata.document_version;
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : 0;
}

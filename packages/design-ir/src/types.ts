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
  readonly bounds?: Readonly<Record<string, number>>;
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

export type IrErrorCode =
  | "IR_SCHEMA_INVALID"
  | "IR_GRAPH_CYCLE"
  | "IR_REFERENCE_MISSING"
  | "IR_VERSION_UNSUPPORTED"
  | "IR_OPERATION_INVALID"
  | "IR_TARGET_NOT_FOUND"
  | "IR_VERSION_CONFLICT"
  | "IR_BATCH_FAILED"
  | "IR_CONSTRAINT_FAILED";

export interface IrIssue {
  readonly code: IrErrorCode;
  readonly message: string;
  readonly pointer?: string;
  readonly node_ids?: readonly string[];
  readonly operation_id?: string;
}

export class IrRuntimeError extends Error {
  readonly code: IrErrorCode;
  readonly pointer: string | undefined;
  readonly node_ids: readonly string[];
  readonly operation_id: string | undefined;

  constructor(issue: IrIssue) {
    super(`${issue.code}: ${issue.message}`);
    this.name = "IrRuntimeError";
    this.code = issue.code;
    this.pointer = issue.pointer;
    this.node_ids = issue.node_ids ?? [];
    this.operation_id = issue.operation_id;
  }
}

export interface SemanticDiff {
  readonly nodes_added: readonly string[];
  readonly nodes_removed: readonly string[];
  readonly properties_changed: readonly string[];
  readonly text_changed: readonly string[];
  readonly geometry_changed: readonly string[];
  readonly asset_replaced: readonly string[];
  readonly constraints_changed: readonly string[];
}

export interface OperationExecution {
  readonly document: DesignDocument;
  readonly previous_version: number;
  readonly document_version: number;
  readonly applied_operation_ids: readonly string[];
  readonly diff: SemanticDiff;
}

export interface NodeSelector {
  readonly id?: string;
  readonly role?: string;
  readonly kind?: DesignNode["kind"];
  readonly parent_id?: string | null;
  readonly frame_id?: string;
  readonly brand_binding?: string;
  readonly asset_binding?: string;
  readonly locked?: boolean;
}

export interface MigrationStep {
  readonly from: string;
  readonly to: string;
  readonly migrate: (document: DesignDocument) => DesignDocument;
}

export type ConstraintPreflight = (
  document: DesignDocument,
  operation: DesignOperation,
) => readonly IrIssue[];

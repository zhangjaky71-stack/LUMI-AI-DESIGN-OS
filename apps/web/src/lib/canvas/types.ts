import type { DesignDocument } from "@lumi/design-ir";
import type { OperationDescriptor } from "@lumi/canvas-sdk";

export type CanvasProjection = {
  designDocumentId: string;
  designDocumentVersionId: string;
  versionNumber: number;
  revision: number;
  contentHash: string;
  activePageId: string;
  document: DesignDocument;
};

export type CanvasSaveState =
  | "saved"
  | "dirty"
  | "saving"
  | "offline"
  | "conflict"
  | "error";

export type CanvasCommandBatch = {
  clientBatchId: string;
  expectedDesignDocumentVersionId: string;
  expectedVersionNumber: number;
  expectedRevision: number;
  descriptors: readonly OperationDescriptor[];
};

export function parseCanvasProjection(value: unknown): CanvasProjection {
  const record = asRecord(value, "CANVAS_PROJECTION_INVALID");
  const rawDocument = structuredClone(
    asRecord(record.document, "CANVAS_DOCUMENT_INVALID"),
  );
  const designDocumentId = requiredString(
    record.design_document_id ?? record.designDocumentId,
    "CANVAS_DOCUMENT_ID_REQUIRED",
  );
  const revision = positiveInteger(record.revision, "CANVAS_REVISION_INVALID");
  const rootId = requiredString(rawDocument.root_id, "CANVAS_ROOT_ID_REQUIRED");
  if (rawDocument.document_id !== designDocumentId) {
    throw new Error("CANVAS_DOCUMENT_ID_MISMATCH");
  }
  const nodes = asRecord(rawDocument.nodes, "CANVAS_DOCUMENT_NODES_INVALID");
  for (const rawNode of Object.values(nodes)) {
    if (!rawNode || typeof rawNode !== "object" || Array.isArray(rawNode)) continue;
    const node = rawNode as Record<string, unknown>;
    const metadata = node.metadata;
    if (
      node.parent_id === null &&
      metadata &&
      typeof metadata === "object" &&
      !Array.isArray(metadata) &&
      (metadata as Record<string, unknown>).source_kind === "page"
    ) {
      node.parent_id = rootId;
    }
  }
  rawDocument.schema_version = normalizeRuntimeSchema(rawDocument.schema_version);
  const document = rawDocument as unknown as DesignDocument;
  const metadataRevision = (document.metadata as Record<string, unknown>)?.document_version;
  if (metadataRevision !== revision) throw new Error("CANVAS_METADATA_REVISION_MISMATCH");
  return {
    designDocumentId,
    designDocumentVersionId: requiredString(
      record.design_document_version_id ?? record.designDocumentVersionId,
      "CANVAS_DOCUMENT_VERSION_ID_REQUIRED",
    ),
    versionNumber: positiveInteger(
      record.version_number ?? record.versionNumber,
      "CANVAS_VERSION_NUMBER_INVALID",
    ),
    revision,
    contentHash: sha256(record.content_hash ?? record.contentHash),
    activePageId: requiredString(
      record.active_page_id ?? record.activePageId,
      "CANVAS_ACTIVE_PAGE_REQUIRED",
    ),
    document,
  };
}

export function wireDescriptor(descriptor: OperationDescriptor): Record<string, unknown> {
  let payload: Record<string, unknown> = structuredClone(descriptor.payload);
  if (descriptor.type === "CREATE_NODE") {
    const node = asRecord(payload.node, "CANVAS_CREATE_NODE_PAYLOAD_INVALID");
    const transform = asRecord(node.transform ?? {}, "CANVAS_CREATE_TRANSFORM_INVALID");
    payload = {
      kind: node.kind,
      id: node.id,
      parent_id: node.parent_id,
      name: node.name,
      x: transform.x ?? 0,
      y: transform.y ?? 0,
      width: transform.width,
      height: transform.height,
      ...(typeof payload.index === "number" ? { index: payload.index } : {}),
    };
  } else if (descriptor.type === "SET_PROPERTY") {
    payload = {
      path: payload.property,
      value: structuredClone(payload.value),
    };
  } else if (descriptor.type === "DELETE_NODE") {
    payload = { ...payload, recursive: true };
  }
  return {
    type: descriptor.type,
    target_ids: [...descriptor.targetIds],
    payload,
    ...(descriptor.reason ? { reason: descriptor.reason } : {}),
  };
}

function normalizeRuntimeSchema(value: unknown): "1.0" | "1.1" | "2.0" {
  if (value === "1.0" || value === "1.1" || value === "2.0") return value;
  if (value === "lumi.design-ir/1.0") return "1.0";
  throw new Error("CANVAS_SCHEMA_VERSION_UNSUPPORTED");
}

function asRecord(value: unknown, code: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(code);
  return value as Record<string, unknown>;
}

function requiredString(value: unknown, code: string): string {
  if (typeof value !== "string" || !value.trim()) throw new Error(code);
  return value;
}

function positiveInteger(value: unknown, code: string): number {
  if (!Number.isInteger(value) || (value as number) < 1) throw new Error(code);
  return value as number;
}

function sha256(value: unknown): string {
  const text = requiredString(value, "CANVAS_CONTENT_HASH_REQUIRED");
  if (!/^[0-9a-f]{64}$/.test(text)) throw new Error("CANVAS_CONTENT_HASH_INVALID");
  return text;
}

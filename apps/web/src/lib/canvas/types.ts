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
  const document = asRecord(record.document, "CANVAS_DOCUMENT_INVALID") as unknown as DesignDocument;
  if (typeof document.document_id !== "string" || typeof document.root_id !== "string") {
    throw new Error("CANVAS_DOCUMENT_IDENTITY_INVALID");
  }
  if (!document.nodes || typeof document.nodes !== "object" || Array.isArray(document.nodes)) {
    throw new Error("CANVAS_DOCUMENT_NODES_INVALID");
  }
  const designDocumentId = requiredString(
    record.design_document_id ?? record.designDocumentId,
    "CANVAS_DOCUMENT_ID_REQUIRED",
  );
  if (document.document_id !== designDocumentId) {
    throw new Error("CANVAS_DOCUMENT_ID_MISMATCH");
  }
  const revision = positiveInteger(record.revision, "CANVAS_REVISION_INVALID");
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
  return {
    type: descriptor.type,
    target_ids: [...descriptor.targetIds],
    payload: structuredClone(descriptor.payload),
    ...(descriptor.reason ? { reason: descriptor.reason } : {}),
  };
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

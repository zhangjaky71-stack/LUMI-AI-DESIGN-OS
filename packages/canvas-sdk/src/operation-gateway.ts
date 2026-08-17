import { applyBatch, applyOperation, IrRuntimeError, type ConstraintPreflight, type DesignDocument, type DesignOperation, type IrIssue } from "../../design-ir/src/index";
import type { OperationCommitResult, OperationDescriptor } from "./types";

function documentVersion(document: DesignDocument): number {
  const value = document.metadata.document_version;
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : 0;
}

export class CanvasOperationGateway {
  private documentValue: DesignDocument;
  private sequence = 0;
  constructor(document: DesignDocument, private readonly preflight?: ConstraintPreflight) { this.documentValue = document; }
  get document(): DesignDocument { return this.documentValue; }
  get version(): number { return documentVersion(this.documentValue); }
  replaceDocument(document: DesignDocument): void { this.documentValue = document; }
  private materialize(descriptor: OperationDescriptor, expected: number, prefix: string): DesignOperation {
    const operationId = `${prefix}:${++this.sequence}`;
    return {
      operation_id: operationId,
      type: descriptor.type,
      target_ids: [...descriptor.targetIds],
      expected_document_version: expected,
      payload: structuredClone(descriptor.payload),
      ...(descriptor.reason ? { reason: descriptor.reason } : {}),
    };
  }
  commit(descriptor: OperationDescriptor, prefix = "canvas"): OperationCommitResult {
    const operation = this.materialize(descriptor, this.version, prefix);
    try {
      const execution = applyOperation(this.documentValue, operation, this.preflight);
      this.documentValue = execution.document;
      return { ok: true, document: execution.document, operationIds: execution.applied_operation_ids, issues: [] };
    } catch (error) { return this.failure(error, [operation.operation_id]); }
  }
  commitBatch(descriptors: readonly OperationDescriptor[], prefix = "canvas-batch"): OperationCommitResult {
    if (!descriptors.length) return { ok: true, document: this.documentValue, operationIds: [], issues: [] };
    const expected = this.version;
    const operations = descriptors.map((descriptor) => this.materialize(descriptor, expected, prefix));
    try {
      const execution = applyBatch(this.documentValue, operations, expected, `${prefix}:root:${++this.sequence}`, this.preflight);
      this.documentValue = execution.document;
      return { ok: true, document: execution.document, operationIds: execution.applied_operation_ids, issues: [] };
    } catch (error) { return this.failure(error, operations.map((operation) => operation.operation_id)); }
  }
  private failure(error: unknown, operationIds: readonly string[]): OperationCommitResult {
    const normalized = error instanceof Error ? error : new Error(String(error));
    const issues: IrIssue[] = error instanceof IrRuntimeError ? [{ code: error.code, message: error.message, node_ids: error.node_ids, ...(error.operation_id ? { operation_id: error.operation_id } : {}), ...(error.pointer ? { pointer: error.pointer } : {}) }] : [];
    return { ok: false, document: this.documentValue, operationIds, issues, error: normalized };
  }
}

import type { OperationDescriptor } from "@lumi/canvas-sdk";

import { api } from "@/lib/api/client";
import { tenantHeaders } from "@/lib/workspace/api";
import {
  type CanvasProjection,
  parseCanvasProjection,
  wireDescriptor,
} from "@/lib/canvas/types";

export async function getArtifactCanvas(
  organizationId: string,
  artifactVersionId: string,
): Promise<CanvasProjection> {
  const payload = await api.get<unknown>(
    `/api/v1/artifact-versions/${encodeURIComponent(artifactVersionId)}/canvas`,
    { headers: tenantHeaders(organizationId), cache: "no-store" },
  );
  return parseCanvasProjection(payload);
}

export async function getCanvasHead(
  organizationId: string,
  designDocumentId: string,
): Promise<CanvasProjection> {
  const payload = await api.get<unknown>(
    `/api/v1/design-documents/${encodeURIComponent(designDocumentId)}/canvas`,
    { headers: tenantHeaders(organizationId), cache: "no-store" },
  );
  return parseCanvasProjection(payload);
}

export async function saveCanvasCommands(
  organizationId: string,
  projection: CanvasProjection,
  descriptors: readonly OperationDescriptor[],
  clientBatchId: string,
): Promise<CanvasProjection> {
  if (!descriptors.length) return projection;
  const payload = await api.post<unknown>(
    `/api/v1/design-documents/${encodeURIComponent(projection.designDocumentId)}/commands`,
    {
      client_batch_id: clientBatchId,
      expected_design_document_version_id: projection.designDocumentVersionId,
      expected_version_number: projection.versionNumber,
      expected_revision: projection.revision,
      descriptors: descriptors.map(wireDescriptor),
    },
    {
      headers: tenantHeaders(organizationId, { "Idempotency-Key": clientBatchId }),
    },
  );
  const record = payload && typeof payload === "object" && !Array.isArray(payload)
    ? payload as Record<string, unknown>
    : null;
  if (!record) throw new Error("CANVAS_SAVE_RESPONSE_INVALID");
  return parseCanvasProjection(record.projection);
}

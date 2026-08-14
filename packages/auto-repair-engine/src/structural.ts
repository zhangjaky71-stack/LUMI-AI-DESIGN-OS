import { guardedExecute } from "../../design-constraints/src/index";
import type { StructuralMaterializerPort } from "./ports";
import type { CandidateMaterialization, RepairPlanItem, RepairSource } from "./types";

export class RepairExecutionError extends Error {}

export async function executeStructuralRepair(
  item: RepairPlanItem,
  source: RepairSource,
  materializer: StructuralMaterializerPort,
): Promise<CandidateMaterialization> {
  if (item.kind !== "STRUCTURAL_DESIGN_OP" || !item.operations?.length) throw new RepairExecutionError("AUTO_REPAIR_STRUCTURAL_OPERATIONS_REQUIRED");
  const guarded = guardedExecute(source.subject.design_document, item.operations, source.constraints);
  if (guarded.preflight.decision === "DENY" || !guarded.execution?.ok) throw new RepairExecutionError("AUTO_REPAIR_CONSTRAINT_PREFLIGHT_DENIED");
  const rendered = await materializer.materialize(guarded.execution.document, source);
  return {
    design_document: guarded.execution.document,
    rendered_asset_ref: rendered.rendered_asset_ref,
    content_hash: rendered.content_hash,
    constraint_snapshot_hash: rendered.constraint_snapshot_hash,
    actual_cost_usd: "0",
    ...(rendered.width !== undefined ? { width: rendered.width } : {}),
    ...(rendered.height !== undefined ? { height: rendered.height } : {}),
    ...(rendered.metadata ? { metadata: rendered.metadata } : {}),
  };
}

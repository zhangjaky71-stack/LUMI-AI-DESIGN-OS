import type {
  BrandComplianceValidator,
  ConstraintViolation,
  DesignConstraint,
  PostflightContext,
} from "../../design-constraints/src/types";
import type { BrandEvaluationContext } from "./types";
import { evaluateBrandCompliance } from "./runtime";

export interface BrandComplianceResolver {
  resolve(context: PostflightContext, constraint: DesignConstraint): Promise<BrandEvaluationContext>;
}

export class BrandConstraintAdapter implements BrandComplianceValidator {
  constructor(private readonly resolver: BrandComplianceResolver) {}

  async validate(context: PostflightContext, constraint: DesignConstraint): Promise<readonly ConstraintViolation[]> {
    if (constraint.type !== "REQUIRE_BRAND_COMPLIANCE" && constraint.type !== "LOCK_BRAND") return [];
    try {
      const brandContext = await this.resolver.resolve(context, constraint);
      const report = evaluateBrandCompliance(brandContext);
      return report.diagnostics.map((item): ConstraintViolation => ({
        constraint_id: constraint.id,
        type: constraint.type,
        severity: item.severity,
        validator: "NODE-43.BrandConstraintAdapter",
        reason_code: item.reason_code,
        ...(item.node_id ? { target_id: item.node_id } : {}),
        ...(item.score !== undefined ? { score: item.score } : {}),
        ...(item.expected !== undefined ? { expected: item.expected } : {}),
        ...(item.actual !== undefined ? { actual: item.actual } : {}),
        repair_hint: {
          brand_rule_id: item.rule_id,
          brand_rule_set_version: report.brand_rule_set_version,
          operation_ids: (item.repair_operations ?? []).map((operation) => operation.operation_id),
        },
      }));
    } catch (error) {
      return [{
        constraint_id: constraint.id,
        type: constraint.type,
        severity: constraint.severity,
        validator: "NODE-43.BrandConstraintAdapter",
        reason_code: "VALIDATION_UNAVAILABLE",
        actual: error instanceof Error ? error.message : "brand compliance unavailable",
        repair_hint: { retryable: true },
      }];
    }
  }
}

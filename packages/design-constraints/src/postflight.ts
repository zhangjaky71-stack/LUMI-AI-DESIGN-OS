import { aggregateViolations, postflightDecision } from "./aggregator";
import { isConstraintOverridden } from "./override";
import type {
  BrandComplianceValidator,
  ConstraintViolation,
  DesignConstraint,
  IdentitySimilarityValidator,
  PostflightContext,
  PostflightEvaluator,
  PostflightReport,
} from "./types";

function unavailable(constraint: DesignConstraint, validator: string): ConstraintViolation {
  return {
    constraint_id: constraint.id,
    type: constraint.type,
    severity: constraint.severity,
    validator,
    reason_code: "VALIDATION_UNAVAILABLE",
    repair_hint: { action: "retry_or_manual_review" },
  };
}

export class DelegatingBrandEvaluator implements PostflightEvaluator {
  readonly name = "brand-compliance";
  readonly supported_types = ["LOCK_BRAND", "REQUIRE_BRAND_COMPLIANCE"] as const;
  readonly supports_preflight = false;
  readonly supports_postflight = true;

  constructor(private readonly validator: BrandComplianceValidator) {}

  evaluate(context: PostflightContext, constraint: DesignConstraint) {
    return this.validator.validate(context, constraint);
  }
}

export class DelegatingIdentityEvaluator implements PostflightEvaluator {
  readonly name = "identity-similarity";
  readonly supported_types = ["LOCK_IDENTITY", "REQUIRE_IDENTITY_SCORE"] as const;
  readonly supports_preflight = false;
  readonly supports_postflight = true;

  constructor(private readonly validator: IdentitySimilarityValidator) {}

  evaluate(context: PostflightContext, constraint: DesignConstraint) {
    return this.validator.validate(context, constraint);
  }
}

export class ConstraintPostflightRuntime {
  constructor(private readonly evaluators: readonly PostflightEvaluator[]) {}

  async validate(context: PostflightContext): Promise<PostflightReport> {
    const violations: ConstraintViolation[] = [];
    const unavailableValidators = new Set<string>();

    for (const constraint of context.constraints.filter((item) => item.active)) {
      if (isConstraintOverridden(context.document, constraint, context.overrides)) continue;
      const matching = this.evaluators.filter(
        (evaluator) => evaluator.supports_postflight && evaluator.supported_types.includes(constraint.type),
      );
      if (!matching.length) {
        // Postflight-only or identity/quality hard requirements must fail closed when no validator exists.
        if (
          constraint.severity === "HARD" &&
          [
            "PROTECT_REGION",
            "REQUIRE_SCANNABILITY",
            "LOCK_IDENTITY",
            "REQUIRE_IDENTITY_SCORE",
            "REQUIRE_BRAND_COMPLIANCE",
            "REQUIRE_CONTRAST",
            "REQUIRE_TEXT_READABILITY",
            "REQUIRE_RESOLUTION",
          ].includes(constraint.type)
        ) {
          unavailableValidators.add(`missing:${constraint.type}`);
          violations.push(unavailable(constraint, `missing:${constraint.type}`));
        }
        continue;
      }
      for (const evaluator of matching) {
        try {
          violations.push(...(await evaluator.evaluate(context, constraint)));
        } catch {
          unavailableValidators.add(evaluator.name);
          if (constraint.severity === "HARD") violations.push(unavailable(constraint, evaluator.name));
        }
      }
    }

    const aggregated = aggregateViolations(violations);
    return {
      decision: postflightDecision(aggregated),
      violations: aggregated,
      unavailable_validators: [...unavailableValidators].sort(),
    };
  }
}

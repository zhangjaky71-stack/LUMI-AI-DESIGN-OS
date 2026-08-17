export interface ConstraintEvaluation {
  readonly constraintId: string;
  readonly passed: boolean;
  readonly message?: string;
}

export * from "./validator/index";

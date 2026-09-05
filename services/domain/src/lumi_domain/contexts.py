from enum import StrEnum


class BoundedContext(StrEnum):
    IDENTITY_TENANCY = "identity_tenancy"
    WORKSPACE_PROJECT = "workspace_project"
    BRAND = "brand"
    ASSET = "asset"
    DESIGN = "design"
    ARTIFACT_VERSION = "artifact_version"
    AGENT_EXECUTION = "agent_execution"
    WORKFLOW_TASK = "workflow_task"
    GENERATION_PROVIDER = "generation_provider"
    BILLING_COST = "billing_cost"
    COLLABORATION = "collaboration"
    AUDIT_GOVERNANCE = "audit_governance"

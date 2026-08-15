DROP TABLE assets;

-- statement-breakpoint

DROP TABLE project_members;

-- statement-breakpoint

DROP TABLE projects;

-- statement-breakpoint

DROP TABLE brand_rules;

-- statement-breakpoint

DROP TABLE brand_logos;

-- statement-breakpoint

DROP TABLE brand_fonts;

-- statement-breakpoint

DROP TABLE brand_palettes;

-- statement-breakpoint

DROP TABLE workspace_members;

-- statement-breakpoint

DROP TABLE audit_events;

-- statement-breakpoint

DROP TABLE inbox_events;

-- statement-breakpoint

DROP TABLE outbox_events;

-- statement-breakpoint

DROP TABLE usage_counters;

-- statement-breakpoint

DROP TABLE idempotency_operations;

-- statement-breakpoint

DROP TABLE brands;

-- statement-breakpoint

DROP TABLE auth_identities;

-- statement-breakpoint

DROP TABLE workspaces;

-- statement-breakpoint

DROP TABLE organization_members;

-- statement-breakpoint

DROP TABLE organizations;

-- statement-breakpoint

DROP TABLE users;

-- statement-breakpoint

DROP FUNCTION IF EXISTS lumi_current_organization_id();

-- statement-breakpoint

DROP FUNCTION IF EXISTS lumi_enforce_same_tenant_fk();

-- statement-breakpoint

DROP FUNCTION IF EXISTS lumi_reject_artifact_edge_cycle();

-- statement-breakpoint

DROP FUNCTION IF EXISTS lumi_reject_task_dependency_cycle();

-- statement-breakpoint

DROP FUNCTION IF EXISTS lumi_protect_artifact_version_history();

-- statement-breakpoint

DROP FUNCTION IF EXISTS lumi_forbid_mutation();

-- statement-breakpoint

DROP FUNCTION IF EXISTS lumi_set_updated_at();

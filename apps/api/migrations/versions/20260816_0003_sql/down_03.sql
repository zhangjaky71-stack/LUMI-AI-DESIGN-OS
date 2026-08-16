DROP TRIGGER IF EXISTS trg_agent_run_project_context_same_tenant ON agent_run_project_context;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_project_summaries_same_tenant ON project_summaries;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_project_branch_defaults_same_tenant ON project_branch_defaults;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_project_brief_versions_same_tenant ON project_brief_versions;

-- statement-breakpoint

DROP FUNCTION IF EXISTS lumi_project_core_same_tenant_guard();

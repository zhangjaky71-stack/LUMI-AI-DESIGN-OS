DROP TRIGGER IF EXISTS trg_generations_project_paid_command_guard ON generations;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_agent_runs_project_paid_command_guard ON agent_runs;

-- statement-breakpoint

DROP FUNCTION IF EXISTS lumi_require_project_accepts_paid_command();

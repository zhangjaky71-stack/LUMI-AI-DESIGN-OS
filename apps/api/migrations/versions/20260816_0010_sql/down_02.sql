DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM agent_run_control LIMIT 1) THEN
    RAISE EXCEPTION 'NODE-28 downgrade refused: durable AgentRun control state exists';
  END IF;
  IF EXISTS (SELECT 1 FROM agent_graph_definitions LIMIT 1) THEN
    RAISE EXCEPTION 'NODE-28 downgrade refused: published graph definitions exist';
  END IF;
  IF EXISTS (
    SELECT 1 FROM agent_runs
    WHERE graph_key <> 'lumi.main'
       OR code_git_sha <> 'unknown'
       OR status = 'waiting_external'
       OR length(thread_id) > 200
       OR length(graph_version) > 80
       OR length(agent_config_version) > 80
    LIMIT 1
  ) THEN
    RAISE EXCEPTION 'NODE-28 downgrade refused: AgentRun contains NODE-28-only state';
  END IF;
END;
$$;

-- statement-breakpoint

DROP POLICY IF EXISTS tenant_isolation_agent_run_control ON agent_run_control;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_agent_run_control_graph_definition ON agent_run_control;

-- statement-breakpoint

DROP FUNCTION IF EXISTS lumi_validate_agent_run_graph_definition();

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_agent_run_control_same_tenant ON agent_run_control;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_agent_run_control_updated_at ON agent_run_control;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_agent_graph_definitions_updated_at ON agent_graph_definitions;

-- statement-breakpoint

DROP TABLE agent_run_control;

-- statement-breakpoint

DROP TABLE agent_graph_definitions;

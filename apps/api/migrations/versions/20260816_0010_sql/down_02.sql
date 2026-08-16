DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM agent_run_control LIMIT 1) THEN
    RAISE EXCEPTION 'NODE-28 downgrade refused: durable AgentRun control state exists';
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

ALTER TABLE agent_runs
  ADD COLUMN graph_key VARCHAR(128) NOT NULL DEFAULT 'lumi.main',
  ADD COLUMN code_git_sha VARCHAR(80) NOT NULL DEFAULT 'unknown';

-- statement-breakpoint

ALTER TABLE agent_runs DROP CONSTRAINT IF EXISTS ck_agent_runs_status;

-- statement-breakpoint

ALTER TABLE agent_runs
  ADD CONSTRAINT ck_agent_runs_status CHECK (
    status IN (
      'pending','running','waiting_user','waiting_external','cancel_requested',
      'cancelled','paused','succeeded','failed'
    )
  );

-- statement-breakpoint

CREATE TABLE agent_graph_definitions (
  id UUID PRIMARY KEY,
  graph_key VARCHAR(128) NOT NULL,
  graph_version VARCHAR(100) NOT NULL,
  agent_config_version VARCHAR(100) NOT NULL,
  code_git_sha VARCHAR(80) NOT NULL,
  description VARCHAR(1000) NOT NULL,
  state_schema_version INTEGER NOT NULL,
  content_hash CHAR(64) NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT true,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_agent_graph_definitions_identity UNIQUE (graph_key, graph_version),
  CONSTRAINT ck_agent_graph_definitions_hash CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  CONSTRAINT ck_agent_graph_definitions_schema_version CHECK (state_schema_version >= 1),
  CONSTRAINT ck_agent_graph_definitions_metadata_size
    CHECK (octet_length(metadata_json::text) <= 262144)
);

-- statement-breakpoint

CREATE INDEX ix_agent_graph_definitions_enabled
  ON agent_graph_definitions (enabled, graph_key, graph_version);

-- statement-breakpoint

CREATE TABLE agent_run_control (
  agent_run_id UUID PRIMARY KEY REFERENCES agent_runs(id) ON DELETE CASCADE,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
  graph_key VARCHAR(128) NOT NULL,
  graph_version VARCHAR(100) NOT NULL,
  code_git_sha VARCHAR(80) NOT NULL,
  graph_definition_hash CHAR(64) NOT NULL,
  thread_id VARCHAR(255) NOT NULL,
  control_status VARCHAR(32) NOT NULL,
  checkpoint_id VARCHAR(512),
  checkpoint_namespace VARCHAR(1024) NOT NULL DEFAULT '',
  state_values_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  next_nodes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  interrupts_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  resume_version INTEGER NOT NULL DEFAULT 1,
  error_code VARCHAR(128),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  version INTEGER NOT NULL DEFAULT 1,
  CONSTRAINT uq_agent_run_control_thread UNIQUE (organization_id, thread_id),
  CONSTRAINT ck_agent_run_control_hash CHECK (graph_definition_hash ~ '^[0-9a-f]{64}$'),
  CONSTRAINT ck_agent_run_control_status CHECK (
    control_status IN (
      'pending','running','waiting_user','waiting_external','succeeded','failed','cancelled'
    )
  ),
  CONSTRAINT ck_agent_run_control_resume_version CHECK (resume_version >= 1),
  CONSTRAINT ck_agent_run_control_version CHECK (version >= 1),
  CONSTRAINT ck_agent_run_control_state_size
    CHECK (octet_length(state_values_json::text) <= 1048576),
  CONSTRAINT ck_agent_run_control_next_size
    CHECK (octet_length(next_nodes_json::text) <= 65536),
  CONSTRAINT ck_agent_run_control_interrupt_size
    CHECK (octet_length(interrupts_json::text) <= 262144)
);

-- statement-breakpoint

CREATE INDEX ix_agent_run_control_org_status
  ON agent_run_control (organization_id, control_status, updated_at);

-- statement-breakpoint

CREATE INDEX ix_agent_run_control_project_status
  ON agent_run_control (project_id, control_status, updated_at);

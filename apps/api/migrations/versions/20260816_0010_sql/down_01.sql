ALTER TABLE agent_runs DROP CONSTRAINT IF EXISTS ck_agent_runs_status;

-- statement-breakpoint

ALTER TABLE agent_runs
  ADD CONSTRAINT ck_agent_runs_status CHECK (
    status IN (
      'pending','running','waiting_user','cancel_requested','cancelled',
      'paused','succeeded','failed'
    )
  );

-- statement-breakpoint

ALTER TABLE agent_runs
  DROP COLUMN code_git_sha,
  DROP COLUMN graph_key;

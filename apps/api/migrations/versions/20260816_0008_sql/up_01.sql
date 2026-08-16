CREATE TABLE provider_health_summaries (
  id UUID PRIMARY KEY,
  provider VARCHAR(128) NOT NULL,
  model VARCHAR(255),
  capability VARCHAR(128),
  state VARCHAR(32) NOT NULL,
  score INTEGER NOT NULL,
  sample_count INTEGER NOT NULL,
  success_rate NUMERIC(7,6) NOT NULL,
  failure_rate NUMERIC(7,6) NOT NULL,
  rate_limit_rate NUMERIC(7,6) NOT NULL,
  timeout_rate NUMERIC(7,6) NOT NULL,
  latency_p50_ms INTEGER,
  latency_p95_ms INTEGER,
  queue_completion_p95_ms INTEGER,
  consecutive_failures INTEGER NOT NULL,
  observed_at TIMESTAMP WITH TIME ZONE NOT NULL,
  source_instance VARCHAR(255),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  CONSTRAINT ck_provider_health_summary_state CHECK (
    state IN (
      'unknown',
      'healthy',
      'degraded',
      'open_circuit',
      'recovering',
      'disabled'
    )
  ),
  CONSTRAINT ck_provider_health_summary_score CHECK (score BETWEEN 0 AND 100),
  CONSTRAINT ck_provider_health_summary_sample_count CHECK (sample_count >= 0),
  CONSTRAINT ck_provider_health_summary_success_rate CHECK (
    success_rate BETWEEN 0 AND 1
  ),
  CONSTRAINT ck_provider_health_summary_failure_rate CHECK (
    failure_rate BETWEEN 0 AND 1
  ),
  CONSTRAINT ck_provider_health_summary_rate_limit_rate CHECK (
    rate_limit_rate BETWEEN 0 AND 1
  ),
  CONSTRAINT ck_provider_health_summary_timeout_rate CHECK (
    timeout_rate BETWEEN 0 AND 1
  ),
  CONSTRAINT ck_provider_health_summary_latency_p50 CHECK (
    latency_p50_ms IS NULL OR latency_p50_ms >= 0
  ),
  CONSTRAINT ck_provider_health_summary_latency_p95 CHECK (
    latency_p95_ms IS NULL OR latency_p95_ms >= 0
  ),
  CONSTRAINT ck_provider_health_summary_queue_p95 CHECK (
    queue_completion_p95_ms IS NULL OR queue_completion_p95_ms >= 0
  ),
  CONSTRAINT ck_provider_health_summary_consecutive CHECK (
    consecutive_failures >= 0
  ),
  CONSTRAINT ck_provider_health_summary_capability_scope CHECK (
    capability IS NULL OR model IS NOT NULL
  )
);

-- statement-breakpoint

CREATE INDEX ix_provider_health_summary_scope_observed
ON provider_health_summaries (
  provider,
  model,
  capability,
  observed_at DESC
);

-- statement-breakpoint

CREATE INDEX ix_provider_health_summary_state_observed
ON provider_health_summaries (state, observed_at DESC);

-- statement-breakpoint

CREATE TABLE provider_health_override_audit (
  id UUID PRIMARY KEY,
  action VARCHAR(64) NOT NULL,
  provider VARCHAR(128) NOT NULL,
  model VARCHAR(255),
  capability VARCHAR(128),
  actor_id VARCHAR(255) NOT NULL,
  reason TEXT NOT NULL,
  observed_at TIMESTAMP WITH TIME ZONE NOT NULL,
  expires_at TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  CONSTRAINT ck_provider_health_audit_action CHECK (
    action IN (
      'force_disabled',
      'force_degraded',
      'clear_override',
      'clear_breaker'
    )
  ),
  CONSTRAINT ck_provider_health_audit_actor CHECK (length(btrim(actor_id)) > 0),
  CONSTRAINT ck_provider_health_audit_reason CHECK (length(btrim(reason)) > 0),
  CONSTRAINT ck_provider_health_audit_capability_scope CHECK (
    capability IS NULL OR model IS NOT NULL
  ),
  CONSTRAINT ck_provider_health_audit_expiry CHECK (
    expires_at IS NULL OR expires_at > observed_at
  )
);

-- statement-breakpoint

CREATE INDEX ix_provider_health_audit_scope_observed
ON provider_health_override_audit (
  provider,
  model,
  capability,
  observed_at DESC
);

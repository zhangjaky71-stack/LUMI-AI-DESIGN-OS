ALTER TABLE outbox_events
  ADD COLUMN last_publish_attempt_at TIMESTAMPTZ NULL,
  ADD COLUMN next_publish_at TIMESTAMPTZ NULL,
  ADD COLUMN last_publish_error TEXT NULL;

-- statement-breakpoint

CREATE INDEX ix_outbox_events_due
ON outbox_events (organization_id, next_publish_at, created_at)
WHERE published_at IS NULL;

-- statement-breakpoint

CREATE TABLE runtime_jobs (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  job_kind VARCHAR(80) NOT NULL,
  operation_id UUID NULL,
  resource_id UUID NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  attempt_count INTEGER NOT NULL DEFAULT 0,
  max_attempts INTEGER NOT NULL DEFAULT 3,
  traceparent VARCHAR(128) NULL,
  input_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  output_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  cancellation_requested_at TIMESTAMPTZ NULL,
  started_at TIMESTAMPTZ NULL,
  finished_at TIMESTAMPTZ NULL,
  next_retry_at TIMESTAMPTZ NULL,
  error_category VARCHAR(32) NULL,
  error_code VARCHAR(128) NULL,
  error_message TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  version INTEGER NOT NULL DEFAULT 1,
  CONSTRAINT ck_runtime_jobs_job_kind CHECK (
    job_kind IN ('image.transform','video.render','asset.preview','asset.validate','export.package')
  ),
  CONSTRAINT ck_runtime_jobs_status CHECK (
    status IN ('pending','running','retrying','succeeded','failed','cancelled')
  ),
  CONSTRAINT ck_runtime_jobs_attempts CHECK (attempt_count >= 0 AND max_attempts >= 1),
  CONSTRAINT ck_runtime_jobs_error_category CHECK (
    error_category IS NULL OR error_category IN ('transient','permanent','cancelled')
  ),
  CONSTRAINT ck_runtime_jobs_version_positive CHECK (version > 0)
);

-- statement-breakpoint

CREATE INDEX ix_runtime_jobs_due
ON runtime_jobs (organization_id, status, next_retry_at);

-- statement-breakpoint

CREATE INDEX ix_runtime_jobs_project_status
ON runtime_jobs (project_id, status);

-- statement-breakpoint

CREATE TABLE dead_letter_records (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
  message_id UUID NOT NULL,
  message_kind VARCHAR(32) NOT NULL,
  source_queue VARCHAR(200) NOT NULL,
  consumer VARCHAR(160) NULL,
  exchange_name VARCHAR(160) NOT NULL,
  routing_key VARCHAR(200) NOT NULL,
  error_category VARCHAR(32) NOT NULL,
  error_code VARCHAR(128) NOT NULL,
  error_message TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 1,
  traceparent VARCHAR(128) NULL,
  payload_json JSONB NOT NULL,
  first_failed_at TIMESTAMPTZ NOT NULL,
  last_failed_at TIMESTAMPTZ NOT NULL,
  replayed_at TIMESTAMPTZ NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'open',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  version INTEGER NOT NULL DEFAULT 1,
  CONSTRAINT ck_dead_letter_records_message_kind CHECK (message_kind IN ('domain_event','job')),
  CONSTRAINT ck_dead_letter_records_error_category CHECK (
    error_category IN ('transient','permanent','cancelled')
  ),
  CONSTRAINT ck_dead_letter_records_attempts_positive CHECK (attempts >= 1),
  CONSTRAINT ck_dead_letter_records_status CHECK (status IN ('open','replayed','discarded')),
  CONSTRAINT ck_dead_letter_records_version_positive CHECK (version > 0)
);

-- statement-breakpoint

CREATE INDEX ix_dead_letter_records_org_status
ON dead_letter_records (organization_id, status, updated_at);

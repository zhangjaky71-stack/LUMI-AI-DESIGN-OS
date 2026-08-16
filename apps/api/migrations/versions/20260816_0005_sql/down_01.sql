DROP INDEX IF EXISTS ix_dead_letter_records_org_status;

-- statement-breakpoint

DROP TABLE IF EXISTS dead_letter_records;

-- statement-breakpoint

DROP INDEX IF EXISTS ix_runtime_jobs_project_status;

-- statement-breakpoint

DROP INDEX IF EXISTS ix_runtime_jobs_due;

-- statement-breakpoint

DROP TABLE IF EXISTS runtime_jobs;

-- statement-breakpoint

DROP INDEX IF EXISTS ix_outbox_events_due;

-- statement-breakpoint

ALTER TABLE outbox_events
  DROP COLUMN IF EXISTS last_publish_error,
  DROP COLUMN IF EXISTS next_publish_at,
  DROP COLUMN IF EXISTS last_publish_attempt_at;

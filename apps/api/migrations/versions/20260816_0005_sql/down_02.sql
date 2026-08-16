DROP POLICY IF EXISTS tenant_isolation_dead_letter_records ON dead_letter_records;

-- statement-breakpoint

DROP POLICY IF EXISTS tenant_isolation_runtime_jobs ON runtime_jobs;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_runtime_jobs_same_tenant ON runtime_jobs;

-- statement-breakpoint

DROP FUNCTION IF EXISTS lumi_queue_runtime_same_tenant_guard();

DROP TRIGGER IF EXISTS trg_image_generation_candidate_tenant ON image_generation_candidates;

-- statement-breakpoint

DROP FUNCTION IF EXISTS enforce_image_generation_tenant_scope();

-- statement-breakpoint

DROP TABLE IF EXISTS image_generation_cost_projection;

-- statement-breakpoint

DROP TABLE IF EXISTS image_generation_pending;

-- statement-breakpoint

DROP TABLE IF EXISTS image_generation_candidates;

-- statement-breakpoint

DROP TABLE IF EXISTS image_generation_jobs;

-- statement-breakpoint

DROP TABLE IF EXISTS image_generation_specs;

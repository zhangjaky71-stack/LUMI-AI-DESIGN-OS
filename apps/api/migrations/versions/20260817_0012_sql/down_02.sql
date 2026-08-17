DROP TRIGGER IF EXISTS trg_capture_agent_run_brand_rule_set ON agent_runs;

-- statement-breakpoint

DROP FUNCTION IF EXISTS lumi_capture_agent_run_brand_rule_set();

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_capture_artifact_brand_rule_set ON artifact_versions;

-- statement-breakpoint

DROP FUNCTION IF EXISTS lumi_capture_artifact_brand_rule_set();

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_validate_active_brand_rule_set ON brands;

-- statement-breakpoint

DROP FUNCTION IF EXISTS lumi_validate_active_brand_rule_set();

-- statement-breakpoint

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM artifact_versions
        WHERE brand_rule_set_version_id IS NOT NULL
    ) OR EXISTS (
        SELECT 1 FROM agent_runs
        WHERE brand_rule_set_version_id IS NOT NULL
    ) OR EXISTS (
        SELECT 1 FROM brands
        WHERE active_rule_set_version_id IS NOT NULL
    ) THEN
        RAISE EXCEPTION
            'NODE-43 downgrade blocked: exact brand rule version references exist';
    END IF;
END
$$;

-- statement-breakpoint

DROP INDEX IF EXISTS ix_brands_active_rule_set_version_id;

-- statement-breakpoint

DROP INDEX IF EXISTS ix_agent_runs_brand_rule_set_version_id;

-- statement-breakpoint

DROP INDEX IF EXISTS ix_artifact_versions_brand_rule_set_version_id;

-- statement-breakpoint

ALTER TABLE agent_runs
DROP CONSTRAINT IF EXISTS
fk_agent_runs_brand_rule_set_version_id_brand_rule_set_versions;

-- statement-breakpoint

ALTER TABLE artifact_versions
DROP CONSTRAINT IF EXISTS
fk_artifact_versions_brand_rule_set_version_id_brand_rule_set_versions;

-- statement-breakpoint

ALTER TABLE brands
DROP CONSTRAINT IF EXISTS
fk_brands_active_rule_set_version_id_brand_rule_set_versions;

-- statement-breakpoint

ALTER TABLE agent_runs DROP COLUMN IF EXISTS brand_rule_set_version_id;

-- statement-breakpoint

ALTER TABLE artifact_versions DROP COLUMN IF EXISTS brand_rule_set_version_id;

-- statement-breakpoint

ALTER TABLE brands DROP COLUMN IF EXISTS active_rule_set_version_id;

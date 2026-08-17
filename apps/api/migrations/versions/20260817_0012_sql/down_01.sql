DROP TRIGGER IF EXISTS trg_brand_rule_set_snapshot_immutable
ON brand_rule_set_versions;

-- statement-breakpoint

DROP FUNCTION IF EXISTS lumi_brand_rules_immutable_snapshot();

-- statement-breakpoint

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM brand_rule_set_versions)
       OR EXISTS (SELECT 1 FROM brand_guide_proposals) THEN
        RAISE EXCEPTION
            'NODE-43 downgrade blocked: Brand Rules Engine data exists';
    END IF;
END
$$;

-- statement-breakpoint

DROP INDEX IF EXISTS ix_brand_rule_set_versions_org_brand_status;

-- statement-breakpoint

DROP TABLE brand_rule_set_versions;

-- statement-breakpoint

DROP TABLE brand_rule_version_counters;

-- statement-breakpoint

DROP INDEX IF EXISTS ix_brand_guide_proposals_org_brand;

-- statement-breakpoint

DROP TABLE brand_guide_proposals;

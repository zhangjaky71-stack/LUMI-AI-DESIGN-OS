DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM identity_validation_records)
       OR EXISTS (SELECT 1 FROM identity_reference_set_versions)
       OR EXISTS (SELECT 1 FROM identity_calibration_reports) THEN
        RAISE EXCEPTION 'NODE-44 downgrade blocked: identity evidence exists';
    END IF;
END
$$;

-- statement-breakpoint

DROP TABLE identity_calibration_reports;

-- statement-breakpoint

DROP TABLE identity_validation_records;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_identity_snapshot_immutable ON identity_reference_set_versions;

-- statement-breakpoint

DROP FUNCTION IF EXISTS lumi_identity_snapshot_immutable();

-- statement-breakpoint

DROP TABLE identity_reference_set_versions;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_identity_scope_tenant_guard ON identity_reference_sets;

-- statement-breakpoint

DROP FUNCTION IF EXISTS lumi_identity_scope_tenant_guard();

-- statement-breakpoint

DROP TABLE identity_reference_sets;

-- statement-breakpoint

DROP TABLE identity_version_counters;

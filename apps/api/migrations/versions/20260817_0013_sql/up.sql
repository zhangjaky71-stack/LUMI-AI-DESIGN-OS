CREATE TABLE identity_reference_sets (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    project_id uuid NULL REFERENCES projects(id) ON DELETE CASCADE,
    brand_id uuid NULL REFERENCES brands(id) ON DELETE CASCADE,
    identity_type varchar(32) NOT NULL,
    name varchar(240) NOT NULL,
    created_by varchar(200) NOT NULL,
    privacy_authorized boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_identity_reference_sets_type CHECK (
        identity_type IN ('PRODUCT','LOGO','CHARACTER','FACE','STYLE_REFERENCE')
    ),
    CONSTRAINT ck_identity_reference_sets_face_scope CHECK (
        identity_type <> 'FACE' OR
        (project_id IS NOT NULL AND brand_id IS NULL AND privacy_authorized)
    )
);

-- statement-breakpoint

CREATE INDEX ix_identity_reference_sets_org_type
ON identity_reference_sets(organization_id, identity_type, created_at DESC);

-- statement-breakpoint

CREATE FUNCTION lumi_identity_scope_tenant_guard()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.project_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM projects
        WHERE id = NEW.project_id AND organization_id = NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'identity project scope must belong to the same organization';
    END IF;
    IF NEW.brand_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM brands
        WHERE id = NEW.brand_id AND organization_id = NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'identity brand scope must belong to the same organization';
    END IF;
    RETURN NEW;
END
$$;

-- statement-breakpoint

CREATE TRIGGER trg_identity_scope_tenant_guard
BEFORE INSERT OR UPDATE ON identity_reference_sets
FOR EACH ROW EXECUTE FUNCTION lumi_identity_scope_tenant_guard();

-- statement-breakpoint

CREATE TABLE identity_version_counters (
    identity_id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    next_version integer NOT NULL CHECK (next_version >= 2)
);

-- statement-breakpoint

CREATE INDEX ix_identity_version_counters_org
ON identity_version_counters(organization_id);

-- statement-breakpoint

CREATE TABLE identity_reference_set_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    identity_id uuid NOT NULL REFERENCES identity_reference_sets(id) ON DELETE CASCADE,
    version_number integer NOT NULL CHECK (version_number > 0),
    snapshot_hash varchar(64) NOT NULL CHECK (snapshot_hash ~ '^[0-9a-f]{64}$'),
    canonical_asset_ids_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    reference_views_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    threshold_profile_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    notes text NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_identity_ref_version UNIQUE(identity_id, version_number)
);

-- statement-breakpoint

CREATE INDEX ix_identity_ref_versions_org_identity
ON identity_reference_set_versions(organization_id, identity_id, version_number DESC);

-- statement-breakpoint

CREATE FUNCTION lumi_identity_snapshot_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'identity reference versions are immutable';
END
$$;

-- statement-breakpoint

CREATE TRIGGER trg_identity_snapshot_immutable
BEFORE UPDATE OR DELETE ON identity_reference_set_versions
FOR EACH ROW EXECUTE FUNCTION lumi_identity_snapshot_immutable();

-- statement-breakpoint

CREATE TABLE identity_validation_records (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    identity_version_id uuid NOT NULL REFERENCES identity_reference_set_versions(id) ON DELETE CASCADE,
    candidate_asset_id uuid NULL REFERENCES assets(id) ON DELETE SET NULL,
    node_id varchar(200) NULL,
    status varchar(32) NOT NULL,
    identity_score numeric(8,4) NULL,
    confidence numeric(8,6) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    threshold_profile_json jsonb NOT NULL,
    signal_scores_json jsonb NOT NULL,
    region_json jsonb NULL,
    evidence_refs_json jsonb NOT NULL,
    failure_codes_json jsonb NOT NULL,
    provider_version varchar(160) NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_identity_validation_status CHECK (
        status IN ('PASS','WARN','BLOCKED','REVIEW_REQUIRED','VALIDATION_UNAVAILABLE')
    )
);

-- statement-breakpoint

CREATE INDEX ix_identity_validation_identity_created
ON identity_validation_records(identity_version_id, created_at DESC);

-- statement-breakpoint

CREATE TABLE identity_calibration_reports (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    identity_type varchar(32) NOT NULL,
    profile_key varchar(120) NOT NULL,
    version_number integer NOT NULL CHECK (version_number > 0),
    dataset_hash varchar(64) NOT NULL CHECK (dataset_hash ~ '^[0-9a-f]{64}$'),
    selected_threshold numeric(8,4) NOT NULL CHECK (selected_threshold >= 0 AND selected_threshold <= 100),
    target_precision numeric(8,6) NOT NULL CHECK (target_precision >= 0 AND target_precision <= 1),
    metrics_json jsonb NOT NULL,
    sample_count integer NOT NULL CHECK (sample_count > 0),
    created_at timestamptz NOT NULL,
    CONSTRAINT uq_identity_calibration_profile_version UNIQUE(
        organization_id, identity_type, profile_key, version_number
    )
);

-- statement-breakpoint

CREATE INDEX ix_identity_calibration_org_type
ON identity_calibration_reports(organization_id, identity_type, profile_key, version_number DESC);

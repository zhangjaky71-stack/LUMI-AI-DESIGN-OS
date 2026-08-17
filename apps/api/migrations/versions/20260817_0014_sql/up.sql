CREATE TABLE asset_intelligence_index_counters (
    organization_id uuid PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
    next_version integer NOT NULL CHECK (next_version > 0)
);

-- statement-breakpoint

CREATE TABLE asset_intelligence_indexes (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    version_number integer NOT NULL CHECK (version_number > 0),
    analyzer_version varchar(160) NOT NULL,
    embedding_model_key varchar(255) NOT NULL,
    embedding_revision_key varchar(255) NOT NULL,
    embedding_version varchar(80) NOT NULL,
    embedding_dimensions integer NOT NULL CHECK (embedding_dimensions > 0),
    embedding_space_id varchar(320) NOT NULL,
    registry_version_id uuid NOT NULL REFERENCES model_registry_versions(id) ON DELETE RESTRICT,
    state varchar(24) NOT NULL CHECK (
        state IN ('BUILDING','READY','ACTIVE','RETIRED','FAILED')
    ),
    coverage_count integer NOT NULL DEFAULT 0 CHECK (coverage_count >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    activated_at timestamptz NULL,
    CONSTRAINT uq_asset_intelligence_index_version UNIQUE(organization_id, version_number)
);

-- statement-breakpoint

CREATE UNIQUE INDEX uq_asset_intelligence_one_active_per_org
ON asset_intelligence_indexes(organization_id)
WHERE state='ACTIVE';

-- statement-breakpoint

CREATE INDEX ix_asset_intelligence_indexes_org_state
ON asset_intelligence_indexes(organization_id, state, version_number DESC);

-- statement-breakpoint

CREATE TABLE asset_intelligence_analysis (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    asset_version varchar(64) NOT NULL CHECK (asset_version ~ '^[0-9a-f]{64}$'),
    project_id uuid NULL REFERENCES projects(id) ON DELETE SET NULL,
    brand_id uuid NULL REFERENCES brands(id) ON DELETE SET NULL,
    index_id uuid NOT NULL REFERENCES asset_intelligence_indexes(id) ON DELETE CASCADE,
    index_version integer NOT NULL CHECK (index_version > 0),
    state varchar(24) NOT NULL CHECK (
        state IN ('READY','STALE','DELETING','DELETED','FAILED')
    ),
    checksum_sha256 varchar(64) NOT NULL CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
    source varchar(80) NOT NULL,
    mime_type varchar(255) NOT NULL,
    media_kind varchar(64) NOT NULL,
    rights_level varchar(32) NOT NULL CHECK (
        rights_level IN ('unknown','owned','licensed','public_domain','restricted')
    ),
    commercial_use boolean NOT NULL DEFAULT false,
    training_authorized boolean NOT NULL DEFAULT false,
    permission_tags_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    preview_ref text NULL,
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    ocr_spans_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    regions_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    semantic_description text NULL,
    visual_tags_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    embedding_id uuid NULL REFERENCES asset_embeddings(id) ON DELETE SET NULL,
    perceptual_hash varchar(256) NULL,
    language varchar(32) NULL,
    local_signature_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    color_signature_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    brand_region_signature_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    analyzer_version varchar(160) NOT NULL,
    embedding_model_key varchar(255) NOT NULL,
    embedding_revision_key varchar(255) NOT NULL,
    embedding_version varchar(80) NOT NULL,
    registry_version_id uuid NOT NULL REFERENCES model_registry_versions(id) ON DELETE RESTRICT,
    evidence_refs_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz NULL,
    error_code varchar(160) NULL,
    CONSTRAINT uq_asset_intelligence_analysis_asset_index
        UNIQUE(organization_id, asset_id, index_id)
);

-- statement-breakpoint

CREATE INDEX ix_asset_intelligence_analysis_scope
ON asset_intelligence_analysis(
    organization_id, index_id, state, project_id, brand_id, rights_level
);

-- statement-breakpoint

CREATE INDEX ix_asset_intelligence_analysis_asset
ON asset_intelligence_analysis(organization_id, asset_id, index_id);

-- statement-breakpoint

CREATE INDEX ix_asset_intelligence_analysis_tags_gin
ON asset_intelligence_analysis USING gin(visual_tags_json);

-- statement-breakpoint

CREATE FUNCTION lumi_asset_intelligence_scope_guard()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM assets
        WHERE id=NEW.asset_id AND organization_id=NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'asset intelligence asset must belong to same organization';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM asset_intelligence_indexes
        WHERE id=NEW.index_id AND organization_id=NEW.organization_id
          AND version_number=NEW.index_version
    ) THEN
        RAISE EXCEPTION 'asset intelligence index must belong to same organization/version';
    END IF;
    IF NEW.project_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM projects
        WHERE id=NEW.project_id AND organization_id=NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'asset intelligence project must belong to same organization';
    END IF;
    IF NEW.brand_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM brands
        WHERE id=NEW.brand_id AND organization_id=NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'asset intelligence brand must belong to same organization';
    END IF;
    IF NEW.embedding_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM asset_embeddings
        WHERE id=NEW.embedding_id AND organization_id=NEW.organization_id
          AND asset_id=NEW.asset_id
    ) THEN
        RAISE EXCEPTION 'asset intelligence embedding must belong to same tenant/asset';
    END IF;
    RETURN NEW;
END
$$;

-- statement-breakpoint

CREATE TRIGGER trg_asset_intelligence_scope_guard
BEFORE INSERT OR UPDATE ON asset_intelligence_analysis
FOR EACH ROW EXECUTE FUNCTION lumi_asset_intelligence_scope_guard();

-- statement-breakpoint

CREATE TABLE asset_intelligence_usage_signals (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    project_id uuid NULL REFERENCES projects(id) ON DELETE SET NULL,
    signal varchar(24) NOT NULL CHECK (signal IN ('SELECTED','APPROVED','REJECTED')),
    actor_id varchar(200) NULL,
    training_authorization_granted boolean NOT NULL DEFAULT false
        CHECK (training_authorization_granted = false),
    occurred_at timestamptz NOT NULL
);

-- statement-breakpoint

CREATE INDEX ix_asset_intelligence_usage_asset_time
ON asset_intelligence_usage_signals(organization_id, asset_id, occurred_at DESC);

-- statement-breakpoint

CREATE FUNCTION lumi_asset_intelligence_usage_scope_guard()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM assets
        WHERE id=NEW.asset_id AND organization_id=NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'asset intelligence usage asset must belong to same organization';
    END IF;
    IF NEW.project_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM projects
        WHERE id=NEW.project_id AND organization_id=NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'asset intelligence usage project must belong to same organization';
    END IF;
    RETURN NEW;
END
$$;

-- statement-breakpoint

CREATE TRIGGER trg_asset_intelligence_usage_scope_guard
BEFORE INSERT OR UPDATE ON asset_intelligence_usage_signals
FOR EACH ROW EXECUTE FUNCTION lumi_asset_intelligence_usage_scope_guard();

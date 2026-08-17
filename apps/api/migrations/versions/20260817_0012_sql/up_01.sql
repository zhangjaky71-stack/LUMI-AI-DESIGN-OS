CREATE TABLE brand_guide_proposals (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    brand_id UUID NOT NULL,
    source_asset_id UUID NOT NULL,
    status VARCHAR(32) DEFAULT 'pending_review' NOT NULL,
    rules_json JSONB DEFAULT '[]'::jsonb NOT NULL,
    citations_json JSONB DEFAULT '[]'::jsonb NOT NULL,
    reviewed_by VARCHAR(200),
    reviewed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_brand_guide_proposals PRIMARY KEY (id),
    CONSTRAINT ck_brand_guide_proposals_status
        CHECK (status IN ('pending_review','approved','rejected','published')),
    CONSTRAINT fk_brand_guide_proposals_organization_id_organizations
        FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
    CONSTRAINT fk_brand_guide_proposals_brand_id_brands
        FOREIGN KEY (brand_id) REFERENCES brands(id) ON DELETE CASCADE,
    CONSTRAINT fk_brand_guide_proposals_source_asset_id_assets
        FOREIGN KEY (source_asset_id) REFERENCES assets(id) ON DELETE RESTRICT
);

-- statement-breakpoint

CREATE INDEX ix_brand_guide_proposals_organization_id
ON brand_guide_proposals (organization_id);

-- statement-breakpoint

CREATE INDEX ix_brand_guide_proposals_org_brand
ON brand_guide_proposals (organization_id, brand_id, created_at);

-- statement-breakpoint

CREATE TABLE brand_rule_version_counters (
    organization_id UUID NOT NULL,
    brand_id UUID NOT NULL,
    next_version INTEGER NOT NULL,
    CONSTRAINT pk_brand_rule_version_counters PRIMARY KEY (brand_id),
    CONSTRAINT ck_brand_rule_version_counters_positive CHECK (next_version >= 1),
    CONSTRAINT fk_brand_rule_version_counters_organization_id_organizations
        FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
    CONSTRAINT fk_brand_rule_version_counters_brand_id_brands
        FOREIGN KEY (brand_id) REFERENCES brands(id) ON DELETE CASCADE
);

-- statement-breakpoint

CREATE INDEX ix_brand_rule_version_counters_organization_id
ON brand_rule_version_counters (organization_id);

-- statement-breakpoint

CREATE TABLE brand_rule_set_versions (
    id UUID NOT NULL,
    organization_id UUID NOT NULL,
    brand_id UUID NOT NULL,
    version_number INTEGER NOT NULL,
    status VARCHAR(32) DEFAULT 'draft' NOT NULL,
    source VARCHAR(64) NOT NULL,
    snapshot_hash VARCHAR(64) NOT NULL,
    token_set_json JSONB DEFAULT '{}'::jsonb NOT NULL,
    asset_set_json JSONB DEFAULT '{}'::jsonb NOT NULL,
    rules_json JSONB DEFAULT '[]'::jsonb NOT NULL,
    voice_json JSONB DEFAULT '{}'::jsonb NOT NULL,
    visual_style_json JSONB DEFAULT '{}'::jsonb NOT NULL,
    source_proposal_id UUID,
    created_by VARCHAR(200) NOT NULL,
    published_at TIMESTAMP WITH TIME ZONE,
    published_by VARCHAR(200),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_brand_rule_set_versions PRIMARY KEY (id),
    CONSTRAINT uq_brand_rule_set_version UNIQUE (brand_id, version_number),
    CONSTRAINT ck_brand_rule_set_versions_version_number_positive
        CHECK (version_number >= 1),
    CONSTRAINT ck_brand_rule_set_versions_status
        CHECK (status IN ('draft','published','retired')),
    CONSTRAINT ck_brand_rule_set_versions_source
        CHECK (source IN (
            'USER_EXPLICIT',
            'APPROVED_GUIDE_EXTRACTION',
            'MANUAL_ADMIN',
            'INFERRED_PROPOSAL'
        )),
    CONSTRAINT ck_brand_rule_set_versions_snapshot_hash_format
        CHECK (snapshot_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_brand_rule_set_versions_inferred_not_published
        CHECK (status <> 'published' OR source <> 'INFERRED_PROPOSAL'),
    CONSTRAINT ck_brand_rule_set_versions_publish_audit
        CHECK (
            (status = 'published' AND published_at IS NOT NULL AND published_by IS NOT NULL)
            OR (status <> 'published' AND published_at IS NULL AND published_by IS NULL)
        ),
    CONSTRAINT fk_brand_rule_set_versions_organization_id_organizations
        FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
    CONSTRAINT fk_brand_rule_set_versions_brand_id_brands
        FOREIGN KEY (brand_id) REFERENCES brands(id) ON DELETE CASCADE,
    CONSTRAINT fk_brand_rule_set_versions_source_proposal_id_brand_guide_proposals
        FOREIGN KEY (source_proposal_id)
        REFERENCES brand_guide_proposals(id) ON DELETE SET NULL
);

-- statement-breakpoint

CREATE INDEX ix_brand_rule_set_versions_organization_id
ON brand_rule_set_versions (organization_id);

-- statement-breakpoint

CREATE INDEX ix_brand_rule_set_versions_org_brand_status
ON brand_rule_set_versions (organization_id, brand_id, status, version_number DESC);

-- statement-breakpoint

CREATE OR REPLACE FUNCTION lumi_brand_rules_immutable_snapshot()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
       OR NEW.brand_id IS DISTINCT FROM OLD.brand_id
       OR NEW.version_number IS DISTINCT FROM OLD.version_number
       OR NEW.source IS DISTINCT FROM OLD.source
       OR NEW.snapshot_hash IS DISTINCT FROM OLD.snapshot_hash
       OR NEW.token_set_json IS DISTINCT FROM OLD.token_set_json
       OR NEW.asset_set_json IS DISTINCT FROM OLD.asset_set_json
       OR NEW.rules_json IS DISTINCT FROM OLD.rules_json
       OR NEW.voice_json IS DISTINCT FROM OLD.voice_json
       OR NEW.visual_style_json IS DISTINCT FROM OLD.visual_style_json
       OR NEW.source_proposal_id IS DISTINCT FROM OLD.source_proposal_id
       OR NEW.created_by IS DISTINCT FROM OLD.created_by
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'brand rule set snapshot content is immutable';
    END IF;
    IF OLD.status IN ('published','retired') AND NEW.status IS DISTINCT FROM OLD.status THEN
        RAISE EXCEPTION 'published/retired brand rule set lifecycle is immutable';
    END IF;
    RETURN NEW;
END
$$;

-- statement-breakpoint

CREATE TRIGGER trg_brand_rule_set_snapshot_immutable
BEFORE UPDATE ON brand_rule_set_versions
FOR EACH ROW EXECUTE FUNCTION lumi_brand_rules_immutable_snapshot();

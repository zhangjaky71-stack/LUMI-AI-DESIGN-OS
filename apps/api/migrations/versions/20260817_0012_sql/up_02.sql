ALTER TABLE brands
ADD COLUMN active_rule_set_version_id UUID;

-- statement-breakpoint

ALTER TABLE artifact_versions
ADD COLUMN brand_rule_set_version_id UUID;

-- statement-breakpoint

ALTER TABLE agent_runs
ADD COLUMN brand_rule_set_version_id UUID;

-- statement-breakpoint

ALTER TABLE brands
ADD CONSTRAINT fk_brands_active_rule_set_version_id_brand_rule_set_versions
FOREIGN KEY (active_rule_set_version_id)
REFERENCES brand_rule_set_versions(id)
ON DELETE SET NULL;

-- statement-breakpoint

ALTER TABLE artifact_versions
ADD CONSTRAINT fk_artifact_versions_brand_rule_set_version_id_brand_rule_set_versions
FOREIGN KEY (brand_rule_set_version_id)
REFERENCES brand_rule_set_versions(id)
ON DELETE RESTRICT;

-- statement-breakpoint

ALTER TABLE agent_runs
ADD CONSTRAINT fk_agent_runs_brand_rule_set_version_id_brand_rule_set_versions
FOREIGN KEY (brand_rule_set_version_id)
REFERENCES brand_rule_set_versions(id)
ON DELETE RESTRICT;

-- statement-breakpoint

CREATE INDEX ix_artifact_versions_brand_rule_set_version_id
ON artifact_versions (brand_rule_set_version_id);

-- statement-breakpoint

CREATE INDEX ix_agent_runs_brand_rule_set_version_id
ON agent_runs (brand_rule_set_version_id);

-- statement-breakpoint

CREATE INDEX ix_brands_active_rule_set_version_id
ON brands (active_rule_set_version_id);

-- statement-breakpoint

CREATE OR REPLACE FUNCTION lumi_validate_active_brand_rule_set()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.active_rule_set_version_id IS NULL THEN
        RETURN NEW;
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM brand_rule_set_versions r
        WHERE r.id = NEW.active_rule_set_version_id
          AND r.organization_id = NEW.organization_id
          AND r.brand_id = NEW.id
          AND r.status = 'published'
    ) THEN
        RAISE EXCEPTION
            'active brand rule set must be published and belong to the same tenant/brand';
    END IF;
    RETURN NEW;
END
$$;

-- statement-breakpoint

CREATE TRIGGER trg_validate_active_brand_rule_set
BEFORE INSERT OR UPDATE OF active_rule_set_version_id ON brands
FOR EACH ROW EXECUTE FUNCTION lumi_validate_active_brand_rule_set();

-- statement-breakpoint

CREATE OR REPLACE FUNCTION lumi_capture_artifact_brand_rule_set()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.brand_rule_set_version_id IS NULL THEN
        SELECT b.active_rule_set_version_id
        INTO NEW.brand_rule_set_version_id
        FROM artifacts a
        JOIN projects p
          ON p.id = a.project_id
         AND p.organization_id = NEW.organization_id
        LEFT JOIN brands b
          ON b.id = p.brand_id
         AND b.organization_id = NEW.organization_id
        WHERE a.id = NEW.artifact_id
          AND a.organization_id = NEW.organization_id;
    END IF;
    RETURN NEW;
END
$$;

-- statement-breakpoint

CREATE TRIGGER trg_capture_artifact_brand_rule_set
BEFORE INSERT ON artifact_versions
FOR EACH ROW EXECUTE FUNCTION lumi_capture_artifact_brand_rule_set();

-- statement-breakpoint

CREATE OR REPLACE FUNCTION lumi_capture_agent_run_brand_rule_set()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.brand_rule_set_version_id IS NULL THEN
        SELECT b.active_rule_set_version_id
        INTO NEW.brand_rule_set_version_id
        FROM projects p
        LEFT JOIN brands b
          ON b.id = p.brand_id
         AND b.organization_id = NEW.organization_id
        WHERE p.id = NEW.project_id
          AND p.organization_id = NEW.organization_id;
    END IF;
    RETURN NEW;
END
$$;

-- statement-breakpoint

CREATE TRIGGER trg_capture_agent_run_brand_rule_set
BEFORE INSERT ON agent_runs
FOR EACH ROW EXECUTE FUNCTION lumi_capture_agent_run_brand_rule_set();

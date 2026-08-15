ALTER TABLE assets ADD CONSTRAINT ck_assets_version_positive CHECK (version >= 1);

-- statement-breakpoint

ALTER TABLE auth_identities ADD CONSTRAINT ck_auth_identities_version_positive CHECK (version >= 1);

-- statement-breakpoint

ALTER TABLE brand_fonts ADD CONSTRAINT ck_brand_fonts_version_positive CHECK (version >= 1);

-- statement-breakpoint

ALTER TABLE brand_logos ADD CONSTRAINT ck_brand_logos_version_positive CHECK (version >= 1);

-- statement-breakpoint

ALTER TABLE brand_palettes ADD CONSTRAINT ck_brand_palettes_version_positive CHECK (version >= 1);

-- statement-breakpoint

ALTER TABLE brand_rules ADD CONSTRAINT ck_brand_rules_version_positive CHECK (version >= 1);

-- statement-breakpoint

ALTER TABLE brands ADD CONSTRAINT ck_brands_version_positive CHECK (version >= 1);

-- statement-breakpoint

ALTER TABLE design_documents ADD CONSTRAINT ck_design_documents_version_positive CHECK (version >= 1);

-- statement-breakpoint

ALTER TABLE generations ADD CONSTRAINT ck_generations_version_positive CHECK (version >= 1);

-- statement-breakpoint

ALTER TABLE organization_members ADD CONSTRAINT ck_organization_members_version_positive CHECK (version >= 1);

-- statement-breakpoint

ALTER TABLE organizations ADD CONSTRAINT ck_organizations_version_positive CHECK (version >= 1);

-- statement-breakpoint

ALTER TABLE project_members ADD CONSTRAINT ck_project_members_version_positive CHECK (version >= 1);

-- statement-breakpoint

ALTER TABLE projects ADD CONSTRAINT ck_projects_version_positive CHECK (version >= 1);

-- statement-breakpoint

ALTER TABLE tasks ADD CONSTRAINT ck_tasks_version_positive CHECK (version >= 1);

-- statement-breakpoint

ALTER TABLE usage_counters ADD CONSTRAINT ck_usage_counters_version_positive CHECK (version >= 1);

-- statement-breakpoint

ALTER TABLE users ADD CONSTRAINT ck_users_version_positive CHECK (version >= 1);

-- statement-breakpoint

ALTER TABLE workspace_members ADD CONSTRAINT ck_workspace_members_version_positive CHECK (version >= 1);

-- statement-breakpoint

ALTER TABLE workspaces ADD CONSTRAINT ck_workspaces_version_positive CHECK (version >= 1);

-- statement-breakpoint

CREATE OR REPLACE FUNCTION lumi_set_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- statement-breakpoint

CREATE TRIGGER trg_agent_runs_updated_at
BEFORE UPDATE ON agent_runs
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_approvals_updated_at
BEFORE UPDATE ON approvals
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_artifact_branches_updated_at
BEFORE UPDATE ON artifact_branches
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_artifacts_updated_at
BEFORE UPDATE ON artifacts
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_asset_metadata_updated_at
BEFORE UPDATE ON asset_metadata
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_asset_rights_updated_at
BEFORE UPDATE ON asset_rights
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_assets_updated_at
BEFORE UPDATE ON assets
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_auth_identities_updated_at
BEFORE UPDATE ON auth_identities
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_brand_fonts_updated_at
BEFORE UPDATE ON brand_fonts
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_brand_logos_updated_at
BEFORE UPDATE ON brand_logos
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_brand_palettes_updated_at
BEFORE UPDATE ON brand_palettes
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_brand_rules_updated_at
BEFORE UPDATE ON brand_rules
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_brands_updated_at
BEFORE UPDATE ON brands
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_design_documents_updated_at
BEFORE UPDATE ON design_documents
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_generations_updated_at
BEFORE UPDATE ON generations
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

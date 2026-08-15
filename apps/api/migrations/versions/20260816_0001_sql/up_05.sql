CREATE TRIGGER trg_organization_members_updated_at
BEFORE UPDATE ON organization_members
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_organizations_updated_at
BEFORE UPDATE ON organizations
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_project_members_updated_at
BEFORE UPDATE ON project_members
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_projects_updated_at
BEFORE UPDATE ON projects
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_tasks_updated_at
BEFORE UPDATE ON tasks
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_usage_counters_updated_at
BEFORE UPDATE ON usage_counters
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_workspace_members_updated_at
BEFORE UPDATE ON workspace_members
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE TRIGGER trg_workspaces_updated_at
BEFORE UPDATE ON workspaces
FOR EACH ROW EXECUTE FUNCTION lumi_set_updated_at();

-- statement-breakpoint

CREATE OR REPLACE FUNCTION lumi_forbid_mutation() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'immutable table % does not allow %', TG_TABLE_NAME, TG_OP
    USING ERRCODE = '55000';
END;
$$ LANGUAGE plpgsql;

-- statement-breakpoint

CREATE TRIGGER trg_cost_ledger_immutable
BEFORE UPDATE OR DELETE ON cost_ledger
FOR EACH ROW EXECUTE FUNCTION lumi_forbid_mutation();

-- statement-breakpoint

CREATE TRIGGER trg_audit_events_immutable
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION lumi_forbid_mutation();

-- statement-breakpoint

CREATE TRIGGER trg_inbox_events_immutable
BEFORE UPDATE OR DELETE ON inbox_events
FOR EACH ROW EXECUTE FUNCTION lumi_forbid_mutation();

-- statement-breakpoint

CREATE TRIGGER trg_design_document_versions_immutable
BEFORE UPDATE OR DELETE ON design_document_versions
FOR EACH ROW EXECUTE FUNCTION lumi_forbid_mutation();

-- statement-breakpoint

CREATE TRIGGER trg_artifact_provenance_immutable
BEFORE UPDATE OR DELETE ON artifact_provenance
FOR EACH ROW EXECUTE FUNCTION lumi_forbid_mutation();

-- statement-breakpoint

CREATE OR REPLACE FUNCTION lumi_protect_artifact_version_history() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'artifact version history cannot be deleted' USING ERRCODE = '55000';
  END IF;
  IF OLD.status = 'approved' THEN
    RAISE EXCEPTION 'approved artifact version is immutable' USING ERRCODE = '55000';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- statement-breakpoint

CREATE TRIGGER trg_artifact_versions_history
BEFORE UPDATE OR DELETE ON artifact_versions
FOR EACH ROW EXECUTE FUNCTION lumi_protect_artifact_version_history();

-- statement-breakpoint

CREATE OR REPLACE FUNCTION lumi_reject_task_dependency_cycle() RETURNS trigger AS $$
DECLARE cycle_found boolean;
BEGIN
  WITH RECURSIVE deps(task_id) AS (
    SELECT NEW.depends_on_task_id
    UNION
    SELECT td.depends_on_task_id
    FROM task_dependencies td
    JOIN deps d ON td.task_id = d.task_id
  )
  SELECT EXISTS(SELECT 1 FROM deps WHERE task_id = NEW.task_id) INTO cycle_found;
  IF cycle_found THEN
    RAISE EXCEPTION 'task dependency cycle detected' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- statement-breakpoint

CREATE TRIGGER trg_task_dependencies_no_cycle
BEFORE INSERT OR UPDATE ON task_dependencies
FOR EACH ROW EXECUTE FUNCTION lumi_reject_task_dependency_cycle();

-- statement-breakpoint

CREATE OR REPLACE FUNCTION lumi_reject_artifact_edge_cycle() RETURNS trigger AS $$
DECLARE cycle_found boolean;
BEGIN
  WITH RECURSIVE edges(version_id) AS (
    SELECT NEW.to_artifact_version_id
    UNION
    SELECT ae.to_artifact_version_id
    FROM artifact_edges ae
    JOIN edges e ON ae.from_artifact_version_id = e.version_id
  )
  SELECT EXISTS(
    SELECT 1 FROM edges WHERE version_id = NEW.from_artifact_version_id
  ) INTO cycle_found;
  IF cycle_found THEN
    RAISE EXCEPTION 'artifact lineage cycle detected' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- statement-breakpoint

CREATE TRIGGER trg_artifact_edges_no_cycle
BEFORE INSERT OR UPDATE ON artifact_edges
FOR EACH ROW EXECUTE FUNCTION lumi_reject_artifact_edge_cycle();

-- statement-breakpoint

CREATE OR REPLACE FUNCTION lumi_enforce_same_tenant_fk() RETURNS trigger AS $$
DECLARE
  i integer;
  reference_text text;
  reference_org uuid;
BEGIN
  i := 0;
  WHILE i < TG_NARGS LOOP
    reference_text := to_jsonb(NEW) ->> TG_ARGV[i];
    IF reference_text IS NOT NULL THEN
      EXECUTE format('SELECT organization_id FROM %I WHERE id = $1', TG_ARGV[i + 1])
        INTO reference_org USING reference_text::uuid;
      IF reference_org IS NOT NULL AND reference_org <> NEW.organization_id THEN
        RAISE EXCEPTION 'cross-tenant reference from %.% to % is forbidden',
          TG_TABLE_NAME, TG_ARGV[i], TG_ARGV[i + 1]
          USING ERRCODE = '23514';
      END IF;
    END IF;
    i := i + 2;
  END LOOP;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- statement-breakpoint

CREATE TRIGGER trg_workspace_members_same_tenant
BEFORE INSERT OR UPDATE ON workspace_members
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('workspace_id', 'workspaces');

-- statement-breakpoint

CREATE TRIGGER trg_brand_palettes_same_tenant
BEFORE INSERT OR UPDATE ON brand_palettes
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('brand_id', 'brands');

-- statement-breakpoint

CREATE TRIGGER trg_brand_fonts_same_tenant
BEFORE INSERT OR UPDATE ON brand_fonts
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('brand_id', 'brands', 'source_asset_id', 'assets');

-- statement-breakpoint

CREATE TRIGGER trg_brand_logos_same_tenant
BEFORE INSERT OR UPDATE ON brand_logos
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('brand_id', 'brands', 'asset_id', 'assets');

-- statement-breakpoint

CREATE TRIGGER trg_brand_rules_same_tenant
BEFORE INSERT OR UPDATE ON brand_rules
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('brand_id', 'brands');

-- statement-breakpoint

CREATE TRIGGER trg_projects_same_tenant
BEFORE INSERT OR UPDATE ON projects
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('workspace_id', 'workspaces', 'brand_id', 'brands', 'active_branch_id', 'artifact_branches');

-- statement-breakpoint

CREATE TRIGGER trg_project_members_same_tenant
BEFORE INSERT OR UPDATE ON project_members
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('project_id', 'projects');

-- statement-breakpoint

CREATE TRIGGER trg_assets_same_tenant
BEFORE INSERT OR UPDATE ON assets
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('project_id', 'projects');

-- statement-breakpoint

CREATE TRIGGER trg_asset_files_same_tenant
BEFORE INSERT OR UPDATE ON asset_files
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('asset_id', 'assets');

-- statement-breakpoint

CREATE TRIGGER trg_asset_previews_same_tenant
BEFORE INSERT OR UPDATE ON asset_previews
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('asset_id', 'assets');

-- statement-breakpoint

CREATE TRIGGER trg_asset_metadata_same_tenant
BEFORE INSERT OR UPDATE ON asset_metadata
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('asset_id', 'assets');

-- statement-breakpoint

CREATE TRIGGER trg_asset_embeddings_same_tenant
BEFORE INSERT OR UPDATE ON asset_embeddings
FOR EACH ROW EXECUTE FUNCTION lumi_enforce_same_tenant_fk('asset_id', 'assets');

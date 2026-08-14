BEGIN;

CREATE TABLE IF NOT EXISTS artifacts (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id uuid NOT NULL,
  type text NOT NULL,
  title text NOT NULL,
  archived boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, id)
);

CREATE TABLE IF NOT EXISTS artifact_branches (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  artifact_id uuid NOT NULL,
  name text NOT NULL,
  base_version_id uuid NULL,
  head_version_id uuid NULL,
  created_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, artifact_id, name),
  UNIQUE (organization_id, id),
  FOREIGN KEY (organization_id, artifact_id) REFERENCES artifacts(organization_id, id)
);

CREATE TABLE IF NOT EXISTS artifact_versions (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  artifact_id uuid NOT NULL,
  branch_id uuid NOT NULL,
  parent_version_id uuid NULL,
  schema_version text NOT NULL,
  version_number bigint NOT NULL CHECK (version_number >= 1),
  status text NOT NULL CHECK (status IN ('DRAFT','READY','APPROVED','REJECTED','ARCHIVED')),
  content_hash char(64) NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  constraint_snapshot_hash char(64) NOT NULL CHECK (constraint_snapshot_hash ~ '^[0-9a-f]{64}$'),
  design_document_version_id uuid NULL,
  primary_file_id uuid NULL,
  quality_score double precision NULL CHECK (quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 1)),
  created_by_type text NOT NULL CHECK (created_by_type IN ('USER','AGENT','SYSTEM')),
  created_by_id text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, artifact_id, version_number),
  UNIQUE (organization_id, id),
  FOREIGN KEY (organization_id, artifact_id) REFERENCES artifacts(organization_id, id),
  FOREIGN KEY (organization_id, branch_id) REFERENCES artifact_branches(organization_id, id)
);

ALTER TABLE artifact_branches
  ADD CONSTRAINT artifact_branches_base_fk FOREIGN KEY (organization_id, base_version_id) REFERENCES artifact_versions(organization_id, id) DEFERRABLE INITIALLY DEFERRED,
  ADD CONSTRAINT artifact_branches_head_fk FOREIGN KEY (organization_id, head_version_id) REFERENCES artifact_versions(organization_id, id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE artifact_versions
  ADD CONSTRAINT artifact_versions_parent_fk FOREIGN KEY (organization_id, parent_version_id) REFERENCES artifact_versions(organization_id, id) DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE IF NOT EXISTS artifact_edges (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  from_version_id uuid NOT NULL,
  to_version_id uuid NOT NULL,
  type text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (from_version_id <> to_version_id),
  UNIQUE (organization_id, from_version_id, to_version_id, type),
  FOREIGN KEY (organization_id, from_version_id) REFERENCES artifact_versions(organization_id, id),
  FOREIGN KEY (organization_id, to_version_id) REFERENCES artifact_versions(organization_id, id)
);

CREATE TABLE IF NOT EXISTS artifact_files (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  artifact_version_id uuid NOT NULL,
  role text NOT NULL CHECK (role IN ('PREVIEW','ORIGINAL','THUMBNAIL','WEB_OPTIMIZED','PRINT_PDF','LAYER_DATA')),
  storage_key text NOT NULL CHECK (storage_key <> '' AND storage_key NOT LIKE '%://%'),
  mime_type text NOT NULL,
  size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
  checksum_sha256 char(64) NOT NULL CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
  width integer NULL CHECK (width IS NULL OR width >= 0),
  height integer NULL CHECK (height IS NULL OR height >= 0),
  duration_ms bigint NULL CHECK (duration_ms IS NULL OR duration_ms >= 0),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, artifact_version_id, role),
  UNIQUE (organization_id, id),
  FOREIGN KEY (organization_id, artifact_version_id) REFERENCES artifact_versions(organization_id, id)
);

ALTER TABLE artifact_versions
  ADD CONSTRAINT artifact_versions_primary_file_fk FOREIGN KEY (organization_id, primary_file_id) REFERENCES artifact_files(organization_id, id) DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE IF NOT EXISTS artifact_provenance (
  artifact_version_id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  constraint_snapshot_hash char(64) NOT NULL CHECK (constraint_snapshot_hash ~ '^[0-9a-f]{64}$'),
  code_git_sha char(40) NOT NULL CHECK (code_git_sha ~ '^[0-9a-f]{40}$'),
  compiler_version text NULL,
  compiler_document_id text NULL,
  compiler_schema_version text NULL,
  compiler_document_version bigint NULL,
  compiler_compile_hash char(64) NULL CHECK (compiler_compile_hash IS NULL OR compiler_compile_hash ~ '^[0-9a-f]{64}$'),
  compiler_resource_versions jsonb NOT NULL DEFAULT '{}'::jsonb,
  compiler_font_versions jsonb NOT NULL DEFAULT '{}'::jsonb,
  agent_run_id uuid NULL,
  task_id uuid NULL,
  generation_id uuid NULL,
  provider text NULL,
  model text NULL,
  provider_request_id text NULL,
  prompt_hash char(64) NULL CHECK (prompt_hash IS NULL OR prompt_hash ~ '^[0-9a-f]{64}$'),
  prompt_template_version text NULL,
  input_asset_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  input_artifact_version_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  design_ir_schema_version text NULL,
  recipe_version text NULL,
  skill_versions jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (organization_id, artifact_version_id) REFERENCES artifact_versions(organization_id, id)
);

CREATE INDEX IF NOT EXISTS artifact_versions_artifact_created_idx ON artifact_versions (organization_id, artifact_id, created_at DESC);
CREATE INDEX IF NOT EXISTS artifact_edges_to_idx ON artifact_edges (organization_id, to_version_id);
CREATE INDEX IF NOT EXISTS artifact_edges_from_idx ON artifact_edges (organization_id, from_version_id);
CREATE INDEX IF NOT EXISTS artifact_files_checksum_idx ON artifact_files (organization_id, checksum_sha256);

-- Repository CAS must use: UPDATE artifact_branches SET head_version_id=:next
-- WHERE organization_id=:org AND id=:branch AND head_version_id IS NOT DISTINCT FROM :expected.
-- A zero-row update is a branch conflict; application code must not retry with a blind overwrite.

COMMIT;

BEGIN;

CREATE TABLE image_edit_jobs (
  id text PRIMARY KEY CHECK (id LIKE 'image-edit:%'),
  organization_id uuid NOT NULL,
  project_id uuid NOT NULL,
  task_id uuid NOT NULL,
  operation_id uuid NOT NULL,
  semantic_hash char(64) NOT NULL CHECK (semantic_hash ~ '^[0-9a-f]{64}$'),
  source_artifact_version_id uuid NOT NULL,
  source_asset_id text NOT NULL,
  source_asset_version text NOT NULL,
  source_checksum_sha256 char(64) NOT NULL CHECK (source_checksum_sha256 ~ '^[0-9a-f]{64}$'),
  route text NOT NULL CHECK (route IN ('STRUCTURAL_IR_EDIT','PIXEL_LOCAL_EDIT','REGENERATE_REGION','FULL_IMAGE_EDIT','HYBRID')),
  status text NOT NULL CHECK (status IN ('PLANNED','RUNNING','PROVIDER_PENDING','VALIDATING','COMPLETED','REPAIR_REQUIRED','REJECTED','FAILED')),
  result_artifact_version_id uuid NULL,
  result_design_document_version_id text NULL,
  provider text NULL,
  model text NULL,
  provider_request_id text NULL,
  provenance_snapshot_id text NULL,
  validation_decision text NULL CHECK (validation_decision IS NULL OR validation_decision IN ('PASS','REPAIR','REJECT')),
  error_code text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, operation_id),
  UNIQUE (organization_id, id),
  FOREIGN KEY (organization_id, source_artifact_version_id) REFERENCES artifact_versions(organization_id, id),
  FOREIGN KEY (organization_id, result_artifact_version_id) REFERENCES artifact_versions(organization_id, id),
  CHECK (result_artifact_version_id IS NULL OR result_artifact_version_id <> source_artifact_version_id)
);

CREATE TABLE image_edit_masks (
  id text NOT NULL,
  organization_id uuid NOT NULL,
  image_edit_id text NOT NULL,
  version text NOT NULL,
  source_kind text NOT NULL CHECK (source_kind IN ('USER_BRUSH','DESIGN_IR','DETECTOR','AGENT_PROPOSED')),
  source_asset_id text NOT NULL,
  source_asset_version text NOT NULL,
  source_checksum_sha256 char(64) NOT NULL CHECK (source_checksum_sha256 ~ '^[0-9a-f]{64}$'),
  source_width integer NOT NULL CHECK (source_width > 0),
  source_height integer NOT NULL CHECK (source_height > 0),
  x integer NOT NULL CHECK (x >= 0),
  y integer NOT NULL CHECK (y >= 0),
  width integer NOT NULL CHECK (width > 0),
  height integer NOT NULL CHECK (height > 0),
  checksum_sha256 char(64) NOT NULL CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
  durable_ref text NOT NULL CHECK (durable_ref <> '' AND position('://' in durable_ref) = 0),
  preview_required boolean NOT NULL DEFAULT false,
  preview_approved_by text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id, id, version),
  FOREIGN KEY (organization_id, image_edit_id) REFERENCES image_edit_jobs(organization_id, id),
  CHECK (x + width <= source_width AND y + height <= source_height),
  CHECK (NOT preview_required OR preview_approved_by IS NOT NULL)
);

CREATE TABLE image_edit_protected_regions (
  organization_id uuid NOT NULL,
  image_edit_id text NOT NULL,
  region_id text NOT NULL,
  role text NOT NULL CHECK (role IN ('EDITABLE','PRODUCT','LOGO','QR','LOCKED_TEXT','CONTENT')),
  severity text NOT NULL CHECK (severity IN ('HARD','SOFT','ADVISORY')),
  x integer NOT NULL CHECK (x >= 0),
  y integer NOT NULL CHECK (y >= 0),
  width integer NOT NULL CHECK (width > 0),
  height integer NOT NULL CHECK (height > 0),
  source_checksum_sha256 char(64) NOT NULL CHECK (source_checksum_sha256 ~ '^[0-9a-f]{64}$'),
  identity_id text NULL,
  expected_text text NULL,
  expected_qr_payload text NULL,
  PRIMARY KEY (organization_id, image_edit_id, region_id),
  FOREIGN KEY (organization_id, image_edit_id) REFERENCES image_edit_jobs(organization_id, id),
  CHECK (role <> 'QR' OR expected_qr_payload IS NOT NULL),
  CHECK (role <> 'LOCKED_TEXT' OR expected_text IS NOT NULL)
);

CREATE TABLE image_edit_pending_invocations (
  organization_id uuid NOT NULL,
  image_edit_id text NOT NULL,
  provider text NOT NULL,
  model text NOT NULL,
  provider_request_id text NOT NULL,
  provider_state jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organization_id, image_edit_id),
  FOREIGN KEY (organization_id, image_edit_id) REFERENCES image_edit_jobs(organization_id, id)
);

CREATE TABLE image_edit_provenance (
  snapshot_id text PRIMARY KEY CHECK (snapshot_id LIKE 'image-edit-provenance:%'),
  organization_id uuid NOT NULL,
  image_edit_id text NOT NULL,
  operation_id uuid NOT NULL,
  route text NOT NULL,
  source_artifact_version_id uuid NOT NULL,
  source_asset_ref text NOT NULL,
  source_checksum_sha256 char(64) NOT NULL,
  instruction_hash char(64) NOT NULL CHECK (instruction_hash ~ '^[0-9a-f]{64}$'),
  mask_hash char(64) NULL CHECK (mask_hash IS NULL OR mask_hash ~ '^[0-9a-f]{64}$'),
  protected_region_hash char(64) NOT NULL CHECK (protected_region_hash ~ '^[0-9a-f]{64}$'),
  constraint_snapshot_hash char(64) NOT NULL CHECK (constraint_snapshot_hash ~ '^[0-9a-f]{64}$'),
  validation_report_hash char(64) NOT NULL CHECK (validation_report_hash ~ '^[0-9a-f]{64}$'),
  provider text NULL,
  model text NULL,
  provider_request_id text NULL,
  routing_reason_codes jsonb NOT NULL DEFAULT '[]'::jsonb,
  pricing_snapshot_id text NULL,
  cost_usd numeric(20,8) NULL CHECK (cost_usd IS NULL OR cost_usd >= 0),
  cost_confidence text NULL,
  seed bigint NULL,
  code_git_sha char(40) NOT NULL CHECK (code_git_sha ~ '^[0-9a-f]{40}$'),
  validation_decision text NOT NULL CHECK (validation_decision IN ('PASS','REPAIR','REJECT')),
  identity_validation_snapshot_id text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, image_edit_id),
  FOREIGN KEY (organization_id, image_edit_id) REFERENCES image_edit_jobs(organization_id, id),
  FOREIGN KEY (organization_id, source_artifact_version_id) REFERENCES artifact_versions(organization_id, id)
);

CREATE TABLE image_edit_validation_findings (
  organization_id uuid NOT NULL,
  image_edit_id text NOT NULL,
  ordinal integer NOT NULL CHECK (ordinal >= 0),
  validator text NOT NULL,
  status text NOT NULL CHECK (status IN ('PASS','FAIL','UNAVAILABLE')),
  severity text NOT NULL CHECK (severity IN ('HARD','SOFT','ADVISORY')),
  reason_code text NOT NULL,
  score double precision NULL,
  threshold double precision NULL,
  evidence_ref text NULL,
  PRIMARY KEY (organization_id, image_edit_id, ordinal),
  FOREIGN KEY (organization_id, image_edit_id) REFERENCES image_edit_jobs(organization_id, id)
);

CREATE INDEX image_edit_source_version_idx ON image_edit_jobs (organization_id, source_artifact_version_id);
CREATE INDEX image_edit_status_idx ON image_edit_jobs (organization_id, status, updated_at);

COMMIT;

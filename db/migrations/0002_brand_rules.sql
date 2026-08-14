BEGIN;

CREATE TABLE IF NOT EXISTS brand_profiles (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  project_id uuid NULL,
  name text NOT NULL CHECK (btrim(name) <> ''),
  status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','ARCHIVED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, id)
);

CREATE TABLE IF NOT EXISTS brand_token_sets (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  brand_profile_id uuid NOT NULL,
  version text NOT NULL CHECK (btrim(version) <> ''),
  colors jsonb NOT NULL DEFAULT '[]'::jsonb,
  fonts jsonb NOT NULL DEFAULT '[]'::jsonb,
  spacing_scale jsonb NOT NULL DEFAULT '[]'::jsonb,
  radius_tokens jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, brand_profile_id, version),
  UNIQUE (organization_id, id),
  FOREIGN KEY (organization_id, brand_profile_id)
    REFERENCES brand_profiles(organization_id, id)
);

CREATE TABLE IF NOT EXISTS brand_asset_sets (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  brand_profile_id uuid NOT NULL,
  version text NOT NULL CHECK (btrim(version) <> ''),
  logo_asset_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  font_asset_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  reference_asset_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  negative_reference_asset_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, brand_profile_id, version),
  UNIQUE (organization_id, id),
  FOREIGN KEY (organization_id, brand_profile_id)
    REFERENCES brand_profiles(organization_id, id)
);

CREATE TABLE IF NOT EXISTS brand_rule_sets (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  brand_profile_id uuid NOT NULL,
  version text NOT NULL CHECK (btrim(version) <> ''),
  status text NOT NULL CHECK (status IN ('DRAFT','PUBLISHED','ARCHIVED')),
  token_set_version text NOT NULL,
  asset_set_version text NOT NULL,
  voice jsonb NOT NULL DEFAULT '{}'::jsonb,
  visual_references jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz NULL,
  UNIQUE (organization_id, brand_profile_id, version),
  UNIQUE (organization_id, id),
  FOREIGN KEY (organization_id, brand_profile_id)
    REFERENCES brand_profiles(organization_id, id),
  FOREIGN KEY (organization_id, brand_profile_id, token_set_version)
    REFERENCES brand_token_sets(organization_id, brand_profile_id, version),
  FOREIGN KEY (organization_id, brand_profile_id, asset_set_version)
    REFERENCES brand_asset_sets(organization_id, brand_profile_id, version),
  CHECK ((status = 'PUBLISHED' AND published_at IS NOT NULL) OR status <> 'PUBLISHED')
);

CREATE TABLE IF NOT EXISTS brand_rules (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  brand_rule_set_id uuid NOT NULL,
  category text NOT NULL CHECK (
    category IN ('COLOR','TYPOGRAPHY','LOGO','SPACING','ASSET','VOICE','VISUAL_STYLE')
  ),
  type text NOT NULL,
  severity text NOT NULL CHECK (severity IN ('HARD','SOFT','ADVISORY')),
  source text NOT NULL CHECK (
    source IN ('USER_EXPLICIT','APPROVED_GUIDE_EXTRACTION','MANUAL_ADMIN','INFERRED_PROPOSAL')
  ),
  priority integer NOT NULL,
  scope jsonb NOT NULL DEFAULT '{}'::jsonb,
  parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
  active boolean NOT NULL DEFAULT true,
  citations jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, brand_rule_set_id, id),
  UNIQUE (organization_id, id),
  FOREIGN KEY (organization_id, brand_rule_set_id)
    REFERENCES brand_rule_sets(organization_id, id),
  CHECK (NOT (source = 'INFERRED_PROPOSAL' AND severity = 'HARD')),
  CHECK (source <> 'APPROVED_GUIDE_EXTRACTION' OR jsonb_array_length(citations) > 0)
);

CREATE TABLE IF NOT EXISTS brand_guide_extraction_proposals (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  brand_profile_id uuid NOT NULL,
  source_asset_id uuid NOT NULL,
  status text NOT NULL CHECK (status IN ('PROPOSED','APPROVED','REJECTED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  reviewed_by text NULL,
  reviewed_at timestamptz NULL,
  UNIQUE (organization_id, id),
  FOREIGN KEY (organization_id, brand_profile_id)
    REFERENCES brand_profiles(organization_id, id),
  CHECK (
    (status = 'PROPOSED' AND reviewed_by IS NULL AND reviewed_at IS NULL)
    OR (status IN ('APPROVED','REJECTED') AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)
  )
);

CREATE TABLE IF NOT EXISTS brand_guide_extraction_candidates (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  proposal_id uuid NOT NULL,
  candidate_key text NOT NULL,
  confidence double precision NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  rule_payload jsonb NOT NULL,
  citations jsonb NOT NULL CHECK (jsonb_array_length(citations) > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (organization_id, proposal_id, candidate_key),
  FOREIGN KEY (organization_id, proposal_id)
    REFERENCES brand_guide_extraction_proposals(organization_id, id),
  CHECK (COALESCE(rule_payload->>'source', '') = 'INFERRED_PROPOSAL'),
  CHECK (COALESCE(rule_payload->>'severity', '') <> 'HARD')
);

CREATE OR REPLACE FUNCTION lumi_reject_inferred_rules_on_publish()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.status = 'PUBLISHED' AND EXISTS (
    SELECT 1
    FROM brand_rules r
    WHERE r.organization_id = NEW.organization_id
      AND r.brand_rule_set_id = NEW.id
      AND r.source = 'INFERRED_PROPOSAL'
  ) THEN
    RAISE EXCEPTION 'cannot publish BrandRuleSet with unreviewed inferred proposals';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS brand_rule_sets_publish_guard ON brand_rule_sets;
CREATE TRIGGER brand_rule_sets_publish_guard
BEFORE INSERT OR UPDATE OF status ON brand_rule_sets
FOR EACH ROW EXECUTE FUNCTION lumi_reject_inferred_rules_on_publish();

CREATE OR REPLACE FUNCTION lumi_reject_inferred_rule_in_published_set()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.source = 'INFERRED_PROPOSAL' AND EXISTS (
    SELECT 1
    FROM brand_rule_sets s
    WHERE s.organization_id = NEW.organization_id
      AND s.id = NEW.brand_rule_set_id
      AND s.status = 'PUBLISHED'
  ) THEN
    RAISE EXCEPTION 'cannot add inferred proposal to published BrandRuleSet';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS brand_rules_published_guard ON brand_rules;
CREATE TRIGGER brand_rules_published_guard
BEFORE INSERT OR UPDATE OF source, brand_rule_set_id ON brand_rules
FOR EACH ROW EXECUTE FUNCTION lumi_reject_inferred_rule_in_published_set();

ALTER TABLE artifact_versions
  ADD COLUMN IF NOT EXISTS brand_rule_set_version text NULL;

ALTER TABLE artifact_provenance
  ADD COLUMN IF NOT EXISTS brand_rule_set_version text NULL;

CREATE INDEX IF NOT EXISTS brand_profiles_project_idx
  ON brand_profiles (organization_id, project_id) WHERE status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS brand_rule_sets_profile_idx
  ON brand_rule_sets (organization_id, brand_profile_id, created_at DESC);
CREATE INDEX IF NOT EXISTS brand_rules_rule_set_idx
  ON brand_rules (organization_id, brand_rule_set_id, priority DESC);
CREATE INDEX IF NOT EXISTS brand_extraction_profile_idx
  ON brand_guide_extraction_proposals (organization_id, brand_profile_id, created_at DESC);

COMMIT;

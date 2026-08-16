CREATE TABLE model_registry_versions (
  id UUID PRIMARY KEY,
  version VARCHAR(64) NOT NULL UNIQUE,
  checksum_sha256 CHAR(64) NOT NULL UNIQUE,
  status VARCHAR(16) DEFAULT 'published' NOT NULL,
  observed_at TIMESTAMP WITH TIME ZONE NOT NULL,
  published_at TIMESTAMP WITH TIME ZONE NOT NULL,
  source_ref TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  CONSTRAINT ck_model_registry_versions_checksum
    CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
  CONSTRAINT ck_model_registry_versions_status
    CHECK (status IN ('draft','published','retired'))
);

-- statement-breakpoint

CREATE TABLE model_providers (
  id UUID PRIMARY KEY,
  provider_key VARCHAR(128) NOT NULL UNIQUE,
  display_name VARCHAR(255) NOT NULL,
  source_ref TEXT NOT NULL,
  observed_at TIMESTAMP WITH TIME ZONE NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
);

-- statement-breakpoint

CREATE TABLE model_definitions (
  id UUID PRIMARY KEY,
  provider_id UUID NOT NULL REFERENCES model_providers(id) ON DELETE RESTRICT,
  model_key VARCHAR(255) NOT NULL UNIQUE,
  provider_model_id VARCHAR(255) NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  CONSTRAINT uq_model_definitions_provider_model
    UNIQUE (provider_id, provider_model_id)
);

-- statement-breakpoint

CREATE TABLE model_revisions (
  id UUID PRIMARY KEY,
  registry_version_id UUID NOT NULL
    REFERENCES model_registry_versions(id) ON DELETE RESTRICT,
  model_definition_id UUID NOT NULL
    REFERENCES model_definitions(id) ON DELETE RESTRICT,
  revision_key VARCHAR(255) NOT NULL,
  lifecycle VARCHAR(24) NOT NULL,
  route_eligible BOOLEAN DEFAULT false NOT NULL,
  regions JSONB DEFAULT '["global"]'::jsonb NOT NULL,
  observed_at TIMESTAMP WITH TIME ZONE NOT NULL,
  source_refs JSONB NOT NULL,
  metadata JSONB DEFAULT '{}'::jsonb NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  CONSTRAINT uq_model_revisions_version_model
    UNIQUE (registry_version_id, model_definition_id),
  CONSTRAINT uq_model_revisions_revision_key UNIQUE (revision_key),
  CONSTRAINT ck_model_revisions_lifecycle
    CHECK (lifecycle IN ('stable','preview','deprecated','legacy','shutdown')),
  CONSTRAINT ck_model_revisions_inactive_not_routeable
    CHECK (
      lifecycle NOT IN ('deprecated','legacy','shutdown') OR route_eligible = false
    ),
  CONSTRAINT ck_model_revisions_regions_array
    CHECK (jsonb_typeof(regions) = 'array'),
  CONSTRAINT ck_model_revisions_sources_array
    CHECK (jsonb_typeof(source_refs) = 'array')
);

-- statement-breakpoint

CREATE TABLE model_capabilities (
  capability_key VARCHAR(128) PRIMARY KEY,
  description TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
);

-- statement-breakpoint

CREATE TABLE model_capability_claims (
  id UUID PRIMARY KEY,
  registry_version_id UUID NOT NULL
    REFERENCES model_registry_versions(id) ON DELETE RESTRICT,
  model_revision_id UUID NOT NULL REFERENCES model_revisions(id) ON DELETE RESTRICT,
  capability_key VARCHAR(128) NOT NULL
    REFERENCES model_capabilities(capability_key) ON DELETE RESTRICT,
  support VARCHAR(16) NOT NULL,
  limits JSONB DEFAULT '{}'::jsonb NOT NULL,
  confidence VARCHAR(24) NOT NULL,
  observed_at TIMESTAMP WITH TIME ZONE NOT NULL,
  source_ref TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  CONSTRAINT uq_model_capability_claims_revision_capability
    UNIQUE (model_revision_id, capability_key),
  CONSTRAINT ck_model_capability_claims_support
    CHECK (support IN ('full','partial','none','unknown')),
  CONSTRAINT ck_model_capability_claims_confidence
    CHECK (confidence IN ('verified_docs','live_test','inferred')),
  CONSTRAINT ck_model_capability_claims_limits_object
    CHECK (jsonb_typeof(limits) = 'object')
);

-- statement-breakpoint

CREATE TABLE model_pricing_snapshots (
  id UUID PRIMARY KEY,
  registry_version_id UUID NOT NULL
    REFERENCES model_registry_versions(id) ON DELETE RESTRICT,
  model_revision_id UUID NOT NULL REFERENCES model_revisions(id) ON DELETE RESTRICT,
  metric VARCHAR(128) NOT NULL,
  currency CHAR(3) DEFAULT 'USD' NOT NULL,
  unit VARCHAR(128) NOT NULL,
  price NUMERIC(24,10) NOT NULL,
  minimum_charge NUMERIC(24,10),
  region VARCHAR(64),
  effective_from TIMESTAMP WITH TIME ZONE NOT NULL,
  observed_at TIMESTAMP WITH TIME ZONE NOT NULL,
  expires_at TIMESTAMP WITH TIME ZONE,
  source_ref TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  CONSTRAINT uq_model_pricing_snapshot_identity
    UNIQUE (model_revision_id, metric, unit, effective_from, region),
  CONSTRAINT ck_model_pricing_currency CHECK (currency = 'USD'),
  CONSTRAINT ck_model_pricing_price CHECK (price >= 0),
  CONSTRAINT ck_model_pricing_minimum CHECK (minimum_charge IS NULL OR minimum_charge >= 0),
  CONSTRAINT ck_model_pricing_expiry
    CHECK (expires_at IS NULL OR expires_at >= effective_from)
);

-- statement-breakpoint

CREATE TABLE model_benchmark_scores (
  id UUID PRIMARY KEY,
  registry_version_id UUID NOT NULL
    REFERENCES model_registry_versions(id) ON DELETE RESTRICT,
  model_revision_id UUID NOT NULL REFERENCES model_revisions(id) ON DELETE RESTRICT,
  profile VARCHAR(128) NOT NULL,
  dataset_version VARCHAR(128) NOT NULL,
  run_id VARCHAR(255) NOT NULL,
  sample_count INTEGER NOT NULL,
  score NUMERIC(8,4) NOT NULL,
  confidence_low NUMERIC(8,4),
  confidence_high NUMERIC(8,4),
  statistics JSONB DEFAULT '{}'::jsonb NOT NULL,
  observed_at TIMESTAMP WITH TIME ZONE NOT NULL,
  source_ref TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  CONSTRAINT uq_model_benchmark_run UNIQUE (model_revision_id, profile, run_id),
  CONSTRAINT ck_model_benchmark_sample_count CHECK (sample_count > 0),
  CONSTRAINT ck_model_benchmark_score CHECK (score BETWEEN 0 AND 100),
  CONSTRAINT ck_model_benchmark_ci_pair
    CHECK ((confidence_low IS NULL) = (confidence_high IS NULL)),
  CONSTRAINT ck_model_benchmark_ci_contains_score
    CHECK (
      confidence_low IS NULL OR
      (confidence_low <= score AND confidence_high >= score)
    ),
  CONSTRAINT ck_model_benchmark_statistics_object
    CHECK (jsonb_typeof(statistics) = 'object')
);

-- statement-breakpoint

CREATE TABLE model_routing_profiles (
  id UUID PRIMARY KEY,
  registry_version_id UUID NOT NULL
    REFERENCES model_registry_versions(id) ON DELETE RESTRICT,
  profile_key VARCHAR(128) NOT NULL,
  required_capabilities JSONB DEFAULT '[]'::jsonb NOT NULL,
  weights JSONB NOT NULL,
  minimum_quality NUMERIC(8,4),
  selection_gate VARCHAR(255) NOT NULL,
  source_ref TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  CONSTRAINT uq_model_routing_profile_version
    UNIQUE (registry_version_id, profile_key),
  CONSTRAINT ck_model_routing_profile_required_array
    CHECK (jsonb_typeof(required_capabilities) = 'array'),
  CONSTRAINT ck_model_routing_profile_weights_object
    CHECK (jsonb_typeof(weights) = 'object'),
  CONSTRAINT ck_model_routing_profile_min_quality
    CHECK (minimum_quality IS NULL OR minimum_quality BETWEEN 0 AND 100)
);

-- statement-breakpoint

CREATE TABLE model_routing_profile_candidates (
  routing_profile_id UUID NOT NULL
    REFERENCES model_routing_profiles(id) ON DELETE CASCADE,
  model_definition_id UUID NOT NULL
    REFERENCES model_definitions(id) ON DELETE RESTRICT,
  ordinal INTEGER NOT NULL,
  stable_fallback BOOLEAN DEFAULT false NOT NULL,
  PRIMARY KEY (routing_profile_id, model_definition_id),
  CONSTRAINT uq_model_routing_profile_candidate_ordinal
    UNIQUE (routing_profile_id, ordinal),
  CONSTRAINT ck_model_routing_profile_candidate_ordinal CHECK (ordinal >= 0)
);

-- statement-breakpoint

CREATE INDEX ix_model_revisions_registry_lifecycle
ON model_revisions (registry_version_id, lifecycle, route_eligible);

-- statement-breakpoint

CREATE INDEX ix_model_capability_claims_capability_support
ON model_capability_claims (registry_version_id, capability_key, support);

-- statement-breakpoint

CREATE INDEX ix_model_pricing_model_effective
ON model_pricing_snapshots (model_revision_id, effective_from, expires_at);

-- statement-breakpoint

CREATE INDEX ix_model_benchmark_profile_observed
ON model_benchmark_scores (model_revision_id, profile, observed_at DESC);

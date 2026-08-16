CREATE TABLE organization_model_policies (
  organization_id UUID PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
  version INTEGER DEFAULT 1 NOT NULL,
  disabled_providers JSONB DEFAULT '[]'::jsonb NOT NULL,
  allowed_regions JSONB DEFAULT '[]'::jsonb NOT NULL,
  preferred_models JSONB DEFAULT '[]'::jsonb NOT NULL,
  max_cost_class VARCHAR(64),
  data_handling_restrictions JSONB DEFAULT '[]'::jsonb NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  CONSTRAINT ck_organization_model_policy_version CHECK (version >= 1),
  CONSTRAINT ck_organization_model_policy_disabled_array
    CHECK (jsonb_typeof(disabled_providers) = 'array'),
  CONSTRAINT ck_organization_model_policy_regions_array
    CHECK (jsonb_typeof(allowed_regions) = 'array'),
  CONSTRAINT ck_organization_model_policy_preferred_array
    CHECK (jsonb_typeof(preferred_models) = 'array'),
  CONSTRAINT ck_organization_model_policy_restrictions_array
    CHECK (jsonb_typeof(data_handling_restrictions) = 'array')
);

-- statement-breakpoint

ALTER TABLE organization_model_policies ENABLE ROW LEVEL SECURITY;

-- statement-breakpoint

CREATE POLICY tenant_isolation_organization_model_policies
ON organization_model_policies
USING (organization_id = lumi_current_organization_id())
WITH CHECK (organization_id = lumi_current_organization_id());

-- statement-breakpoint

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lumi_app') THEN
    GRANT SELECT ON TABLE
      model_registry_versions,
      model_providers,
      model_definitions,
      model_revisions,
      model_capabilities,
      model_capability_claims,
      model_pricing_snapshots,
      model_benchmark_scores,
      model_routing_profiles,
      model_routing_profile_candidates
    TO lumi_app;
    REVOKE INSERT, UPDATE, DELETE ON TABLE
      model_registry_versions,
      model_providers,
      model_definitions,
      model_revisions,
      model_capabilities,
      model_capability_claims,
      model_pricing_snapshots,
      model_benchmark_scores,
      model_routing_profiles,
      model_routing_profile_candidates
    FROM lumi_app;
    GRANT SELECT, INSERT, UPDATE ON TABLE organization_model_policies TO lumi_app;
    REVOKE DELETE ON TABLE organization_model_policies FROM lumi_app;
  END IF;
END;
$$;

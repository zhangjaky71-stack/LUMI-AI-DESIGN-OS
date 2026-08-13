"""Add versioned model capability registry control-plane facts.

Revision ID: 0010_capability_registry
Revises: 0009_idempotency_side_effects
Create Date: 2026-08-13
"""

from alembic import op

revision = "0010_capability_registry"
down_revision = "0009_idempotency_side_effects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE model_registry_versions (
            id uuid PRIMARY KEY,
            version integer NOT NULL UNIQUE CHECK (version > 0),
            source_registry_version varchar(64) NOT NULL,
            content_hash char(64) NOT NULL UNIQUE,
            observed_at timestamptz NOT NULL,
            source_ref varchar(512) NOT NULL,
            activated_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE model_registry_models (
            id uuid PRIMARY KEY,
            registry_version_id uuid NOT NULL
                REFERENCES model_registry_versions(id) ON DELETE CASCADE,
            model_key varchar(512) NOT NULL,
            provider varchar(100) NOT NULL,
            model varchar(255) NOT NULL,
            lifecycle varchar(32) NOT NULL,
            route_eligible boolean NOT NULL,
            regions_json jsonb NOT NULL DEFAULT '[]'::jsonb,
            latency_class varchar(32),
            benchmark_status varchar(64) NOT NULL DEFAULT 'NOT_MEASURED',
            observed_at timestamptz NOT NULL,
            source_ref varchar(1024) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_model_registry_models_version_key
                UNIQUE (registry_version_id, model_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE model_capability_claims (
            id uuid PRIMARY KEY,
            registry_version_id uuid NOT NULL
                REFERENCES model_registry_versions(id) ON DELETE CASCADE,
            model_key varchar(512) NOT NULL,
            capability varchar(100) NOT NULL,
            support varchar(16) NOT NULL,
            limits_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            confidence varchar(32) NOT NULL,
            observed_at timestamptz NOT NULL,
            source_ref varchar(1024) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_model_capability_claim_version_key
                UNIQUE (registry_version_id, model_key, capability),
            CONSTRAINT ck_model_capability_claim_support
                CHECK (support IN ('full','partial','none','unknown')),
            CONSTRAINT ck_model_capability_claim_confidence
                CHECK (confidence IN ('verified_docs','live_test','inferred'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE model_pricing_snapshots (
            id uuid PRIMARY KEY,
            registry_version_id uuid NOT NULL
                REFERENCES model_registry_versions(id) ON DELETE CASCADE,
            price_snapshot_key varchar(128) NOT NULL UNIQUE,
            model_key varchar(512) NOT NULL,
            currency char(3) NOT NULL,
            unit varchar(128) NOT NULL,
            price numeric(30,10) NOT NULL CHECK (price >= 0),
            minimum_charge numeric(30,10),
            effective_from timestamptz NOT NULL,
            valid_until timestamptz,
            observed_at timestamptz NOT NULL,
            source_ref varchar(1024) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_model_pricing_currency CHECK (currency ~ '^[A-Z]{3}$'),
            CONSTRAINT ck_model_pricing_window
                CHECK (valid_until IS NULL OR valid_until > effective_from)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE model_benchmark_scores (
            id uuid PRIMARY KEY,
            registry_version_id uuid NOT NULL
                REFERENCES model_registry_versions(id) ON DELETE CASCADE,
            model_key varchar(512) NOT NULL,
            profile varchar(100) NOT NULL,
            score numeric(10,4) NOT NULL CHECK (score >= 0 AND score <= 100),
            dataset_version varchar(128) NOT NULL,
            run_id varchar(255) NOT NULL,
            sample_count integer NOT NULL CHECK (sample_count > 0),
            statistics_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            confidence varchar(32) NOT NULL,
            observed_at timestamptz NOT NULL,
            source_ref varchar(1024) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_model_benchmark_version_identity
                UNIQUE (registry_version_id, model_key, profile, dataset_version, run_id),
            CONSTRAINT ck_model_benchmark_confidence
                CHECK (confidence IN ('verified_docs','live_test','inferred'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE model_routing_profiles (
            id uuid PRIMARY KEY,
            registry_version_id uuid NOT NULL
                REFERENCES model_registry_versions(id) ON DELETE CASCADE,
            profile varchar(150) NOT NULL,
            required_capabilities_json jsonb NOT NULL,
            candidate_models_json jsonb NOT NULL,
            weights_json jsonb NOT NULL,
            minimum_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            observed_at timestamptz NOT NULL,
            source_ref varchar(1024) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_model_routing_profile_version
                UNIQUE (registry_version_id, profile)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE organization_model_policies (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL
                REFERENCES organizations(id) ON DELETE CASCADE,
            policy_version integer NOT NULL CHECK (policy_version > 0),
            disabled_providers_json jsonb NOT NULL DEFAULT '[]'::jsonb,
            denied_models_json jsonb NOT NULL DEFAULT '[]'::jsonb,
            allowed_regions_json jsonb NOT NULL DEFAULT '[]'::jsonb,
            max_cost_class varchar(64),
            preferred_models_json jsonb NOT NULL DEFAULT '[]'::jsonb,
            data_handling_restrictions_json jsonb NOT NULL DEFAULT '[]'::jsonb,
            effective_from timestamptz NOT NULL DEFAULT now(),
            effective_to timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_organization_model_policy_version
                UNIQUE (organization_id, policy_version),
            CONSTRAINT ck_organization_model_policy_window
                CHECK (effective_to IS NULL OR effective_to > effective_from)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_model_registry_models_provider "
        "ON model_registry_models (registry_version_id, provider)"
    )
    op.execute(
        "CREATE INDEX ix_model_capability_claim_lookup "
        "ON model_capability_claims (registry_version_id, capability, support)"
    )
    op.execute(
        "CREATE INDEX ix_model_pricing_lookup "
        "ON model_pricing_snapshots (model_key, effective_from, valid_until)"
    )
    op.execute(
        "CREATE INDEX ix_model_benchmark_lookup "
        "ON model_benchmark_scores (model_key, profile, observed_at)"
    )
    op.execute(
        "CREATE INDEX ix_org_model_policy_effective "
        "ON organization_model_policies (organization_id, effective_from, effective_to)"
    )
    for table in (
        "model_registry_versions",
        "model_registry_models",
        "model_capability_claims",
        "model_pricing_snapshots",
        "model_benchmark_scores",
        "model_routing_profiles",
        "organization_model_policies",
    ):
        op.execute(f"GRANT SELECT ON {table} TO lumi_app")


def downgrade() -> None:
    for table in (
        "organization_model_policies",
        "model_routing_profiles",
        "model_benchmark_scores",
        "model_pricing_snapshots",
        "model_capability_claims",
        "model_registry_models",
        "model_registry_versions",
    ):
        op.execute(f"DROP TABLE {table}")

"""Add durable Hosted video-generation runtime snapshots.

Revision ID: 0023_video_generation_runtime
Revises: 0022_langgraph_postgres_runtime
Create Date: 2026-08-20

NODE-48's historical seven-table SQL remains non-canonical. Production keeps only
runtime recovery state here; Artifact lineage, Provider cost accounting and events
continue to use the canonical Artifact, NODE-27 and outbox schemas.
"""

from alembic import op

revision = "0023_video_generation_runtime"
down_revision = "0022_langgraph_postgres_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE video_generation_jobs (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            task_id uuid NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            operation_id uuid NOT NULL,
            semantic_hash char(64) NOT NULL CHECK (semantic_hash ~ '^[0-9a-f]{64}$'),
            storyboard_hash char(64) NOT NULL CHECK (storyboard_hash ~ '^[0-9a-f]{64}$'),
            status varchar(32) NOT NULL CHECK (
                status IN ('SUBMITTING','WAITING_EXTERNAL','VALIDATING','COMPOSING','COMPLETED','PARTIAL','FAILED','CANCELLED')
            ),
            estimated_cost_usd numeric(20,8) NOT NULL DEFAULT 0 CHECK (estimated_cost_usd >= 0),
            actual_cost_usd numeric(20,8) NOT NULL DEFAULT 0 CHECK (actual_cost_usd >= 0),
            spec_snapshot jsonb NOT NULL,
            job_snapshot jsonb NOT NULL,
            final_artifact_version_id uuid NULL REFERENCES artifact_versions(id) ON DELETE SET NULL,
            error_code varchar(255) NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            version integer NOT NULL DEFAULT 1 CHECK (version > 0),
            CONSTRAINT video_generation_job_operation_identity UNIQUE (organization_id, operation_id),
            CONSTRAINT video_generation_job_task_identity UNIQUE (organization_id, task_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_video_generation_jobs_org_project "
        "ON video_generation_jobs (organization_id, project_id)"
    )
    op.execute(
        "CREATE INDEX ix_video_generation_jobs_status_updated "
        "ON video_generation_jobs (status, updated_at)"
    )
    op.execute(
        """
        CREATE TABLE video_provider_jobs (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            video_job_id uuid NOT NULL REFERENCES video_generation_jobs(id) ON DELETE CASCADE,
            shot_id varchar(128) NOT NULL,
            paid_operation_id uuid NOT NULL,
            request_hash char(64) NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
            provider varchar(100) NOT NULL,
            model varchar(255) NOT NULL,
            provider_request_id varchar(512) NULL,
            status varchar(32) NOT NULL CHECK (status IN ('PENDING','SUCCEEDED','FAILED','CANCELLED')),
            active boolean NOT NULL DEFAULT true,
            result_snapshot jsonb NOT NULL,
            attempt_ordinal integer NOT NULL DEFAULT 0 CHECK (attempt_ordinal >= 0),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            version integer NOT NULL DEFAULT 1 CHECK (version > 0),
            CONSTRAINT video_provider_job_paid_attempt_identity
                UNIQUE (video_job_id, shot_id, paid_operation_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_video_provider_jobs_org_job "
        "ON video_provider_jobs (organization_id, video_job_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_video_provider_jobs_active_shot "
        "ON video_provider_jobs (video_job_id, shot_id) WHERE active"
    )
    # Recovery history is mutable only through state advancement. No production
    # runtime needs physical DELETE; keeping DELETE revoked prevents a Worker from
    # erasing paid-attempt recovery evidence.
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON video_generation_jobs, video_provider_jobs TO lumi_app"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS video_provider_jobs")
    op.execute("DROP TABLE IF EXISTS video_generation_jobs")

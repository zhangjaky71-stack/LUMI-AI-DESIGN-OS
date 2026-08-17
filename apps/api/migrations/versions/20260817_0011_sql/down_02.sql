DROP TABLE artifact_outbox_events;

-- statement-breakpoint

DROP TABLE artifact_gc_audits;

-- statement-breakpoint

DROP TABLE artifact_gc_marks;

-- statement-breakpoint

DROP TABLE artifact_version_approvals;

-- statement-breakpoint

DROP INDEX ix_artifact_provenance_prompt_hash;

-- statement-breakpoint

DROP INDEX ix_artifact_provenance_provider_model;

-- statement-breakpoint

DROP INDEX ix_artifact_provenance_generation_id;

-- statement-breakpoint

DROP INDEX ix_artifact_provenance_task_id;

-- statement-breakpoint

DROP INDEX ix_artifact_provenance_agent_run_id;

-- statement-breakpoint

ALTER TABLE artifact_provenance
    DROP COLUMN missing_fields_json,
    DROP COLUMN completeness_score,
    DROP COLUMN completeness_status,
    DROP COLUMN constraint_snapshot_hash,
    DROP COLUMN code_git_sha,
    DROP COLUMN agent_version,
    DROP COLUMN compiler_version,
    DROP COLUMN recipe_version,
    DROP COLUMN prompt_template_version,
    DROP COLUMN prompt_hash,
    DROP COLUMN provider_request_id,
    DROP COLUMN model,
    DROP COLUMN provider,
    DROP COLUMN generation_id,
    DROP COLUMN task_id,
    DROP COLUMN agent_run_id;

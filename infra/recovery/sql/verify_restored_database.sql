\set ON_ERROR_STOP on

-- NODE-68 post-restore verification. This file is intentionally read-only.
-- Any hard invariant row returned with violations > 0 is a STOP SHIP condition.

WITH invariant_results AS (
    SELECT 'alembic_single_version' AS invariant,
           CASE WHEN to_regclass('public.alembic_version') IS NULL THEN 1
                ELSE GREATEST((SELECT count(*) FROM alembic_version) - 1, 0)
           END::bigint AS violations
    UNION ALL
    SELECT 'project_workspace_tenant_match', count(*)
      FROM projects p
      JOIN workspaces w ON w.id = p.workspace_id
     WHERE p.organization_id <> w.organization_id
    UNION ALL
    SELECT 'asset_project_tenant_match', count(*)
      FROM assets a
      JOIN projects p ON p.id = a.project_id
     WHERE a.project_id IS NOT NULL
       AND a.organization_id <> p.organization_id
    UNION ALL
    SELECT 'asset_file_parent_tenant_match', count(*)
      FROM asset_files af
      JOIN assets a ON a.id = af.asset_id
     WHERE af.organization_id <> a.organization_id
    UNION ALL
    SELECT 'artifact_version_parent_tenant_match', count(*)
      FROM artifact_versions av
      JOIN artifacts a ON a.id = av.artifact_id
     WHERE av.organization_id <> a.organization_id
        OR av.project_id <> a.project_id
    UNION ALL
    SELECT 'artifact_file_parent_tenant_match', count(*)
      FROM artifact_files af
      JOIN artifact_versions av ON av.id = af.artifact_version_id
     WHERE af.organization_id <> av.organization_id
    UNION ALL
    SELECT 'agent_run_control_parent_match', count(*)
      FROM agent_run_control arc
      JOIN agent_runs ar ON ar.id = arc.agent_run_id
     WHERE arc.organization_id <> ar.organization_id
        OR arc.project_id <> ar.project_id
    UNION ALL
    SELECT 'task_agent_run_parent_match', count(*)
      FROM tasks t
      JOIN agent_runs ar ON ar.id = t.agent_run_id
     WHERE t.agent_run_id IS NOT NULL
       AND (t.organization_id <> ar.organization_id OR t.project_id <> ar.project_id)
    UNION ALL
    SELECT 'cost_ledger_duplicate_operation_entry', count(*)
      FROM (
        SELECT operation_id, entry_type
          FROM cost_ledger
         WHERE operation_id IS NOT NULL
         GROUP BY operation_id, entry_type
        HAVING count(*) > 1
      ) duplicates
    UNION ALL
    SELECT 'asset_file_checksum_format', count(*)
      FROM asset_files
     WHERE checksum_sha256 !~ '^[0-9a-fA-F]{64}$'
    UNION ALL
    SELECT 'artifact_file_checksum_format', count(*)
      FROM artifact_files
     WHERE checksum_sha256 !~ '^[0-9a-fA-F]{64}$'
)
SELECT 'INVARIANT' AS record_type, invariant, violations::text AS value
  FROM invariant_results
 ORDER BY invariant;

-- Recovery workload is informational. Operators use the planner/runbooks to decide
-- how each row is handled; these counts are not automatically mutated here.
SELECT 'WORKLOAD', 'outbox_unpublished', count(*)::text
  FROM outbox_events
 WHERE published_at IS NULL
UNION ALL
SELECT 'WORKLOAD', 'dead_letter_unreplayed', count(*)::text
  FROM dead_letter_records
 WHERE replayed_at IS NULL
UNION ALL
SELECT 'WORKLOAD', 'idempotency_ambiguous', count(*)::text
  FROM idempotency_operations
 WHERE status = 'ambiguous'
UNION ALL
SELECT 'WORKLOAD', 'idempotency_expired_in_progress', count(*)::text
  FROM idempotency_operations
 WHERE status = 'in_progress'
   AND lease_expires_at IS NOT NULL
   AND lease_expires_at < now()
UNION ALL
SELECT 'WORKLOAD', 'task_expired_running', count(*)::text
  FROM tasks
 WHERE status = 'running'
   AND lease_expires_at IS NOT NULL
   AND lease_expires_at < now()
UNION ALL
SELECT 'WORKLOAD', 'agent_control_non_terminal', count(*)::text
  FROM agent_run_control
 WHERE control_status IN ('pending','running','interrupted')
UNION ALL
SELECT 'WORKLOAD', 'asset_object_refs', count(*)::text FROM asset_files
UNION ALL
SELECT 'WORKLOAD', 'artifact_object_refs', count(*)::text FROM artifact_files
UNION ALL
SELECT 'WORKLOAD', 'cost_ledger_entries', count(*)::text FROM cost_ledger
ORDER BY 2;

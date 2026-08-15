\set ON_ERROR_STOP on

-- NODE-68 recovery inventory. Read only. Do not feed this output directly to a
-- mutation loop; classify each row with the recovery planner/runbook first.

SELECT 'COUNT' AS record_type, 'outbox_unpublished' AS category, count(*)::text AS item_id,
       NULL::text AS status, NULL::text AS external_ref
  FROM outbox_events WHERE published_at IS NULL
UNION ALL
SELECT 'COUNT', 'dead_letter_unreplayed', count(*)::text, NULL, NULL
  FROM dead_letter_records WHERE replayed_at IS NULL
UNION ALL
SELECT 'COUNT', 'idempotency_ambiguous', count(*)::text, NULL, NULL
  FROM idempotency_operations WHERE lower(status) = 'ambiguous'
UNION ALL
SELECT 'COUNT', 'idempotency_in_progress', count(*)::text, NULL, NULL
  FROM idempotency_operations WHERE lower(status) = 'in_progress'
UNION ALL
SELECT 'COUNT', 'tasks_running_or_waiting', count(*)::text, NULL, NULL
  FROM tasks
 WHERE lower(status) IN (
   'pending','ready','running','retry','failed_retryable',
   'waiting_user','waiting_for_user','waiting_external','waiting_for_external'
 )
UNION ALL
SELECT 'COUNT', 'agent_runs_non_terminal', count(*)::text, NULL, NULL
  FROM agent_run_control WHERE lower(control_status) IN ('pending','running','interrupted')
ORDER BY category;

\if :{?include_ids}
SELECT 'ITEM', 'idempotency_operation', id::text, status,
       COALESCE(provider_request_id, '')
  FROM idempotency_operations
 WHERE lower(status) IN ('new','in_progress','failed_retryable','ambiguous')
 ORDER BY updated_at, id
 LIMIT 500;

SELECT 'ITEM', 'task', id::text, status,
       COALESCE(external_ref, '')
  FROM tasks
 WHERE lower(status) IN (
   'pending','ready','running','retry','failed_retryable',
   'waiting_user','waiting_for_user','waiting_external','waiting_for_external'
 )
 ORDER BY updated_at, id
 LIMIT 500;

SELECT 'ITEM', 'agent_run', agent_run_id::text, control_status,
       COALESCE(checkpoint_id, '')
  FROM agent_run_control
 WHERE lower(control_status) IN ('pending','running','interrupted')
 ORDER BY updated_at, agent_run_id
 LIMIT 500;

SELECT 'ITEM', 'outbox_event', id::text,
       CASE WHEN published_at IS NULL THEN 'unpublished' ELSE 'published' END,
       event_name
  FROM outbox_events
 WHERE published_at IS NULL
 ORDER BY created_at, id
 LIMIT 500;
\endif

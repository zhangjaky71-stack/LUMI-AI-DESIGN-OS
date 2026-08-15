\set ON_ERROR_STOP on
\pset pager off

SELECT 'database' AS section, datname, numbackends, xact_commit, xact_rollback,
       blks_read, blks_hit, tup_returned, tup_fetched, tup_inserted, tup_updated, tup_deleted,
       temp_files, temp_bytes, deadlocks
  FROM pg_stat_database
 WHERE datname = current_database();

SELECT 'connections' AS section, state, wait_event_type, wait_event, count(*) AS sessions
  FROM pg_stat_activity
 WHERE datname = current_database()
 GROUP BY state, wait_event_type, wait_event
 ORDER BY sessions DESC;

SELECT 'locks' AS section, locktype, mode, granted, count(*) AS locks
  FROM pg_locks
 GROUP BY locktype, mode, granted
 ORDER BY locks DESC
 LIMIT 50;

SELECT to_regclass('pg_stat_statements') IS NOT NULL AS has_pgss \gset
\if :has_pgss
SELECT 'pg_stat_statements' AS section,
       calls,
       round(total_exec_time::numeric, 3) AS total_exec_ms,
       round(mean_exec_time::numeric, 3) AS mean_exec_ms,
       rows,
       shared_blks_hit,
       shared_blks_read,
       temp_blks_written,
       left(regexp_replace(query, '\\s+', ' ', 'g'), 500) AS normalized_query
  FROM pg_stat_statements
 ORDER BY total_exec_time DESC
 LIMIT 25;
\else
\echo '[perf-db] pg_stat_statements is not available; query-level ranking omitted'
\endif

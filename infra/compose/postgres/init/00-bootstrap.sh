#!/usr/bin/env bash
set -euo pipefail

psql \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set ON_ERROR_STOP=on \
  --set app_password="$POSTGRES_APP_PASSWORD" \
  --set migration_password="$POSTGRES_MIGRATION_PASSWORD" \
  --set db_name="$POSTGRES_DB" <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

SELECT 'CREATE ROLE lumi_app LOGIN PASSWORD ' || quote_literal(:'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lumi_app') \gexec
ALTER ROLE lumi_app PASSWORD :'app_password';

SELECT 'CREATE ROLE lumi_migration LOGIN PASSWORD ' || quote_literal(:'migration_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lumi_migration') \gexec
ALTER ROLE lumi_migration PASSWORD :'migration_password';

GRANT CONNECT ON DATABASE :"db_name" TO lumi_app, lumi_migration;
GRANT USAGE ON SCHEMA public TO lumi_app;
GRANT USAGE, CREATE ON SCHEMA public TO lumi_migration;
SQL

-- LOCAL/CI deterministic fixture. Execute with the migration role after `alembic upgrade head`.
-- UUIDs are stable UUIDv7-shaped identifiers so tests and docs can reference them.

INSERT INTO users (id, email, display_name)
VALUES
  ('01910000-0000-7000-8000-000000000011', 'owner-a@lumi.local', 'Owner A'),
  ('01910000-0000-7000-8000-000000000012', 'owner-b@lumi.local', 'Owner B')
ON CONFLICT DO NOTHING;

INSERT INTO organizations (id, name, slug, plan)
VALUES
  ('01910000-0000-7000-8000-000000000001', 'LUMI Fixture A', 'lumi-fixture-a', 'pro'),
  ('01910000-0000-7000-8000-000000000002', 'LUMI Fixture B', 'lumi-fixture-b', 'pro')
ON CONFLICT DO NOTHING;

INSERT INTO organization_members (id, organization_id, user_id, role)
VALUES
  ('01910000-0000-7000-8000-000000000101', '01910000-0000-7000-8000-000000000001', '01910000-0000-7000-8000-000000000011', 'owner'),
  ('01910000-0000-7000-8000-000000000102', '01910000-0000-7000-8000-000000000002', '01910000-0000-7000-8000-000000000012', 'owner')
ON CONFLICT DO NOTHING;

INSERT INTO workspaces (id, organization_id, name)
VALUES
  ('01910000-0000-7000-8000-000000000021', '01910000-0000-7000-8000-000000000001', 'Fixture Workspace A'),
  ('01910000-0000-7000-8000-000000000022', '01910000-0000-7000-8000-000000000002', 'Fixture Workspace B')
ON CONFLICT DO NOTHING;

INSERT INTO brands (id, organization_id, name, profile_json)
VALUES
  ('01910000-0000-7000-8000-000000000041', '01910000-0000-7000-8000-000000000001', 'Fixture Brand A', '{"tone":"minimal"}'::jsonb),
  ('01910000-0000-7000-8000-000000000042', '01910000-0000-7000-8000-000000000002', 'Fixture Brand B', '{"tone":"editorial"}'::jsonb)
ON CONFLICT DO NOTHING;

INSERT INTO projects (id, organization_id, workspace_id, name, status, brand_id)
VALUES
  ('01910000-0000-7000-8000-000000000031', '01910000-0000-7000-8000-000000000001', '01910000-0000-7000-8000-000000000021', 'Fixture Project A', 'active', '01910000-0000-7000-8000-000000000041'),
  ('01910000-0000-7000-8000-000000000032', '01910000-0000-7000-8000-000000000002', '01910000-0000-7000-8000-000000000022', 'Fixture Project B', 'active', '01910000-0000-7000-8000-000000000042')
ON CONFLICT DO NOTHING;

INSERT INTO assets (id, organization_id, project_id, source, mime_type, status)
VALUES
  ('01910000-0000-7000-8000-000000000051', '01910000-0000-7000-8000-000000000001', '01910000-0000-7000-8000-000000000031', 'upload', 'image/png', 'ready'),
  ('01910000-0000-7000-8000-000000000052', '01910000-0000-7000-8000-000000000002', '01910000-0000-7000-8000-000000000032', 'upload', 'image/png', 'ready')
ON CONFLICT DO NOTHING;

INSERT INTO asset_files (id, organization_id, asset_id, bucket, object_key, checksum_sha256, byte_size, width, height)
VALUES
  ('01910000-0000-7000-8000-000000000151', '01910000-0000-7000-8000-000000000001', '01910000-0000-7000-8000-000000000051', 'lumi-assets', 'fixture-a/input.png', repeat('a', 64), 1024, 512, 512),
  ('01910000-0000-7000-8000-000000000152', '01910000-0000-7000-8000-000000000002', '01910000-0000-7000-8000-000000000052', 'lumi-assets', 'fixture-b/input.png', repeat('b', 64), 2048, 512, 512)
ON CONFLICT DO NOTHING;

INSERT INTO tasks (id, organization_id, project_id, task_type, name, status)
VALUES
  ('01910000-0000-7000-8000-000000000061', '01910000-0000-7000-8000-000000000001', '01910000-0000-7000-8000-000000000031', 'research', 'Fixture Research', 'succeeded'),
  ('01910000-0000-7000-8000-000000000062', '01910000-0000-7000-8000-000000000001', '01910000-0000-7000-8000-000000000031', 'generate', 'Fixture Generate', 'ready'),
  ('01910000-0000-7000-8000-000000000063', '01910000-0000-7000-8000-000000000002', '01910000-0000-7000-8000-000000000032', 'generate', 'Fixture Tenant B', 'ready')
ON CONFLICT DO NOTHING;

INSERT INTO task_dependencies (organization_id, task_id, depends_on_task_id)
VALUES ('01910000-0000-7000-8000-000000000001', '01910000-0000-7000-8000-000000000062', '01910000-0000-7000-8000-000000000061')
ON CONFLICT DO NOTHING;

INSERT INTO design_documents (id, organization_id, project_id, name, ir_version)
VALUES ('01910000-0000-7000-8000-000000000081', '01910000-0000-7000-8000-000000000001', '01910000-0000-7000-8000-000000000031', 'Fixture Document', 'design-ir-v1')
ON CONFLICT DO NOTHING;

INSERT INTO design_document_versions (id, organization_id, design_document_id, version_number, content_json, content_hash)
VALUES ('01910000-0000-7000-8000-000000000082', '01910000-0000-7000-8000-000000000001', '01910000-0000-7000-8000-000000000081', 1, '{"nodes":[]}'::jsonb, repeat('c', 64))
ON CONFLICT DO NOTHING;

INSERT INTO artifacts (id, organization_id, project_id, kind, design_document_id)
VALUES ('01910000-0000-7000-8000-000000000091', '01910000-0000-7000-8000-000000000001', '01910000-0000-7000-8000-000000000031', 'design_document', '01910000-0000-7000-8000-000000000081')
ON CONFLICT DO NOTHING;

INSERT INTO artifact_branches (id, organization_id, project_id, artifact_id, name)
VALUES ('01910000-0000-7000-8000-000000000092', '01910000-0000-7000-8000-000000000001', '01910000-0000-7000-8000-000000000031', '01910000-0000-7000-8000-000000000091', 'main')
ON CONFLICT DO NOTHING;

INSERT INTO artifact_versions (id, organization_id, artifact_id, branch_id, version_number, status, content_hash)
VALUES ('01910000-0000-7000-8000-000000000093', '01910000-0000-7000-8000-000000000001', '01910000-0000-7000-8000-000000000091', '01910000-0000-7000-8000-000000000092', 1, 'ready', repeat('d', 64))
ON CONFLICT DO NOTHING;

INSERT INTO idempotency_operations (id, organization_id, idempotency_key, operation_type, request_hash, status)
VALUES ('01910000-0000-7000-8000-000000000071', '01910000-0000-7000-8000-000000000001', 'fixture:generation:1', 'image.generate', repeat('e', 64), 'completed')
ON CONFLICT DO NOTHING;

INSERT INTO generations (id, organization_id, project_id, operation_id, provider, model, model_version, status)
VALUES ('01910000-0000-7000-8000-000000000072', '01910000-0000-7000-8000-000000000001', '01910000-0000-7000-8000-000000000031', '01910000-0000-7000-8000-000000000071', 'fixture', 'fixture-image-model', 'v1', 'completed')
ON CONFLICT DO NOTHING;

INSERT INTO cost_ledger (id, organization_id, project_id, generation_id, entry_type, amount, currency, quantity, unit)
VALUES ('01910000-0000-7000-8000-000000000073', '01910000-0000-7000-8000-000000000001', '01910000-0000-7000-8000-000000000031', '01910000-0000-7000-8000-000000000072', 'charge', 0.12345678, 'USD', 1.0000000000, 'generation')
ON CONFLICT DO NOTHING;

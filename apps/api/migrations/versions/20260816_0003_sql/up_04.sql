UPDATE project_brief_versions
SET id = project_id
WHERE version_number = 1 AND change_reason = 'migrated baseline brief';

-- statement-breakpoint

UPDATE project_branch_defaults
SET id = project_id
WHERE name = 'main';

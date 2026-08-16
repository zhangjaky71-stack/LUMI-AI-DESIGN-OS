UPDATE organization_members
SET role = 'viewer'
WHERE role IN ('editor', 'billing');

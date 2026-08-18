DROP TRIGGER IF EXISTS trg_platform_break_glass_immutable ON platform_break_glass_grants;

-- statement-breakpoint

DROP FUNCTION IF EXISTS platform_admin_reject_break_glass_mutation();

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_platform_admin_audit_immutable ON platform_admin_audit_events;

-- statement-breakpoint

DROP FUNCTION IF EXISTS platform_admin_reject_audit_mutation();

-- statement-breakpoint

DROP TABLE IF EXISTS platform_break_glass_grants;

-- statement-breakpoint

DROP TABLE IF EXISTS platform_feature_flags;

-- statement-breakpoint

DROP TABLE IF EXISTS platform_admin_audit_events;

-- statement-breakpoint

DROP TABLE IF EXISTS platform_admin_principals;

DROP TRIGGER IF EXISTS trg_provider_health_override_audit_immutable
ON provider_health_override_audit;

-- statement-breakpoint

DROP FUNCTION IF EXISTS lumi_provider_health_audit_immutable();

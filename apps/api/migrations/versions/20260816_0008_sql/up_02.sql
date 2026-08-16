CREATE OR REPLACE FUNCTION lumi_provider_health_audit_immutable()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'provider_health_override_audit is append-only';
END;
$$;

-- statement-breakpoint

CREATE TRIGGER trg_provider_health_override_audit_immutable
BEFORE UPDATE OR DELETE ON provider_health_override_audit
FOR EACH ROW
EXECUTE FUNCTION lumi_provider_health_audit_immutable();

-- statement-breakpoint

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lumi_app') THEN
    GRANT SELECT, INSERT ON TABLE
      provider_health_summaries,
      provider_health_override_audit
    TO lumi_app;
    REVOKE UPDATE, DELETE ON TABLE
      provider_health_summaries,
      provider_health_override_audit
    FROM lumi_app;
  END IF;
END;
$$;

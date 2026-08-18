UPDATE audit_events
SET details_json = details_json || jsonb_build_object('legacy_actor_type', actor_type)
WHERE upper(actor_type) NOT IN ('USER','API_TOKEN','AGENT','SERVICE','PLATFORM_ADMIN');

-- statement-breakpoint

UPDATE audit_events
SET actor_type = CASE
      WHEN upper(actor_type) IN ('USER','API_TOKEN','AGENT','SERVICE','PLATFORM_ADMIN') THEN upper(actor_type)
      ELSE 'SERVICE'
    END,
    actor_id = COALESCE(NULLIF(btrim(actor_id), ''), 'legacy:unknown');

-- statement-breakpoint

ALTER TABLE audit_events ALTER COLUMN actor_id SET NOT NULL;

-- statement-breakpoint

ALTER TABLE audit_events
  ADD CONSTRAINT ck_audit_events_actor_type
  CHECK (actor_type IN ('USER','API_TOKEN','AGENT','SERVICE','PLATFORM_ADMIN'));

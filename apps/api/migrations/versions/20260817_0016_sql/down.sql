DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM image_edit_specs LIMIT 1) THEN
    RAISE EXCEPTION
      'NODE47 downgrade blocked: image edit history exists; preserve provenance before downgrade';
  END IF;
END
$$;

-- statement-breakpoint

DROP TABLE IF EXISTS image_edit_cost_projection;

-- statement-breakpoint

DROP TABLE IF EXISTS image_edit_audits;

-- statement-breakpoint

DROP TABLE IF EXISTS image_edit_pending;

-- statement-breakpoint

DROP TABLE IF EXISTS image_edit_masks;

-- statement-breakpoint

DROP TABLE IF EXISTS image_edit_jobs;

-- statement-breakpoint

DROP TABLE IF EXISTS image_edit_specs;

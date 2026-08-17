DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM asset_intelligence_analysis)
       OR EXISTS (SELECT 1 FROM asset_intelligence_usage_signals)
       OR EXISTS (SELECT 1 FROM asset_intelligence_indexes) THEN
        RAISE EXCEPTION 'NODE-45 downgrade blocked: Asset Intelligence data exists';
    END IF;
END
$$;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_asset_intelligence_usage_scope_guard
ON asset_intelligence_usage_signals;

-- statement-breakpoint

DROP FUNCTION IF EXISTS lumi_asset_intelligence_usage_scope_guard();

-- statement-breakpoint

DROP TABLE asset_intelligence_usage_signals;

-- statement-breakpoint

DROP TRIGGER IF EXISTS trg_asset_intelligence_scope_guard
ON asset_intelligence_analysis;

-- statement-breakpoint

DROP FUNCTION IF EXISTS lumi_asset_intelligence_scope_guard();

-- statement-breakpoint

DROP TABLE asset_intelligence_analysis;

-- statement-breakpoint

DROP TABLE asset_intelligence_indexes;

-- statement-breakpoint

DROP TABLE asset_intelligence_index_counters;

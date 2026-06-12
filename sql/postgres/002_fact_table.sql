-- =========================================================================
-- 002_fact_table.sql — GENERATED from metric_registry.py. Do not hand-edit;
-- edit the registry and regenerate. (The sync job rebuilds this table daily
-- via staging + atomic swap; this file exists for the FIRST deployment.)
-- =========================================================================
CREATE TABLE fact_daily_performance (
  date DATE,
  platform TEXT,
  canonical_key TEXT,
  apple_id BIGINT,
  ios_bundle_id TEXT,
  android_package TEXT,
  app_name TEXT,
  publisher TEXT,
  developer TEXT,
  pod TEXT,
  pod_owner TEXT,
  hou TEXT,
  app_category TEXT,
  ownership_type TEXT,
  is_mapped BOOLEAN,
  store_first_time_installs BIGINT,
  store_redownloads BIGINT,
  store_total_installs BIGINT,
  store_organic_installs BIGINT,
  gp_uninstalls BIGINT,
  apple_restores BIGINT,
  organic_install_share NUMERIC(12,6),
  fb_paid_installs BIGINT,
  gads_paid_installs DOUBLE PRECISION,
  mint_adv_paid_installs BIGINT,
  total_paid_installs DOUBLE PRECISION,
  fb_spend_usd NUMERIC(18,4),
  fb_impressions BIGINT,
  fb_clicks BIGINT,
  fb_purchases BIGINT,
  fb_purchase_value NUMERIC(18,4),
  gads_spend_usd NUMERIC(18,4),
  gads_impressions BIGINT,
  gads_clicks BIGINT,
  gads_conversions NUMERIC(18,4),
  gads_conversions_value NUMERIC(18,4),
  mint_adv_spend_usd NUMERIC(18,4),
  mint_adv_impressions BIGINT,
  mint_adv_clicks BIGINT,
  total_ua_spend_usd NUMERIC(18,4),
  cpi NUMERIC(18,4),
  fb_cpi NUMERIC(18,4),
  gads_cpi NUMERIC(18,4),
  mint_adv_cpi NUMERIC(18,4),
  fb_ctr NUMERIC(12,6),
  gads_ctr NUMERIC(12,6),
  mint_adv_ctr NUMERIC(12,6),
  admob_revenue_usd NUMERIC(18,4),
  admob_impressions BIGINT,
  applovin_revenue_usd NUMERIC(18,4),
  applovin_impressions BIGINT,
  total_ad_revenue_usd NUMERIC(18,4),
  admob_ecpm NUMERIC(18,4),
  applovin_ecpm NUMERIC(18,4),
  gp_iap_gross_usd NUMERIC(18,4),
  gp_iap_refunds_usd NUMERIC(18,4),
  gp_google_fee_usd NUMERIC(18,4),
  gp_iap_net_usd NUMERIC(18,4),
  gp_revenue_status TEXT,
  apple_iap_gross_usd NUMERIC(18,4),
  apple_iap_refunds_usd NUMERIC(18,4),
  apple_iap_net_usd NUMERIC(18,4),
  apple_fee_usd NUMERIC(18,4),
  apple_iap_purchases BIGINT,
  apple_revenue_status TEXT,
  total_iap_gross_usd NUMERIC(18,4),
  total_iap_net_usd NUMERIC(18,4),
  adjust_conversions BIGINT,
  adjust_attribution BIGINT,
  adjust_installs BIGINT,
  adjust_paid_installs BIGINT,
  adjust_organic_installs BIGINT,
  adjust_reattributions BIGINT,
  total_revenue_usd NUMERIC(18,4),
  profit_usd NUMERIC(18,4),
  roas NUMERIC(18,4),
  ad_roas NUMERIC(18,4),
  _built_at TIMESTAMPTZ,
  app_key TEXT GENERATED ALWAYS AS (
    COALESCE(canonical_key, android_package, CAST(apple_id AS TEXT), 'unknown')
  ) STORED,
  PRIMARY KEY (date, platform, app_key)
);

CREATE INDEX idx_fact_date ON fact_daily_performance (date);
CREATE INDEX idx_fact_canonical ON fact_daily_performance (canonical_key, date);
CREATE INDEX idx_fact_pod ON fact_daily_performance (pod, date);
CREATE INDEX idx_fact_hou ON fact_daily_performance (hou, date);
CREATE INDEX idx_fact_publisher ON fact_daily_performance (publisher, date);

GRANT SELECT ON fact_daily_performance TO api_service;
GRANT SELECT, INSERT, UPDATE, DELETE ON fact_daily_performance TO sync_service;
ALTER TABLE fact_daily_performance OWNER TO sync_service;  -- sync must RENAME/DROP it
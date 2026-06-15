-- ============================================================================
-- terafort.api.daily_performance_v1  —  THE STABLE CONTRACT
-- The platform reads ONLY this view. Change the underlying table freely;
-- keep this view's output columns (names + types) stable. Breaking change → _v2.
-- Derived metrics computed here in BigQuery (owner requirement). SAFE_DIVIDE
-- returns NULL on zero denominators — never errors, never fake zeros.
-- Prereq: CREATE SCHEMA IF NOT EXISTS `terafort.api`;
-- ============================================================================
CREATE OR REPLACE VIEW `terafort.api.daily_performance_v1` AS
SELECT
  -- identity & dimensions
  date, platform, canonical_key, apple_id, ios_bundle_id, android_package,
  app_name, publisher, developer, pod, pod_owner, hou,
  app_category, ownership_type, is_mapped,

  -- store installs (separated, validated)
  store_first_time_installs, store_redownloads, store_total_installs,
  store_organic_installs, gp_uninstalls, apple_restores,

  -- paid UA installs
  fb_paid_installs, gads_paid_installs, mint_adv_paid_installs, total_paid_installs,

  -- IAP
  gp_iap_gross_usd, gp_iap_refunds_usd, gp_google_fee_usd, gp_iap_net_usd, gp_revenue_status,
  apple_iap_gross_usd, apple_iap_refunds_usd, apple_iap_net_usd, apple_fee_usd,
  apple_iap_purchases, apple_revenue_status,
  total_iap_gross_usd, total_iap_net_usd,

  -- ad revenue (AdMob + AppLovin additive; Mintegral publisher excluded by design)
  admob_revenue_usd, admob_impressions, applovin_revenue_usd, applovin_impressions,
  total_ad_revenue_usd,

  -- UA spend & engagement
  fb_spend_usd, fb_impressions, fb_clicks, fb_purchases, fb_purchase_value,
  gads_spend_usd, gads_impressions, gads_clicks, gads_conversions, gads_conversions_value,
  mint_adv_spend_usd, mint_adv_impressions, mint_adv_clicks,
  total_ua_spend_usd,

  -- headline
  total_revenue_usd,

  -- Infra / tech cost per app-day (feeds Gross Profit on the Overview).
  -- PLACEHOLDER 0 until the data team adds tech_cost_usd to the source table;
  -- when it lands, replace this line with:  COALESCE(tech_cost_usd, 0) AS tech_cost_usd
  -- The sync also tolerates this column's absence (defaults to 0) — see sync_job.py.
  CAST(0 AS FLOAT64) AS tech_cost_usd,

  -- Adjust (data flows; NO dashboard features in v1 per requirements)
  adjust_conversions, adjust_attribution, adjust_installs,
  adjust_paid_installs, adjust_organic_installs, adjust_reattributions,

  -- ── DERIVED METRICS (all inputs verified to exist) ──
  ROUND(total_revenue_usd - total_ua_spend_usd, 4)                          AS profit_usd,
  ROUND(SAFE_DIVIDE(total_revenue_usd,    total_ua_spend_usd), 4)          AS roas,
  ROUND(SAFE_DIVIDE(total_ad_revenue_usd, total_ua_spend_usd), 4)          AS ad_roas,
  ROUND(SAFE_DIVIDE(total_ua_spend_usd,   total_paid_installs), 4)         AS cpi,
  ROUND(SAFE_DIVIDE(fb_spend_usd,         fb_paid_installs), 4)            AS fb_cpi,
  ROUND(SAFE_DIVIDE(gads_spend_usd,       gads_paid_installs), 4)          AS gads_cpi,
  ROUND(SAFE_DIVIDE(mint_adv_spend_usd,   mint_adv_paid_installs), 4)      AS mint_adv_cpi,
  ROUND(SAFE_DIVIDE(admob_revenue_usd,    admob_impressions)    * 1000, 4) AS admob_ecpm,
  ROUND(SAFE_DIVIDE(applovin_revenue_usd, applovin_impressions) * 1000, 4) AS applovin_ecpm,
  ROUND(SAFE_DIVIDE(fb_clicks,        fb_impressions), 6)                  AS fb_ctr,
  ROUND(SAFE_DIVIDE(gads_clicks,      gads_impressions), 6)                AS gads_ctr,
  ROUND(SAFE_DIVIDE(mint_adv_clicks,  mint_adv_impressions), 6)            AS mint_adv_ctr,
  ROUND(SAFE_DIVIDE(store_organic_installs, store_total_installs), 6)      AS organic_install_share,

  _built_at
FROM `terafort.Final_Staging_tables.unified_daily_performance`;

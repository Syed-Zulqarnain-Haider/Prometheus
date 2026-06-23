"""
metric_registry.py — SINGLE SOURCE OF TRUTH for every column in daily_performance_v1.

Everything is generated from this file:
  • the Postgres fact-table / staging DDL        (generate_fact_ddl)
  • the sync job's BigQuery schema validation    (expected_bq_schema)
  • (later) Pydantic response models + RBAC column filters in the API

Adding a column to the BQ view = add ONE entry here + run a migration. Nothing else.
Removing/renaming a view column without updating this file → sync halts with
'schema_mismatch' and serves yesterday's data (never loads garbage).
"""
from dataclasses import dataclass
from enum import Enum


class Group(str, Enum):
    DIMENSION = "dimension"
    STORE_INSTALLS = "store_installs"
    UA_SPEND = "ua_spend"
    AD_REVENUE = "ad_revenue"
    IAP_REVENUE = "iap_revenue"
    ATTRIBUTION = "attribution"
    PROFITABILITY = "profitability"
    SYSTEM = "system"


@dataclass(frozen=True)
class Col:
    name: str
    bq_type: str   # BigQuery INFORMATION_SCHEMA data_type
    pg_type: str   # Postgres column type
    group: Group


# fmt: off
REGISTRY: list[Col] = [
    # ── dimensions ──────────────────────────────────────────────────────────
    Col("date",            "DATE",    "DATE",    Group.DIMENSION),
    Col("platform",        "STRING",  "TEXT",    Group.DIMENSION),
    Col("canonical_key",   "STRING",  "TEXT",    Group.DIMENSION),
    Col("apple_id",        "INT64",   "BIGINT",  Group.DIMENSION),
    Col("ios_bundle_id",   "STRING",  "TEXT",    Group.DIMENSION),
    Col("android_package", "STRING",  "TEXT",    Group.DIMENSION),
    Col("app_name",        "STRING",  "TEXT",    Group.DIMENSION),
    Col("publisher",       "STRING",  "TEXT",    Group.DIMENSION),
    Col("developer",       "STRING",  "TEXT",    Group.DIMENSION),
    Col("pod",             "STRING",  "TEXT",    Group.DIMENSION),
    Col("pod_owner",       "STRING",  "TEXT",    Group.DIMENSION),
    Col("hou",             "STRING",  "TEXT",    Group.DIMENSION),
    Col("app_category",    "STRING",  "TEXT",    Group.DIMENSION),
    Col("ownership_type",  "STRING",  "TEXT",    Group.DIMENSION),
    Col("is_mapped",       "BOOL",    "BOOLEAN", Group.DIMENSION),

    # ── store installs ──────────────────────────────────────────────────────
    Col("store_first_time_installs", "INT64", "BIGINT", Group.STORE_INSTALLS),
    Col("store_redownloads",         "INT64", "BIGINT", Group.STORE_INSTALLS),
    Col("store_total_installs",      "INT64", "BIGINT", Group.STORE_INSTALLS),
    Col("store_organic_installs",    "INT64", "BIGINT", Group.STORE_INSTALLS),
    Col("gp_uninstalls",             "INT64", "BIGINT", Group.STORE_INSTALLS),
    Col("apple_restores",            "INT64", "BIGINT", Group.STORE_INSTALLS),
    Col("organic_install_share", "FLOAT64", "NUMERIC(12,6)", Group.STORE_INSTALLS),

    # ── paid UA installs + spend + engagement + derived ────────────────────
    Col("fb_paid_installs",       "INT64",   "BIGINT",           Group.UA_SPEND),
    Col("gads_paid_installs",     "FLOAT64", "DOUBLE PRECISION", Group.UA_SPEND),
    Col("mint_adv_paid_installs", "INT64",   "BIGINT",           Group.UA_SPEND),
    Col("total_paid_installs",    "FLOAT64", "DOUBLE PRECISION", Group.UA_SPEND),
    Col("fb_spend_usd",         "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND),
    Col("fb_impressions",       "INT64",   "BIGINT",        Group.UA_SPEND),
    Col("fb_clicks",            "INT64",   "BIGINT",        Group.UA_SPEND),
    Col("fb_purchases",         "INT64",   "BIGINT",        Group.UA_SPEND),
    Col("fb_purchase_value",    "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND),
    Col("gads_spend_usd",       "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND),
    Col("gads_impressions",     "INT64",   "BIGINT",        Group.UA_SPEND),
    Col("gads_clicks",          "INT64",   "BIGINT",        Group.UA_SPEND),
    Col("gads_conversions",     "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND),
    Col("gads_conversions_value","FLOAT64","NUMERIC(18,4)", Group.UA_SPEND),
    Col("mint_adv_spend_usd",   "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND),
    Col("mint_adv_impressions", "INT64",   "BIGINT",        Group.UA_SPEND),
    Col("mint_adv_clicks",      "INT64",   "BIGINT",        Group.UA_SPEND),
    Col("total_ua_spend_usd",   "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND),
    Col("cpi",          "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND),
    Col("fb_cpi",       "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND),
    Col("gads_cpi",     "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND),
    Col("mint_adv_cpi", "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND),
    Col("fb_ctr",       "FLOAT64", "NUMERIC(12,6)", Group.UA_SPEND),
    Col("gads_ctr",     "FLOAT64", "NUMERIC(12,6)", Group.UA_SPEND),
    Col("mint_adv_ctr", "FLOAT64", "NUMERIC(12,6)", Group.UA_SPEND),

    # ── ad revenue + derived ────────────────────────────────────────────────
    Col("admob_revenue_usd",    "FLOAT64", "NUMERIC(18,4)", Group.AD_REVENUE),
    Col("admob_impressions",    "INT64",   "BIGINT",        Group.AD_REVENUE),
    Col("applovin_revenue_usd", "FLOAT64", "NUMERIC(18,4)", Group.AD_REVENUE),
    Col("applovin_impressions", "INT64",   "BIGINT",        Group.AD_REVENUE),
    Col("total_ad_revenue_usd", "FLOAT64", "NUMERIC(18,4)", Group.AD_REVENUE),
    Col("admob_ecpm",           "FLOAT64", "NUMERIC(18,4)", Group.AD_REVENUE),
    Col("applovin_ecpm",        "FLOAT64", "NUMERIC(18,4)", Group.AD_REVENUE),

    # ── IAP revenue ─────────────────────────────────────────────────────────
    Col("gp_iap_gross_usd",      "FLOAT64", "NUMERIC(18,4)", Group.IAP_REVENUE),
    Col("gp_iap_refunds_usd",    "FLOAT64", "NUMERIC(18,4)", Group.IAP_REVENUE),
    Col("gp_google_fee_usd",     "FLOAT64", "NUMERIC(18,4)", Group.IAP_REVENUE),
    Col("gp_iap_net_usd",        "FLOAT64", "NUMERIC(18,4)", Group.IAP_REVENUE),
    Col("gp_revenue_status",     "STRING",  "TEXT",          Group.IAP_REVENUE),
    Col("apple_iap_gross_usd",   "FLOAT64", "NUMERIC(18,4)", Group.IAP_REVENUE),
    Col("apple_iap_refunds_usd", "FLOAT64", "NUMERIC(18,4)", Group.IAP_REVENUE),
    Col("apple_iap_net_usd",     "FLOAT64", "NUMERIC(18,4)", Group.IAP_REVENUE),
    Col("apple_fee_usd",         "FLOAT64", "NUMERIC(18,4)", Group.IAP_REVENUE),
    Col("apple_iap_purchases",   "INT64",   "BIGINT",        Group.IAP_REVENUE),
    Col("apple_revenue_status",  "STRING",  "TEXT",          Group.IAP_REVENUE),
    Col("total_iap_gross_usd",   "FLOAT64", "NUMERIC(18,4)", Group.IAP_REVENUE),
    Col("total_iap_net_usd",     "FLOAT64", "NUMERIC(18,4)", Group.IAP_REVENUE),

    # ── attribution (Adjust) — data synced, no v1 dashboard features ────────
    Col("adjust_conversions",      "INT64", "BIGINT", Group.ATTRIBUTION),
    Col("adjust_attribution",      "INT64", "BIGINT", Group.ATTRIBUTION),
    Col("adjust_installs",         "INT64", "BIGINT", Group.ATTRIBUTION),
    Col("adjust_paid_installs",    "INT64", "BIGINT", Group.ATTRIBUTION),
    Col("adjust_organic_installs", "INT64", "BIGINT", Group.ATTRIBUTION),
    Col("adjust_reattributions",   "INT64", "BIGINT", Group.ATTRIBUTION),

    # ── profitability / headline ────────────────────────────────────────────
    Col("total_revenue_usd", "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("tech_cost_usd",     "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("profit_usd",        "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("roas",              "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("ad_roas",           "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),

    # ── system ──────────────────────────────────────────────────────────────
    Col("_built_at", "TIMESTAMP", "TIMESTAMPTZ", Group.SYSTEM),
]
# fmt: on

COLUMN_NAMES: list[str] = [c.name for c in REGISTRY]

# Columns the registry knows about but the BigQuery view may not expose yet. When
# absent from the view, the sync defaults them to 0 instead of halting with a
# schema_mismatch. (tech_cost_usd: the data team will add the real field; until
# then we treat it as 0 so Gross Profit degrades gracefully rather than breaking.)
OPTIONAL_SOURCE_COLUMNS: set[str] = {"tech_cost_usd"}


def expected_bq_schema() -> dict[str, str]:
    """name -> BQ data_type, for INFORMATION_SCHEMA validation."""
    return {c.name: c.bq_type for c in REGISTRY}


def columns_for_groups(groups: set[Group]) -> list[str]:
    """Used later by the API to build per-role response models."""
    return [c.name for c in REGISTRY if c.group in groups]


def generate_fact_ddl(table_name: str) -> str:
    """Emit CREATE TABLE for the fact/staging table, plus the generated app_key
    column used as part of the primary key (expressions aren't allowed in PKs)."""
    cols = ",\n  ".join(f"{c.name} {c.pg_type}" for c in REGISTRY)
    return f"""CREATE TABLE {table_name} (
  {cols},
  app_key TEXT GENERATED ALWAYS AS (
    COALESCE(canonical_key, android_package, CAST(apple_id AS TEXT), 'unknown')
  ) STORED,
  PRIMARY KEY (date, platform, app_key)
);"""


# Columns covered by the date-leading covering index (idx_fact_cover) so the hot,
# uncached Overview aggregates (summary / timeseries / breakdown / table) run as
# INDEX-ONLY scans instead of scattered heap reads. Under production-like (uncorrelated)
# physical order a 30-day window touches ~almost every heap page; the covering index
# turns that into a contiguous index-only slice (~16x fewer buffer reads, results
# unchanged). The set is the group/table dimensions + the Overview's headline additive
# measures, curated to stay well under Postgres's 32-column-per-index limit (a single
# index cannot cover all ~50 additive measures).
COVER_INDEX_COLUMNS = [
    # dimensions used for scope filters, GROUP BY, and the table endpoint's max()
    "canonical_key", "platform", "apple_id", "android_package", "app_name",
    "publisher", "pod", "pod_owner", "hou",
    # headline additive measures (KPIs, donuts, trend, splits, revenue tables)
    "store_total_installs", "store_organic_installs", "total_paid_installs",
    "total_revenue_usd", "total_ua_spend_usd", "total_ad_revenue_usd",
    "total_iap_gross_usd", "total_iap_net_usd", "tech_cost_usd", "profit_usd",
]


def generate_indexes(table_name: str, suffix: str = "") -> list[str]:
    """Index DDL. `suffix` lets the staging table use non-conflicting names;
    they are renamed to canonical names after the atomic swap."""
    cover = f"(date) INCLUDE ({', '.join(COVER_INDEX_COLUMNS)})"
    specs = [
        ("idx_fact_date",      "(date)"),
        ("idx_fact_canonical", "(canonical_key, date)"),
        ("idx_fact_pod",       "(pod, date)"),
        ("idx_fact_hou",       "(hou, date)"),
        ("idx_fact_publisher", "(publisher, date)"),
        ("idx_fact_cover",     cover),
    ]
    return [f"CREATE INDEX {n}{suffix} ON {table_name} {cols};" for n, cols in specs]


INDEX_BASE_NAMES = ["idx_fact_date", "idx_fact_canonical", "idx_fact_pod",
                    "idx_fact_hou", "idx_fact_publisher", "idx_fact_cover"]

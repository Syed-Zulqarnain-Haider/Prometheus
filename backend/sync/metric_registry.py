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
    # BigQuery-discovered columns adopted by the admin schema-reconcile with no curated
    # metric group yet (admin-only on the serving side). Mirrors the backend registry.
    UNCLASSIFIED = "unclassified"


@dataclass(frozen=True)
class Col:
    name: str
    bq_type: str   # BigQuery INFORMATION_SCHEMA data_type
    pg_type: str   # Postgres column type
    group: Group
    # BigQuery expression that PRODUCES this column from the raw source table when the
    # sync reads the table directly (no view). None = plain pass-through (the source has a
    # column of this exact name). Set for the CAST(pod) dimension and every derived metric
    # (roas/profit/cpi/ecpm/ctr/organic_install_share) — the finance math the view used to
    # hold now lives here, so bypassing the view never drops a metric. Columns WITH a
    # source_expr are never expected to exist in the source, so schema validation/diff skip
    # them (see expected_bq_schema).
    source_expr: str | None = None


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
    # pod is INT64 in the source; the serving layer treats it as text (dim/group/filter),
    # so cast it here (the view used to do this).
    Col("pod",             "STRING",  "TEXT",    Group.DIMENSION,
        source_expr="CAST(pod AS STRING)"),
    Col("pod_owner",       "STRING",  "TEXT",    Group.DIMENSION),
    Col("hou",             "STRING",  "TEXT",    Group.DIMENSION),
    Col("app_category",    "STRING",  "TEXT",    Group.DIMENSION),
    Col("ownership_type",  "STRING",  "TEXT",    Group.DIMENSION),
    Col("is_mapped",       "BOOL",    "BOOLEAN", Group.DIMENSION),
    # store/console account dimensions (Console + account filters)
    Col("google_play_account", "STRING", "TEXT", Group.DIMENSION),
    Col("apple_account",       "STRING", "TEXT", Group.DIMENSION),
    Col("rpt_console",         "STRING", "TEXT", Group.DIMENSION),

    # ── store installs ──────────────────────────────────────────────────────
    Col("store_first_time_installs", "INT64", "BIGINT", Group.STORE_INSTALLS),
    Col("store_redownloads",         "INT64", "BIGINT", Group.STORE_INSTALLS),
    Col("store_total_installs",      "INT64", "BIGINT", Group.STORE_INSTALLS),
    Col("store_organic_installs",    "INT64", "BIGINT", Group.STORE_INSTALLS),
    Col("gp_uninstalls",             "INT64", "BIGINT", Group.STORE_INSTALLS),
    Col("apple_restores",            "INT64", "BIGINT", Group.STORE_INSTALLS),
    Col("organic_install_share", "FLOAT64", "NUMERIC(12,6)", Group.STORE_INSTALLS,
        source_expr="ROUND(SAFE_DIVIDE(store_organic_installs, store_total_installs), 6)"),

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
    Col("cpi",          "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND,
        source_expr="ROUND(SAFE_DIVIDE(total_ua_spend_usd, total_paid_installs), 4)"),
    Col("fb_cpi",       "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND,
        source_expr="ROUND(SAFE_DIVIDE(fb_spend_usd, fb_paid_installs), 4)"),
    Col("gads_cpi",     "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND,
        source_expr="ROUND(SAFE_DIVIDE(gads_spend_usd, gads_paid_installs), 4)"),
    Col("mint_adv_cpi", "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND,
        source_expr="ROUND(SAFE_DIVIDE(mint_adv_spend_usd, mint_adv_paid_installs), 4)"),
    Col("fb_ctr",       "FLOAT64", "NUMERIC(12,6)", Group.UA_SPEND,
        source_expr="ROUND(SAFE_DIVIDE(fb_clicks, fb_impressions), 6)"),
    Col("gads_ctr",     "FLOAT64", "NUMERIC(12,6)", Group.UA_SPEND,
        source_expr="ROUND(SAFE_DIVIDE(gads_clicks, gads_impressions), 6)"),
    Col("mint_adv_ctr", "FLOAT64", "NUMERIC(12,6)", Group.UA_SPEND,
        source_expr="ROUND(SAFE_DIVIDE(mint_adv_clicks, mint_adv_impressions), 6)"),

    # ── ad revenue + derived ────────────────────────────────────────────────
    Col("admob_revenue_usd",    "FLOAT64", "NUMERIC(18,4)", Group.AD_REVENUE),
    Col("admob_impressions",    "INT64",   "BIGINT",        Group.AD_REVENUE),
    Col("applovin_revenue_usd", "FLOAT64", "NUMERIC(18,4)", Group.AD_REVENUE),
    Col("applovin_impressions", "INT64",   "BIGINT",        Group.AD_REVENUE),
    Col("total_ad_revenue_usd", "FLOAT64", "NUMERIC(18,4)", Group.AD_REVENUE),
    Col("admob_ecpm",           "FLOAT64", "NUMERIC(18,4)", Group.AD_REVENUE,
        source_expr="ROUND(SAFE_DIVIDE(admob_revenue_usd, admob_impressions) * 1000, 4)"),
    Col("applovin_ecpm",        "FLOAT64", "NUMERIC(18,4)", Group.AD_REVENUE,
        source_expr="ROUND(SAFE_DIVIDE(applovin_revenue_usd, applovin_impressions) * 1000, 4)"),

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
    Col("profit_usd",        "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY,
        source_expr="ROUND(total_revenue_usd - total_ua_spend_usd, 4)"),
    Col("roas",              "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY,
        source_expr="ROUND(SAFE_DIVIDE(total_revenue_usd, total_ua_spend_usd), 4)"),
    Col("ad_roas",           "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY,
        source_expr="ROUND(SAFE_DIVIDE(total_ad_revenue_usd, total_ua_spend_usd), 4)"),

    # ── reported actual totals (rpt_*) — finance-authoritative figures the cards now show ──
    Col("rpt_gross_revenue_usd",     "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_ua_cost_usd",           "FLOAT64", "NUMERIC(18,4)", Group.UA_SPEND),
    Col("rpt_tf_profit_usd",         "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_shares_fees_taxes_usd", "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),

    # ── reported finance ladder (rpt_*), read straight from the source table ──────────────
    # The finance-authoritative figures the source already computes upstream — pass-through,
    # never recomputed here (owner decision to surface the reported ladder directly).
    Col("rpt_first_time_installs",       "INT64",   "BIGINT",        Group.STORE_INSTALLS),
    Col("rpt_redownloads",               "INT64",   "BIGINT",        Group.STORE_INSTALLS),
    Col("rpt_total_installs",            "INT64",   "BIGINT",        Group.STORE_INSTALLS),
    Col("rpt_organic_installs",          "INT64",   "BIGINT",        Group.STORE_INSTALLS),
    Col("rpt_ad_revenue_usd",            "FLOAT64", "NUMERIC(18,4)", Group.AD_REVENUE),
    Col("rpt_ad_revenue_after_share_usd","FLOAT64", "NUMERIC(18,4)", Group.AD_REVENUE),
    Col("rpt_total_revenue_usd",         "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_net_revenue_usd",           "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_net_revenue_terafort_usd",  "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_gross_profit_usd",          "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_net_profit_usd",            "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_total_cost_usd",            "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_tax_fees_usd",              "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_withholding_tax_usd",       "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_store_fee_usd",             "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_partner_fees_usd",          "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_partner_share_app_usd",     "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_partner_share_transsion_usd","FLOAT64","NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_partner_share_usd",         "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),
    Col("rpt_total_deductions_usd",      "FLOAT64", "NUMERIC(18,4)", Group.PROFITABILITY),

    # ── system ──────────────────────────────────────────────────────────────
    Col("_built_at", "TIMESTAMP", "TIMESTAMPTZ", Group.SYSTEM),
]
# fmt: on

COLUMN_NAMES: list[str] = [c.name for c in REGISTRY]

# Columns the registry knows about but the BigQuery view may not expose yet. When
# absent from the view, the sync defaults them to 0 instead of halting with a
# schema_mismatch. (tech_cost_usd: the data team will add the real field; until
# then we treat it as 0 so Gross Profit degrades gracefully rather than breaking.)
OPTIONAL_SOURCE_COLUMNS: set[str] = {
    "tech_cost_usd",
    # Newly surfaced from the source view; optional so the sync keeps working if the code
    # deploys before the updated daily_performance_v1 view. Type-aware defaults (0 for
    # numerics, NULL for text) are applied by the sync until the view exposes them.
    "google_play_account",
    "apple_account",
    "rpt_console",
    "rpt_gross_revenue_usd",
    "rpt_ua_cost_usd",
    "rpt_tf_profit_usd",
    "rpt_shares_fees_taxes_usd",
}


def optional_default_expr(name: str) -> str:
    """SQL literal for an optional source column the view doesn't expose yet, matched to the
    column's BigQuery type so the staging COPY stays type-correct (0 for numerics, typed NULL
    for text/bool/timestamp). Prevents a text dimension from being loaded as a numeric 0."""
    bq = {c.name: c.bq_type for c in REGISTRY}.get(name, "FLOAT64")
    if bq == "STRING":
        return f"CAST(NULL AS STRING) AS {name}"
    if bq == "BOOL":
        return f"CAST(NULL AS BOOL) AS {name}"
    if bq == "INT64":
        return f"CAST(0 AS INT64) AS {name}"
    if bq == "TIMESTAMP":
        return f"CAST(NULL AS TIMESTAMP) AS {name}"
    return f"CAST(0 AS FLOAT64) AS {name}"


# name -> BigQuery expression that produces each computed column from the raw source table.
# Used by the loader to build the SELECT; columns not here are plain pass-through.
SOURCE_EXPR: dict[str, str] = {
    c.name: c.source_expr for c in REGISTRY if c.source_expr is not None
}


def expected_bq_schema() -> dict[str, str]:
    """name -> BQ data_type, for INFORMATION_SCHEMA validation. Only pass-through columns are
    expected to exist in the source; computed columns (SOURCE_EXPR) are produced by the loader
    and must never be required in — or type-checked against — the raw table."""
    return {c.name: c.bq_type for c in REGISTRY if c.source_expr is None}


def columns_for_groups(groups: set[Group]) -> list[str]:
    """Used later by the API to build per-role response models."""
    return [c.name for c in REGISTRY if c.group in groups]


def generate_fact_ddl(table_name: str, with_pk: bool = True) -> str:
    """Emit CREATE TABLE for the fact/staging table, plus the generated app_key
    column used as part of the primary key (expressions aren't allowed in PKs).

    ``with_pk=False`` is used for the STAGING table: it omits the primary key so the load
    COPY can never crash on a duplicate natural key coming from the source view (the sync
    de-duplicates staging before merging — see ``generate_dedupe_sql``). The LIVE fact table
    always keeps its primary key, which the UPSERT relies on."""
    cols = ",\n  ".join(f"{c.name} {c.pg_type}" for c in REGISTRY)
    pk = ",\n  PRIMARY KEY (date, platform, app_key)" if with_pk else ""
    return f"""CREATE TABLE {table_name} (
  {cols},
  app_key TEXT GENERATED ALWAYS AS (
    COALESCE(canonical_key, android_package, CAST(apple_id AS TEXT), 'unknown')
  ) STORED{pk}
);"""


def generate_dedupe_sql(staging_table: str) -> str:
    """Remove duplicate natural-key rows from staging, keeping ONE deterministic row per
    (date, platform, app_key) — the richest one (highest revenue, then installs).

    The BigQuery view is expected to be unique per natural key. If it ever emits duplicates
    (e.g. a mapping collision that collapses two source rows to the same app_key), this keeps
    the sync from crashing on the staging load and avoids double-counting — instead of
    summing (which would corrupt derived ratios computed in the view). The sync logs and
    alerts the number removed, so the anomaly is visible and can be fixed at the source."""
    return f"""DELETE FROM {staging_table} s
USING (
    SELECT ctid, row_number() OVER (
        PARTITION BY date, platform, app_key
        ORDER BY total_revenue_usd DESC NULLS LAST,
                 store_total_installs DESC NULLS LAST,
                 ctid
    ) AS rn
    FROM {staging_table}
) d
WHERE s.ctid = d.ctid AND d.rn > 1"""


# The natural key the daily sync UPSERTs on — the fact table's primary key. app_key is a
# generated column (COALESCE of canonical_key / android_package / apple_id), so this
# triple uniquely identifies one app's row for one day across iOS + Android.
UPSERT_KEY = ("date", "platform", "app_key")


def generate_upsert_sql(
    fact_table: str, staging_table: str, extra_columns: list[str] | None = None
) -> str:
    """Emit the INSERT…SELECT…ON CONFLICT that merges a freshly loaded staging table
    into the live fact table, keyed on (date, platform, app_key).

    Re-running a date UPDATES the existing rows in place (every non-key column refreshed
    to the latest values — so the Apple 2-3 day lag self-corrects); a new date APPENDS;
    rows already in the fact table but absent from staging are RETAINED. The fact table
    therefore accumulates full history even after BigQuery ages older days out — never a
    destructive replace.

    ``extra_columns`` are BigQuery-discovered dynamic columns (identifier-safe) present in
    BOTH staging and fact for this run; they are merged exactly like registry columns."""
    all_cols = [*COLUMN_NAMES, *(extra_columns or [])]
    cols = ", ".join(all_cols)
    # app_key is generated (never in COLUMN_NAMES); date/platform are the key, not updated.
    key = set(UPSERT_KEY)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in all_cols if c not in key)
    conflict = ", ".join(UPSERT_KEY)
    return (
        f"INSERT INTO {fact_table} ({cols})\n"
        f"SELECT {cols} FROM {staging_table}\n"
        f"ON CONFLICT ({conflict}) DO UPDATE SET {updates}"
    )


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
